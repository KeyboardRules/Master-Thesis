# HANDOFF — take over PHPJoy Phase-2 execution

You are continuing a thesis project (cross-module PHP vulnerability detection with an Enhanced
Code Property Graph). Earlier work was done on machines without the toolchain; you are now on
Linux where it CAN run. Read this, then build/METHODOLOGY.md, build/SMOKE_TEST.md,
build/PHASE2_README.md, build/SLICING.md, build/LINEARIZATION.md.

## State
- Phase 1 (DONE, real): dataset of 977 cross-module PHP CVE positives / 13 CWE, each with a
  matched negative. In build/dataset_xmodule/ (index.json, splits.json = repo-grouped
  train/val/test, per-sample meta.json with repo/fix_commit/cwe/changed_php).
- Phase 2 & 3 (CODE-COMPLETE but NEVER EXECUTED — needs this toolchain + a GPU):
  - api-framework/apis/vuln_model.py    (PATCHED source/sink/sanitizer model; .bak = original)
  - api-framework/apis/backward_slice.py (B2: GlobalBackwardSliceTraversal + run_slicing; backward
    taint slice over PDG/CG + MDG(INCLUDE)/CHG(EXTENDS,TRAIT); ablation flags disable_include/
    disable_inherit/with_control_context)
  - api-framework/apis/linearize.py     (B3: Slice -> hybrid text; build_ft_dataset -> ft_dataset.jsonl)
  - build/qlora_train_eval.py           (B4: QLoRA Qwen2.5-Coder + F1/PR-AUC by variant)
  - build/perturb.py, build/eval_external.py (Phase-3 robustness + external-tool comparison)
  - build/run_phase2.py (batch driver), build/env_setup.sh (Ubuntu/WSL toolchain install)

## Mission (in order)
1. Toolchain: `bash build/env_setup.sh`, then set Neo4j password to 123.
2. SMOKE TEST on ONE sample (build/SMOKE_TEST.md): build tutorial/example E-CPG, import to Neo4j,
   `cd tutorial && python main.py -1 example -vt 9` (expect "find N taint path"), then
   `python smoke_slice.py -1 example -vt 9` (expect >=1 slice + a hybrid record).
3. FIX integration points against the LIVE graph (the reason a human/agent is needed here):
   - backward_slice.py `# VERIFY` marks (match_relationship signature, fig_step
     get_toplevel_file_first_statement, get_ast_root_node returning a method's class,
     find_cg_call_nodes on get_node_itself(funcid)); see SMOKE_TEST.md step 7.
   - run_phase2.py `# ADJUST` marks (Parser.php output filenames, neo4j-admin-import.sh args,
     ports). Make `python build/run_phase2.py --limit 1` write rows to build/ft_dataset.jsonl.
4. Batch: `python build/run_phase2.py --split test` (resumable) -> build/ft_dataset.jsonl,
   emitting 3 variants/seed (cross-module / intra-file / no-slice).
5. Train+eval (GPU): `python build/qlora_train_eval.py --data build/ft_dataset.jsonl
   --model Qwen/Qwen2.5-Coder-7B-Instruct`. No local GPU -> hand ft_dataset.jsonl to a cloud GPU.

## Acceptance
Cross-module variant must beat intra-file and no-slice on F1 and PR-AUC (qlora_train_eval.py
prints per-variant/per-CWE). The slicer's crosses_include/crosses_inherit is also the E-CPG
confirmation that closes the dataset's `heuristic_pending_ecpg` labels — compare it to each
sample's meta.json boundary_type.

## Notes
- Run from the repo root with `. .venv/bin/activate` (except main.py / smoke_slice.py which run
  from tutorial/). The driver git-clones each repo -> needs internet.
- build/PACKAGE_INDEX.md describes the *zip package* layout (phase2/, scripts/) — ignore its
  paths; in THIS repo the code lives at api-framework/apis/ and build/ as listed above.
- Not in the repo (regenerate if needed): build/packagist/ (re-download OSV all.zip to re-harvest),
  the built zip/tarball, neo4j install, .venv.
