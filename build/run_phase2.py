#!/usr/bin/env python3
"""
Phase-2 batch driver: dataset -> ft_dataset.jsonl (Linux/WSL, needs the E-CPG toolchain).

For every dataset sample it does, for BOTH the vulnerable (fix^1) and fixed (fix) checkout,
exactly what build/SMOKE_TEST.md §8 does by hand:
    git checkout  ->  build E-CPG (Parser.php + phpast2cpg.jar)  ->  import+start Neo4j
    ->  run_slicing + build_ft_dataset  ->  stop Neo4j  ->  clean.
Positives come from fix^1, negatives from fix. Resumable via a checkpoint file.

    cd phpjoy_release && . .venv/bin/activate
    python build/run_phase2.py --limit 1          # validate on one sample FIRST
    python build/run_phase2.py --split test        # then a subset / everything
    python build/run_phase2.py --dry-run           # print the plan only

IMPORTANT: run --limit 1 first and fix any `# ADJUST` call to match your toolchain (the exact
Parser.php output filenames, the neo4j-admin-import.sh interface, and the `# VERIFY` marks in
apis/backward_slice.py). Only then batch. This script is authored offline and NOT executed here.
"""
import argparse, json, os, shutil, subprocess, sys, time, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent            # phpjoy_release/
PHPJOY = ROOT / "phpjoy"
TUT = ROOT / "tutorial"
DS = ROOT / "build" / "dataset_xmodule"
sys.path.append(str(ROOT / "api-framework"))

# CWE -> PHPJoy vuln_type id (invert VULN_TYPE_ID_TO_STRING). Unmapped -> ALL_SINK(1).
CWE_TO_VT = {
    "CWE-79": 10, "CWE-89": 9, "CWE-78": 4, "CWE-94": 3, "CWE-95": 3, "CWE-22": 5, "CWE-73": 5,
    "CWE-98": 7, "CWE-434": 6, "CWE-502": 8, "CWE-918": 11, "CWE-601": 13, "CWE-74": 1,
    "CWE-611": 1, "CWE-1336": 1, "CWE-90": 1,
}
DB, BOLT, HTTP = "example", 17473, 17474


def sh(cmd, cwd=None, check=True, timeout=1800):
    print("  $", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, cwd=cwd, check=check, timeout=timeout)


def prepare_checkout(repo, sha, want, workdir):
    """Shallow-fetch <sha> + parent, check out `want` (sha or sha^1) into workdir."""
    workdir.mkdir(parents=True, exist_ok=True)
    sh(["git", "init", "-q"], cwd=workdir)
    sh(["git", "remote", "add", "origin", f"https://github.com/{repo}.git"], cwd=workdir, check=False)
    sh(["git", "fetch", "--depth", "2", "origin", sha], cwd=workdir)
    sh(["git", "checkout", "-q", want], cwd=workdir)


def build_ecpg(project_dir):
    # ADJUST: confirm Parser.php writes nodes.csv/rels.csv into PHPJOY cwd (per README).
    sh(["php", "php2ast/src/Parser.php", str(project_dir)], cwd=PHPJOY)
    sh(["java", "-jar", "phpast2cpg.jar", "-n", "nodes.csv", "-e", "rels.csv"], cwd=PHPJOY)


def neo4j(cmd):
    sh(["bash", str(ROOT / DB / "bin" / "neo4j"), cmd], cwd=ROOT, check=False)


def import_and_start():
    neo4j("stop")
    shutil.rmtree(ROOT / DB, ignore_errors=True)          # ADJUST: fresh db each import
    sh(["bash", "./neo4j-admin-import.sh", DB, str(BOLT), str(HTTP)], cwd=PHPJOY)  # ADJUST args
    neo4j("start")
    # wait for the http port
    for _ in range(60):
        try:
            import socket
            with socket.create_connection(("127.0.0.1", HTTP), timeout=1):
                return
        except OSError:
            time.sleep(2)
    raise TimeoutError("Neo4j did not come up")


def run_pipeline(cwe, sample_id, split, out_fp):
    from apis.analysis_framework import AnalysisFramework
    from apis.cache.thread_pool import BasicCacheGraph
    from apis.linearize import build_ft_dataset
    config = json.load(open(TUT / "neo4j_configure_map.json"))[DB]
    af = AnalysisFramework.from_dict(config, cache_graph=BasicCacheGraph())
    vt = CWE_TO_VT.get(cwe, 1)
    return build_ft_dataset(af, vt, cwe, sample_id, split, out_fp)


def process(sample, split, out_fp):
    repo, sha, cwe, sid = sample["repo"], sample["fix_commit"], sample["cwe"], sample["id"]
    for want, tag in ((f"{sha}^1", "vuln"), (sha, "fixed")):
        work = Path(tempfile.mkdtemp(prefix=f"p2_{sid}_{tag}_"))
        try:
            print(f"[{sid}] {tag}: {repo}@{want}")
            prepare_checkout(repo, sha, want, work)
            build_ecpg(work)
            import_and_start()
            n = run_pipeline(cwe, sid, split, out_fp)
            print(f"   -> {n} rows ({tag})")
        finally:
            neo4j("stop")
            shutil.rmtree(work, ignore_errors=True)
            for f in ("nodes.csv", "rels.csv", "cpg_edges.csv"):
                (PHPJOY / f).unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "build" / "ft_dataset.jsonl"))
    ap.add_argument("--state", default=str(ROOT / "build" / "phase2_state.json"))
    ap.add_argument("--split", choices=["train", "val", "test", "all"], default="all")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    index = json.load(open(DS / "index.json"))
    splits = json.load(open(DS / "splits.json"))["splits"]
    id2split = {i: s for s in ("train", "val", "test") for i in splits[s]["ids"]}
    if args.split != "all":
        index = [s for s in index if id2split.get(s["id"]) == args.split]

    done = set(json.load(open(args.state))) if os.path.exists(args.state) else set()
    todo = [s for s in index if s["id"] not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(todo)} sample(s) to process (split={args.split}, already done={len(done)})")

    if args.dry_run:
        for s in todo[:20]:
            print(f"  would process {s['id']} {s['cwe']} {s['repo']}@{s['fix_commit']} "
                  f"vt={CWE_TO_VT.get(s['cwe'],1)} split={id2split.get(s['id'])}")
        return

    with open(args.out, "a", encoding="utf-8") as out_fp:
        for s in todo:
            try:
                process(s, id2split.get(s["id"], "train"), out_fp)
                out_fp.flush()
                done.add(s["id"])
                json.dump(sorted(done), open(args.state, "w"))
            except Exception as e:                        # keep going; one bad repo shouldn't stop the batch
                print(f"   !! {s['id']} failed: {e}")
    print(f"done. ft_dataset -> {args.out}")


if __name__ == "__main__":
    main()
