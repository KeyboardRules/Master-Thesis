# Phase-2 (Week 9–16) — install & run order

The Phase-2 code plugs into the **PHPJoy artifact** (the `api-framework` + `phpjoy` +
`tutorial` tree). This package ships the new/changed files under `phase2/code/`; copy them in:

| Ship file (`phase2/code/`) | Copy to (in the PHPJoy artifact) | Note |
|---|---|---|
| `vuln_model.py` | `api-framework/apis/vuln_model.py` | **replaces** the original (keep a `.bak`). Fixes: `_REQUESTS`→`_REQUEST`, `_FILE`→`_FILES`, +`_SERVER`/`_ENV`; decoders removed from sanitizers; `preg_replace`→CODE_INJECTION sink; `eregi` comma. |
| `backward_slice.py` | `api-framework/apis/backward_slice.py` | new (B2) |
| `linearize.py` | `api-framework/apis/linearize.py` | new (B3) |
| `smoke_slice.py` | `tutorial/smoke_slice.py` | new (smoke test) |

`qlora_train_eval.py` (B4) stays wherever you keep `ft_dataset.jsonl`; it only needs pip deps.

## Run order

1. **Smoke test (do this first).** Follow `phase2/SMOKE_TEST.md`: build the `tutorial/example`
   E-CPG, import to Neo4j, run `tutorial/main.py -vt 9` (forward, sanity), then
   `tutorial/smoke_slice.py -vt 9` (B2+B3). Work through the `# VERIFY` checklist. Green ⇒ proceed.

2. **Build `ft_dataset.jsonl`** (SMOKE_TEST.md §8): for each sample in `dataset_xmodule/`,
   build two E-CPGs — `repo@<fix_commit>^1` (positive/vulnerable) and `repo@<fix_commit>`
   (negative/fixed) — and call `apis.linearize.build_ft_dataset(af, vuln_type, cwe, id, split, out)`.
   Get `split` from `dataset_xmodule/splits.json` (repo-grouped, no leakage). Emit all 3
   variants/seed (cross-module / intra-file / no-slice).

3. **Fine-tune + evaluate** (B4):
   ```bash
   pip install "transformers>=4.44" peft bitsandbytes datasets accelerate scikit-learn
   python scripts/qlora_train_eval.py --data ft_dataset.jsonl --model Qwen/Qwen2.5-Coder-7B-Instruct
   ```
   The eval prints F1 / PR-AUC per `variant` and per CWE. **Acceptance:**
   `variant:cross-module` beats `variant:intra-file` and `variant:no-slice`.

## Dependency map
```
vuln_model.py (patched) ─► backward_slice.py (B2, Neo4j) ─► linearize.py (B3)
        └────────────────────────────────────────────────► ft_dataset.jsonl (+ splits.json)
                                                                    └► qlora_train_eval.py (B4, GPU)
```
Design rationale for each stage: `phase2/SOURCES_SINKS_XCHECK.md` (B1), `SLICING.md` (B2),
`LINEARIZATION.md` (B3).
