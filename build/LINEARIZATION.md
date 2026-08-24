# Hybrid Linearization: Sliced E-CPG → Text for Qwen2.5-Coder (Week 9–16, step B3)

Turn each backward slice (`SLICING.md §5`) into one text record for QLoRA fine-tuning.
**Hybrid** = a **code-sequential** block (what a code LLM reads best) + a **graph-structural**
block (the taint / include / inheritance edges as explicit triples). The code gives lexical
signal; the edges give the cross-module structure a plain listing would lose.

## 1. Design goals

1. Keep **real code** (Qwen2.5-Coder is a code model — don't obfuscate identifiers).
2. Make the **taint witness path** and the **cross-module hops** explicit and machine-uniform.
3. Only the **slice**, never whole files → fits context; deterministic truncation.
4. One fixed schema so the model learns the format; a **single scored label token** so we can
   read a probability for **PR-AUC**.
5. Identical wrapper for the 3 ablation variants (no-slice / intra / cross) — only the SLICE
   content changes.

## 2. Special tokens (add to tokenizer as additional_special_tokens)

```
[SLICE] [/SLICE] [EDGES] [/EDGES]        block delimiters
[UNIT file=… func=… class=…]             a code unit (file/function/method) header
[SRC] [SAN] [SNK]                        role of the line: taint source / sanitizer / sink
⟦t⟧                                       marks the tainted symbol inline, e.g. ⟦t⟧$entity
[INCLUDE→ path]                          MDG hop: control/scope crosses into an included file
[INHERIT→ Class::member]                 CHG hop: resolution crosses EXTENDS / TRAIT
[Ln]                                      original line number tag (kept for traceability)
```
Node ids are rewritten to small local ids `n0,n1,…` (stable within a record) so the EDGES
block stays short and the model isn't asked to reason over 6-digit Neo4j ids.

## 3. Record layout

```
<META>  cwe=<CWE-xx> boundary=<include|inherit|include+inherit|intra> vartrace=⟦t⟧$name
[SLICE]
[UNIT file=A.php func=<toplevel>]
 n0 [Ln 8] [SRC] $entity = ⟦t⟧$_POST['entity'];
[INCLUDE→ ../../includes/authenticate.php]
[UNIT file=authenticate.php func=<toplevel>]
 n1 [Ln 20] if (!checkAuth()) exit;            # control predicate pulled via one FLOWS_TO hop
[UNIT file=A.php func=<toplevel>]
 n2 [Ln 8] [SNK] $out = escapeshellcmd(⟦t⟧$entity);   # sink for CWE-78
[/SLICE]
[EDGES]
 n0 -REACHES($entity)-> n2
 n0 -SOURCE-> $_POST
 n2 -SINK(cmd)-> escapeshellcmd
[/EDGES]
```

- **SLICE** is emitted in **witness order** source→…→sink; when the path leaves a file/class,
  an `[INCLUDE→]` / `[INHERIT→]` marker precedes the next `[UNIT]`. This is the visible
  cross-module boundary — the crux of the whole method.
- **EDGES** lists only slice-internal edges: `REACHES(var)` (def-use), `CALLS` (interproc),
  `INCLUDE`, `EXTENDS`/`TRAIT`, plus synthetic `SOURCE`/`SINK(class)` annotations. Format:
  `<src_id> -<REL(arg)>-> <dst_id>`.

## 4. Ordering, dedup, truncation

- Order SLICE by the witness path; if several def-use predecessors feed one node, emit them
  in ascending `(file, lineno)` immediately before that node.
- One line per node; dedup repeated nodes by local id.
- **Truncation** to `MAX_TOKENS` (e.g. 2048): drop nodes **farthest (in edges) from the
  sink** first; never drop `[SRC]`, `[SNK]`, or any `[INCLUDE→]/[INHERIT→]` marker. Record a
  `[TRUNCATED k nodes]` note so it's explicit.

## 5. Prompt wrapping + label (for QLoRA + scoring)

Use the Qwen2.5 chat template. The **assistant target is a single deterministic line ending
in a scored label token**, so training is next-token and inference reads one probability.

```
<|im_start|>system
You are a PHP taint-analysis judge. Given a program slice (code + data-flow edges), decide if
untrusted input reaches the sink unsanitized.<|im_end|>
<|im_start|>user
<the full record from §3><|im_end|>
<|im_start|>assistant
verdict=VULNERABLE cwe=CWE-78 boundary=include<|im_end|>
```

- **Label space:** the token right after `verdict=` is `VULNERABLE` | `SAFE`.
  **PR-AUC / F1 score = softmax prob of the `VULNERABLE` token** at that position
  (teacher-forced up to `verdict=`). `cwe=`/`boundary=` are auxiliary supervision (multitask)
  and can be dropped for a pure binary head.
- Train only on the assistant span (mask the prompt) — standard QLoRA SFT loss.

## 6. Positives, negatives, and the 3 ablation renderings

Every training item is the **same seed sink** rendered under one variant; the wrapper (§5) is
identical, only `[SLICE]`/`[EDGES]` differ:

| Variant | SLICE content | Purpose |
|---|---|---|
| **no-slice** | whole enclosing function/file text, no EDGES block | baseline 1 |
| **intra-file** | slice with steps b/c/d disabled (no CALLS-across-file, no INCLUDE, no INHERIT) | baseline 2 |
| **cross-module** | full slice incl. `[INCLUDE→]/[INHERIT→]` hops + EDGES | our method |

Labels: **positive** = slice whose witness path reaches a source unsanitized (from the
dataset's `vuln/` pre-fix code); **negative** = the **`fixed/` post-fix** rendering of the
same seed (sanitizer now on the path → `verdict=SAFE`), **plus** naturally-safe sinks found
during slicing (hard negatives). Keep positive:negative ≈ 1:1–1:3 and **inherit the
train/val/test assignment from `splits.json`** (repo-grouped — no leakage).

## 7. Fine-tune data schema (`ft_dataset.jsonl`, one row per rendered item)

```json
{"id":"GHSA-277f-37gw-9gmq","cwe":"CWE-78","boundary":"include",
 "variant":"cross-module","label":"VULNERABLE","split":"train",
 "prompt":"<system+user text>","target":"verdict=VULNERABLE cwe=CWE-78 boundary=include"}
```
Join keys `id` → `samples.jsonl` (code paths) and `id`'s repo → `splits.json` (split). Emit
all 3 variants per seed so ablations train/evaluate on identical seeds.

## 8. Why this beats a plain code dump (the thesis hypothesis)

`no-slice` drowns the sink in irrelevant code; `intra-file` **cannot see** a source that lives
across an `INCLUDE`/`EXTENDS` boundary, so on `boundary≠intra` samples its taint evidence is
absent → lower recall. The cross-module hybrid makes both the code and the boundary-crossing
edges explicit, which is exactly the signal the F1 / PR-AUC gap should reward.
