# Package Index — PHPJoy Cross-Module Dataset + Phase-2 Blueprint

Two things in one package: (A) the verifiable cross-module PHP vulnerability **dataset**, and
(B) the **Week 9–16 pipeline** (backward slicing → hybrid linearization → QLoRA) built on it.

## A. Dataset (verify first)
| Path | What |
|---|---|
| `dataset_xmodule/` | 977 cross-module positives / 13 CWE, each with a matched negative; `index.json`, `samples.jsonl`, `splits.json`, `STATS.md`, `README.md`, `dropped.json` |
| `METHODOLOGY.md` | how the dataset was built (OSV → taint-CWE → git cross-module classifier) |
| `VERIFY.md` | **start here** — 3 verification levels (provenance / manual / E-CPG) |
| `candidates_taint.json` | the 1830 harvested candidates (reproduction) |
| `scripts/verify_provenance.ps1` | re-fetches each fix commit from GitHub, byte-checks vuln/fixed (authenticity) |
| `scripts/review.ps1` | stratified manual-review helper (label precision) |
| `scripts/make_splits.ps1` | regenerates the repo-grouped, leakage-free train/val/test split |
| `scripts/extract_osv.ps1 … consolidate.ps1` | the 5-stage build pipeline |

## B. Phase-2 blueprint (`phase2/`)
| Path | What | Runs on |
|---|---|---|
| `phase2/SOURCES_SINKS_XCHECK.md` | PHPJoy ↔ NAVEX ↔ TChecker source/sink/sanitizer table + 3 model bugfixes | — |
| `phase2/SLICING.md` | backward taint-slicing algorithm over the E-CPG (MDG+CHG) | — |
| `phase2/LINEARIZATION.md` | hybrid graph→text format for Qwen2.5-Coder | — |
| `phase2/SMOKE_TEST.md` | **run this first** — de-risk the whole chain on one sample | PHP+Java+Neo4j |
| `phase2/PHASE3_PLAN.md` | Phase-3 plan: ablations, robustness, comparison + acceptance | — |
| `phase2/code/backward_slice.py` | B2 slicer (`GlobalBackwardSliceTraversal`, `run_slicing`) | Neo4j |
| `phase2/code/linearize.py` | B3 linearizer (`build_ft_dataset` → `ft_dataset.jsonl`) | after B2 |
| `phase2/code/vuln_model.py` | **patched** source/sink/sanitizer model (drop-in replacement) | — |
| `phase2/code/smoke_slice.py` | one-sample B2+B3 smoke script | Neo4j |
| `scripts/qlora_train_eval.py` | B4 QLoRA fine-tune + F1/PR-AUC eval by variant | GPU |
| `scripts/perturb.py` | Phase-3 robustness: 6 semantic-preserving PHP transforms | Python only |
| `scripts/eval_external.py` | Phase-3 comparison: score NAVEX/TChecker/Progpilot at sample level | Python only |

See `phase2/PHASE2_README.md` for where each code file goes in the PHPJoy artifact and the
end-to-end run order.

## What runs where
- **Now, no toolchain:** dataset verification (Level 1/2), split, all design docs.
- **Needs PHP+Java+Neo4j (E-CPG):** SMOKE_TEST, `backward_slice.py`, `linearize.py`.
- **Needs GPU:** `qlora_train_eval.py`.

All Phase-2 code is written against the real PHPJoy API and marked `# VERIFY` where a live
Neo4j graph is required to confirm a method's behaviour. It has not been executed offline.
