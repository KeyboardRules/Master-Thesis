# Phase-3 Plan — Ablations, Robustness, Comparison

Phase 3 answers three questions on top of the trained model (Phase 2): *what* makes it work
(ablations), *how well it holds up* (robustness), and *how it stacks up* (comparison). All
runs reuse the repo-grouped test split in `dataset_xmodule/splits.json` (no leakage), report
**F1 + PR-AUC** as in `scripts/qlora_train_eval.py`, and hold every other factor fixed.

## 1. Ablations — isolate the contribution of each design choice

| # | Factor toggled | Hypothesis | How to run (knob) |
|---|---|---|---|
| A1 | **Slice scope**: no-slice → intra-file → cross-module | cross-module wins, gap largest on `boundary≠intra` | already emitted: `variant` in `ft_dataset.jsonl` (`build_ft_dataset`) |
| A2 | **Boundary layer**: PDG-only → +MDG(include) → +CHG(inherit) → full | each cross-module edge type adds recall | add flags `disable_include` / `disable_inherit` to `GlobalBackwardSliceTraversal` (mirror `intra_file_only`); regenerate variants |
| A3 | **Linearization**: code-only vs code+`[EDGES]` | the structural edge block adds signal | in `linearize_slice`, emit with / without the `[EDGES]` block |
| A4 | **Model patch**: patched `vuln_model.py` vs original `.bak` | fixing source typos + decoder bug lifts recall | swap the two files, rebuild `ft_dataset.jsonl` |
| A5 | **Control context**: with / without the `FLOWS_TO` predicate hop | guard predicates help disambiguate sanitized paths | include/exclude predicate nodes in the slice |
| A6 | **Base model size**: Qwen2.5-Coder 1.5B / 3B / 7B | larger helps but slicing helps at every size | `--model` in `qlora_train_eval.py` |

Report each as a Δ(F1) / Δ(PR-AUC) vs the full model, split overall / per-CWE / macro. The
headline ablation is **A1** (it is the thesis claim); A2 shows *which* boundary matters.

## 2. Robustness — does it generalize, or memorize?

| Axis | Protocol | Metric |
|---|---|---|
| **Cross-project** | test = unseen repos (already guaranteed by repo-grouped split) | F1/PR-AUC on test; gap vs a random-split control quantifies leakage avoided |
| **Semantic-preserving perturbation** | apply transforms that do NOT change the vuln, re-run inference | **consistency** = % verdict unchanged; **robust-F1** = F1 under perturbation |
| **Class imbalance** | XSS = 50%; 2 tiny CWEs (73, 98) | per-CWE + **macro**-F1/PR-AUC; flag CWE-73/98 as low-n |
| **Distribution shift** | group test by PHP-version / framework style if labelled | F1 per group |

Perturbation harness (semantic-preserving, apply to the PHP *before* E-CPG build, or to the
linearized record for a cheaper proxy):
- variable / parameter **renaming** (consistent),
- **dead-code** insertion (unrelated statements, unused vars),
- **comment / whitespace / formatting** changes,
- independent-statement **reordering**,
- wrapping the sink file behind **one extra include layer** (stress the MDG step).

A robust model keeps its verdict; a memorizing one flips. Report the consistency matrix and
the F1 drop per transform; expect the **cross-module** model to be *more* stable on the
extra-include transform than the intra-file baseline.

## 3. Comparison — against baselines and prior tools

| Group | Systems | Alignment |
|---|---|---|
| **Internal baselines** | no-slice, intra-file (Phase-2 variants) | identical seeds/split |
| **Prior detectors (26-week plan targets)** | **RealVul, VulEye, DeepTective, and PHPJoy's own static analysis** | run on the same test repos@commit; compare at **CVE level** (detected/not) |
| **Zero-shot control** | vanilla Qwen2.5-Coder (no fine-tune) | same test records |

Note: NAVEX / TChecker are NOT Phase-3 comparison targets — they are used in Phase 2 to
cross-check the source/sink/sanitizer model (see `SOURCES_SINKS_XCHECK.md`). PHPJoy-static =
running PHPJoy's own forward taint analysis (`tutorial/main.py` / `GlobalPDGForwardTraversalWithModel`)
as a non-LLM baseline on the same split.

Fairness notes:
- Static tools emit **paths**, we classify **slices** → align at the **sample (CVE) level**:
  a tool "detects" a sample if it flags the vulnerable statement in `vuln/`.
- Evaluate everyone on **positives = `vuln/`** and **negatives = `fixed/`** of the test split.
- Report precision / recall / F1 / PR-AUC; for tools without scores, report F1 at their
  operating point and place them as points on the PR curve.
- Cross-reference the sink coverage in `phase2/SOURCES_SINKS_XCHECK.md` when explaining
  recall differences (e.g. a tool lacking SSRF/XXE sinks).

## 4. Protocol & reporting

- **Primary metrics:** PR-AUC (threshold-free) and F1@0.5; secondary: precision, recall.
- **Breakdowns:** overall, per-`variant`, per-CWE, macro-over-CWE (already produced by
  `qlora_train_eval.py`).
- **Significance:** bootstrap 95% CI on PR-AUC (resample test samples); **McNemar** test
  between cross-module and each baseline on the paired verdicts.
- **Controls:** fixed seed, same split, same base model per comparison; log every hyper-param.

## 5. Acceptance for Phase 3
1. **Ablation:** `cross-module` > `intra-file` > `no-slice` on F1 and PR-AUC, gap significant
   (McNemar p<0.05) and largest on `boundary≠intra`.
2. **Robustness:** verdict consistency ≥ a stated bound under semantic-preserving transforms;
   no collapse on the extra-include stress test.
3. **Comparison:** competitive with / beating NAVEX, TChecker and the LLM baselines at CVE
   level on the held-out repos, with the source/sink model differences accounted for.

## Code touch-points — DONE (shipped in this package)
- ✅ `backward_slice.py`: `disable_include` / `disable_inherit` flags (A2) + `with_control_context`
  predicate toggle (A5). Drive via `run_slicing(af, vt, disable_include=True, ...)`.
- ✅ `linearize.py`: `include_edges: bool` on `linearize_slice` / `build_ft_dataset` — drops the
  `[EDGES]` block for A3.
- ✅ `perturb.py` (phase2/code or scripts): 6 semantic-preserving transforms + CLI + manifest.
- ✅ `eval_external.py`: sample-level scoring of NAVEX/TChecker/Progpilot vs the test split,
  from a normalized `findings.jsonl` (incl. a Progpilot parser).

Ablation drivers (A1 variant, A6 model size) already exist in `scripts/qlora_train_eval.py`.
So Phase-3 is code-complete; only execution remains (E-CPG toolchain + GPU).
