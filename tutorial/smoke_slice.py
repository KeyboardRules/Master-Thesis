"""
Smoke test for the backward slicer (B2) + hybrid linearizer (B3) on the tutorial example.

Run from the `tutorial/` directory AFTER the example E-CPG is imported into Neo4j and the DB
is started (see build/SMOKE_TEST.md steps 1-3). Mirrors tutorial/main.py's framework setup.

    python ./smoke_slice.py -1 example -vt 9        # 9 = SQL_INJECTION

Success = it prints >= 1 slice with a verdict/boundary and a readable hybrid record, and
writes smoke_ft.jsonl. This proves the whole B2->B3 chain runs on a live E-CPG before you
scale to the 977-sample dataset.
"""
import argparse, json, sys

sys.path.append("../api-framework")
from apis.analysis_framework import AnalysisFramework
from apis.cache.thread_pool import BasicCacheGraph
from apis.backward_slice import run_slicing
from apis.linearize import linearize_slice, build_ft_dataset
from apis.vuln_model import VULN_TYPE_ID_TO_STRING

ap = argparse.ArgumentParser()
ap.add_argument("-1", "--map-key", dest="map_key", default="example")
ap.add_argument("-vt", "--vuln-type", dest="vuln_type", type=int, default=9)
ap.add_argument("--cwe", default="CWE-89")
args = ap.parse_args()

with open("neo4j_configure_map.json") as f:
    config = json.load(f)[args.map_key]

af = AnalysisFramework.from_dict(config, cache_graph=BasicCacheGraph())
print(f"[*] connected. vuln_type={args.vuln_type} ({VULN_TYPE_ID_TO_STRING.get(args.vuln_type)})")

slices = run_slicing(af, args.vuln_type)
print(f"[*] slicer returned {len(slices)} slice(s)")
for i, sl in enumerate(slices[:5]):
    print(f"  - slice {i}: verdict={sl.verdict} boundary={sl.boundary_type} "
          f"nodes={len(sl.nodes)} witness_len={len(sl.witness)} "
          f"include={sl.crosses_include} inherit={sl.crosses_inherit}")

if slices:
    print("\n===== hybrid linearization of slice 0 =====")
    print(linearize_slice(slices[0], af, args.cwe, args.vuln_type))

# tiny fine-tune-format sanity dump (single sample, split=train just for the smoke test)
with open("smoke_ft.jsonl", "w", encoding="utf-8") as out:
    n = build_ft_dataset(af, args.vuln_type, cwe=args.cwe,
                         sample_id="tutorial-example", split="train", out_fp=out)
print(f"\n[*] wrote {n} row(s) to smoke_ft.jsonl (3 variants x sinks)")
