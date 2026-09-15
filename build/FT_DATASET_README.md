# `ft_dataset.jsonl.gz` — the Phase-2 fine-tuning corpus

Committed gzipped (1.8 MB; 36 MB raw). Unpack before use:

```bash
gunzip -c build/ft_dataset.jsonl.gz > build/ft_dataset.jsonl
```

## What is in it

15 786 rows produced by `build/run_phase2.py --split test` over the cross-module CVE corpus in
`build/dataset_xmodule/`. One row per (seed sink × variant):

| variant | rows | VULNERABLE | SAFE | positive rate |
|---|---|---|---|---|
| cross-module | 5 262 | 210 | 5 052 | 4.0% |
| intra-file | 5 262 | 104 | 5 158 | 2.0% |
| no-slice | 5 262 | 210 | 5 052 | 4.0% |

The three variants are rendered from an **identical seed set**, which is what makes the ablation
a fair comparison. Row schema is described in `LINEARIZATION.md` §7.

Provenance of this corpus: 89 of 144 test samples completed (71 produced slices, 18 had no
qualifying sink), 55 were retired as unanalysable on the available hardware. The accompanying
`phase2_state.json` (completed ids) and `phase2_attempts.json` (per-sample failure counts)
record exactly which samples contributed.

## Running the comparison

```bash
pip install "transformers>=4.44" peft bitsandbytes datasets accelerate scikit-learn
python build/qlora_train_eval.py --data build/ft_dataset.jsonl \
                                 --model Qwen/Qwen2.5-Coder-7B-Instruct
```

Needs a GPU. Acceptance criterion: `variant=cross-module` beats both `intra-file` and
`no-slice` on F1 and PR-AUC.

## Three things that will silently corrupt the result

Read `THREATS_TO_VALIDITY.md` before reporting numbers. The short version:

1. **Do not de-duplicate this file first.** De-duplication is not variant-neutral: the no-slice
   rendering is the whole enclosing function, so sinks sharing a function are byte-identical and
   that arm collapses from 5 262 rows to 990 while the sliced arms barely move, destroying the
   seed pairing. `dedupe_ft_dataset.py` is for corpus statistics, not for building the eval set.
2. **Do not subset on a row's `boundary` field.** It records what the *slice* crossed, and the
   intra-file variant is defined by forbidding cross-file steps, so 100% of its rows are
   `boundary=intra`. Filtering on it leaves the baseline with zero rows. Subset on the sample's
   ground-truth `boundary_type` in `dataset_xmodule/index.json` instead.
3. **Report PR-AUC, not accuracy,** and quote the positive rate next to F1 — the corpus is 2-4%
   positive and the rate differs per variant.
