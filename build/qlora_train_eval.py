#!/usr/bin/env python
"""
QLoRA fine-tune + evaluation of Qwen2.5-Coder on the hybrid-linearized slices (thesis step B4).

Input : ft_dataset.jsonl  (from apis.linearize.build_ft_dataset) — rows:
        {id, cwe, boundary, variant, label(VULNERABLE|SAFE), split, prompt, target}
Output: a LoRA adapter + a metrics report (F1 / PR-AUC) broken down by variant and CWE, i.e.
        the head-to-head the thesis needs:  cross-module  vs  intra-file  vs  no-slice.

Stack: transformers + peft + bitsandbytes + datasets + sklearn (GPU required to RUN; this file
is authored offline and has NOT been executed here). Install:
    pip install "transformers>=4.44" peft bitsandbytes datasets accelerate scikit-learn

Train:   python qlora_train_eval.py --data ft_dataset.jsonl --model Qwen/Qwen2.5-Coder-7B-Instruct
Eval:    python qlora_train_eval.py --data ft_dataset.jsonl --adapter out/ --eval_only
"""
import argparse, json, math, os
from collections import defaultdict

import torch
from datasets import Dataset
from transformers import (AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig,
                          Trainer, TrainingArguments)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training, PeftModel
from sklearn.metrics import average_precision_score, f1_score, precision_recall_fscore_support

SPECIAL_TOKENS = ["[SLICE]", "[/SLICE]", "[EDGES]", "[/EDGES]", "[SRC]", "[SAN]", "[SNK]", "⟦t⟧"]
LABELS = ("VULNERABLE", "SAFE")


# ------------------------------------------------------------------ data ------------------
def load_rows(fp):
    with open(fp, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def build_tokenizer(model_name):
    tok = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    tok.add_special_tokens({"additional_special_tokens": SPECIAL_TOKENS})
    return tok


def tokenize_completion_only(rows, tok, max_len):
    """labels = -100 on the prompt span so loss is computed only on the assistant target."""
    def _map(r):
        target = r["target"] + tok.eos_token
        p_ids = tok(r["prompt"], add_special_tokens=False)["input_ids"]
        t_ids = tok(target, add_special_tokens=False)["input_ids"]
        ids = (p_ids + t_ids)[:max_len]
        labels = ([-100] * len(p_ids) + t_ids)[:max_len]
        attn = [1] * len(ids)
        return {"input_ids": ids, "labels": labels, "attention_mask": attn}
    return Dataset.from_list([_map(r) for r in rows])


class PadCollator:
    def __init__(self, tok): self.tok = tok
    def __call__(self, feats):
        m = max(len(f["input_ids"]) for f in feats)
        pad = self.tok.pad_token_id
        out = {"input_ids": [], "attention_mask": [], "labels": []}
        for f in feats:
            n = m - len(f["input_ids"])
            out["input_ids"].append(f["input_ids"] + [pad] * n)
            out["attention_mask"].append(f["attention_mask"] + [0] * n)
            out["labels"].append(f["labels"] + [-100] * n)
        return {k: torch.tensor(v) for k, v in out.items()}


# ------------------------------------------------------------------ model -----------------
def load_base(model_name, four_bit=True):
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_compute_dtype=torch.bfloat16,
                             bnb_4bit_use_double_quant=True) if four_bit else None
    model = AutoModelForCausalLM.from_pretrained(
        model_name, quantization_config=bnb, device_map="auto",
        torch_dtype=torch.bfloat16, trust_remote_code=True)
    return model


def add_lora(model):
    model = prepare_model_for_kbit_training(model)
    cfg = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"])
    return get_peft_model(model, cfg)


# ------------------------------------------------------------------ scoring ---------------
@torch.no_grad()
def label_logprob(model, tok, prompt, label, device):
    """log P(label | prompt + 'verdict=') summed over the label's tokens."""
    ctx = prompt + "verdict="
    ctx_ids = tok(ctx, add_special_tokens=False)["input_ids"]
    lab_ids = tok(label, add_special_tokens=False)["input_ids"]
    ids = torch.tensor([ctx_ids + lab_ids], device=device)
    logits = model(ids).logits.float()
    lp = torch.log_softmax(logits, dim=-1)[0]
    total, start = 0.0, len(ctx_ids)
    for i, tid in enumerate(lab_ids):
        total += lp[start + i - 1, tid].item()          # predict token at pos from previous
    return total


