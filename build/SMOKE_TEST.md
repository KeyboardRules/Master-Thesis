# End-to-End Smoke Test — de-risk the toolchain on ONE sample

Goal: prove the whole chain **E-CPG build → Neo4j → backward slice (B2) → hybrid linearize
(B3)** runs on a live graph *before* investing in the 977-sample build or a GPU. Uses the
artifact's bundled `tutorial/example`. Budget ~30–60 min on a fresh machine.

**Success = ** step 4 prints `find N taint path` (N≥1), step 5 prints `≥1 slice` with a
verdict/boundary, and step 6 prints a readable `[SLICE]/[EDGES]` record + writes `smoke_ft.jsonl`.

## 0. Prerequisites (versions per the main PHPJoy README)

| Tool | Version | Check |
|---|---|---|
| Python | ≥ 3.9 | `python --version` |
| PHP | ≥ 8.0 | `php -v` |
| Java | 11 | `java -version` |
| Neo4j | community-4.4.4 | in project root |
| composer, uv | any | `composer -V`, `uv --version` |

Linux or WSL recommended — the import/start scripts (`neo4j-admin-import.sh`, `neo4j start`)
are bash. On Windows use WSL2.

## 1. Build the example E-CPG

Fastest path — reuse the **pre-built** graph the artifact ships:
```bash
cd phpjoy
cp ../tutorial/example_cpgs/* .        # nodes.csv, rels.csv, cpg_edges.csv, ...
```
Or rebuild from source to test the parser too:
```bash
cd phpjoy/php2ast/src && composer install && cd ../..
php ./php2ast/src/Parser.php ../tutorial/example      # -> nodes.csv, rels.csv
java -jar phpast2cpg.jar -n nodes.csv -e rels.csv     # -> E-CPG edges
```

## 2. Import into Neo4j and start it
```bash
cd phpjoy
bash ./neo4j-admin-import example 17473 17474         # dbname bolt http
../example/bin/neo4j start                             # wait until "Started"
```

## 3. Configure the DB connection

Edit `tutorial/neo4j_configure_map.json` so the `example` block matches (port 17474, the
password you set on first Neo4j login):
```json
{ "example": { "NEO4J_HOST":"127.0.0.1","NEO4J_PORT":17474,"NEO4J_USERNAME":"neo4j",
               "NEO4J_PASSWORD":"123","NEO4J_DATABASE":"neo4j","NEO4J_PROTOCOL":"http" } }
```

## 4. Validate PHPJoy core (forward analysis) — proves graph + framework work
```bash
cd tutorial
uv venv && . .venv/bin/activate && uv sync
python ./main.py -1 example -vt 9 -o output            # 9 = SQL_INJECTION
```
Expect a log line `find N taint path for vuln_type 9(SQL Injection)` with **N ≥ 1** and an
`output-9.json`. If this fails, fix the toolchain here before touching the slicer.

## 5 + 6. Validate the NEW backward slicer (B2) + linearizer (B3)

`tutorial/smoke_slice.py` is provided. From the same activated venv:
```bash
python ./smoke_slice.py -1 example -vt 9 --cwe CWE-89
```
Expect:
```
[*] connected. vuln_type=9 (SQL Injection)
[*] slicer returned K slice(s)
  - slice 0: verdict=VULNERABLE boundary=include nodes=.. witness_len=.. include=True inherit=False
===== hybrid linearization of slice 0 =====
<META> cwe=CWE-89 boundary=include vartrace=⟦t⟧$...
[SLICE] ... [INCLUDE→ ...] ... [SNK] ... [/SLICE]
[EDGES] n0 -REACHES($..)-> n1 ...
[*] wrote M row(s) to smoke_ft.jsonl
```
The tutorial example is include-based, so at least one slice should show `boundary=include`.

## 7. VERIFY checklist (the `# VERIFY` marks in the code)

Confirm each live-graph assumption; if a name differs, adjust the one call and re-run step 6.

| Where | Assumption to confirm | If wrong |
|---|---|---|
| `backward_slice._backward_inherit` | `match_relationship(nodes=(class_node,None), r_type=EXTENDS_EDGE)` returns the parent-class rel | use the py2neo form your `basic_step.match_relationship` expects (check `steps/basic_step.py`) |
| `backward_slice._backward_include` | `fig_step.get_toplevel_file_first_statement(f)` gives the included file's toplevel stmt | swap for `fig_step.get_include_map` / `get_toplevel_file...` variant present |
| `backward_slice._backward_inherit` | `get_ast_root_node(method_node)` yields the **class** node | resolve class via `filter_ast_child_nodes(..., [TYPE_CLASS])` upward |
| `backward_slice._backward_cg` | `get_node_itself(funcid)` is the function **decl** node accepted by `find_cg_call_nodes` | map funcid→decl via `basic_step.match(**{NODE_INDEX:funcid})` |
| `linearize._unit` | `fig_step.get_belong_file(node)` returns a file label | use `get_node_from_file_system` |

Tip: drop into a REPL and poke one node:
```python
from apis.analysis_framework import AnalysisFramework; import json
af = AnalysisFramework.from_dict(json.load(open("neo4j_configure_map.json"))["example"])
n = af.neo4j_graph.nodes.match(type="AST_CALL").first()
print(af.fig_step.get_belong_file(n), af.find_pdg_def_nodes(n))
```

## 8. Scale-up path (after the smoke test is green)

For each dataset sample `build/dataset_xmodule/<CWE>/<GHSA-id>/` (`meta.json` has `repo`,
`fix_commit`, `cwe`, `boundary_type`, and its split is in `dataset_xmodule/splits.json`):

1. Two graphs per sample: check out `repo@<fix_commit>^1` (→ **positive**, vulnerable) and
   `repo@<fix_commit>` (→ **negative**, fixed); build+import an E-CPG for each into its own
   Neo4j db (reuse steps 1–2 with a per-sample dbname/port).
2. Map `cwe`→`vuln_type` int (invert `vuln_model.VULN_TYPE_ID_TO_STRING`), look up the sample's
   `split`, then:
   ```python
   from apis.linearize import build_ft_dataset
   with open("ft_dataset.jsonl","a",encoding="utf-8") as out:
       build_ft_dataset(af_vuln, vuln_type, cwe, sample_id, split, out)   # positives
       build_ft_dataset(af_fixed, vuln_type, cwe, sample_id, split, out)  # negatives
   ```
3. When `ft_dataset.jsonl` is complete, run `build/qlora_train_eval.py` (needs GPU).

Automate step 1–2 as a loop over `index.json`; run a handful of samples first, eyeball their
records, then batch. Because the slicer also emits `crosses_include/inherit`, compare those
against each sample's heuristic `boundary_type` — agreement is your E-CPG confirmation that
closes the `heuristic_pending_ecpg` label.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `composer install` fails | match PHP 8 CLI; `composer install --ignore-platform-reqs` as last resort |
| Neo4j auth error | first `../example/bin/neo4j start`, set password in browser (`:7474`-style http port), put it in the JSON |
| `find 0 taint path` | wrong `-vt`, empty graph (re-import), or ports mismatch with the JSON |
| py2neo connection refused | Neo4j not started / wrong `NEO4J_PORT` (http 17474 vs bolt 17473) |
| slicer returns 0 slices but forward found paths | a `# VERIFY` method name differs — work through the step-7 table |