@torch.no_grad()
def evaluate(model, tok, rows, device):
    """Score = softmax over {VULNERABLE, SAFE} log-likelihoods; report F1 & PR-AUC by variant/CWE."""
    model.eval()
    by = defaultdict(lambda: {"y": [], "s": []})
    for r in rows:
        lv = label_logprob(model, tok, r["prompt"], LABELS[0], device)
        ls = label_logprob(model, tok, r["prompt"], LABELS[1], device)
        p_vuln = math.exp(lv) / (math.exp(lv) + math.exp(ls) + 1e-12)
        y = 1 if r["label"] == "VULNERABLE" else 0
        for key in ("ALL", f"variant:{r['variant']}", f"cwe:{r['cwe']}"):
            by[key]["y"].append(y); by[key]["s"].append(p_vuln)

    def metrics(y, s):
        if len(set(y)) < 2:
            return {"n": len(y), "pr_auc": float("nan"), "f1": float("nan")}
        pred = [1 if x >= 0.5 else 0 for x in s]
        return {"n": len(y),
                "pr_auc": round(average_precision_score(y, s), 4),
                "f1": round(f1_score(y, pred), 4)}

    report = {k: metrics(v["y"], v["s"]) for k, v in by.items()}
    # macro-F1 / macro-PR-AUC over CWEs
    cwe_keys = [k for k in report if k.startswith("cwe:") and not math.isnan(report[k]["f1"])]
    if cwe_keys:
        report["MACRO_over_CWE"] = {
            "n": len(cwe_keys),
            "pr_auc": round(sum(report[k]["pr_auc"] for k in cwe_keys) / len(cwe_keys), 4),
            "f1": round(sum(report[k]["f1"] for k in cwe_keys) / len(cwe_keys), 4)}
    return report


def print_report(rep):
    print("\n=== F1 / PR-AUC ===")
    order = (["ALL", "MACRO_over_CWE"]
             + sorted(k for k in rep if k.startswith("variant:"))
             + sorted(k for k in rep if k.startswith("cwe:")))
    print(f"{'group':28s} {'n':>5s} {'PR-AUC':>8s} {'F1':>7s}")
    for k in order:
        if k in rep:
            m = rep[k]; print(f"{k:28s} {m['n']:>5d} {str(m['pr_auc']):>8s} {str(m['f1']):>7s}")
    print("\nThesis claim holds iff variant:cross-module > variant:intra-file and > variant:no-slice.")


# ------------------------------------------------------------------ main ------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--model", default="Qwen/Qwen2.5-Coder-7B-Instruct")
    ap.add_argument("--output", default="out")
    ap.add_argument("--adapter", default=None, help="load an existing LoRA adapter")
    ap.add_argument("--epochs", type=float, default=3)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--grad_accum", type=int, default=16)
    ap.add_argument("--max_len", type=int, default=2048)
    ap.add_argument("--eval_only", action="store_true")
    args = ap.parse_args()

    rows = load_rows(args.data)
    tr = [r for r in rows if r["split"] == "train"]
    va = [r for r in rows if r["split"] == "val"]
    te = [r for r in rows if r["split"] == "test"]
    print(f"rows: train={len(tr)} val={len(va)} test={len(te)}")

    tok = build_tokenizer(args.model)
    model = load_base(args.model)
    model.resize_token_embeddings(len(tok))

    if args.adapter:
        model = PeftModel.from_pretrained(model, args.adapter)
    elif not args.eval_only:
        model = add_lora(model)
        train_ds = tokenize_completion_only(tr, tok, args.max_len)
        val_ds = tokenize_completion_only(va, tok, args.max_len) if va else None
        targs = TrainingArguments(
            output_dir=args.output, num_train_epochs=args.epochs,
            per_device_train_batch_size=args.batch, gradient_accumulation_steps=args.grad_accum,
            learning_rate=args.lr, bf16=True, logging_steps=10,
            save_strategy="epoch", eval_strategy=("epoch" if val_ds else "no"),
            warmup_ratio=0.03, lr_scheduler_type="cosine", report_to=[])
        Trainer(model=model, args=targs, train_dataset=train_ds, eval_dataset=val_ds,
                data_collator=PadCollator(tok)).train()
        model.save_pretrained(os.path.join(args.output, "adapter"))
        tok.save_pretrained(os.path.join(args.output, "adapter"))

    device = next(model.parameters()).device
    print_report(evaluate(model, tok, te, device))


if __name__ == "__main__":
    main()
