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
import argparse, json, os, shutil, signal, subprocess, sys, time, tempfile
from pathlib import Path

PIPELINE_TIMEOUT_S = 600    # wall-clock budget for run_pipeline() per checkout (vuln/fixed)
JVM_HEAP_MB = 2000          # max heap for phpast2cpg.jar (default ~950MB OOM-ed on big repos;
                            # kept under total RAM so the OS OOM-killer doesn't fire instead)

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
    # Confirmed on the live toolchain: Parser.php writes nodes.csv/rels.csv/predefined.csv
    # into PHPJOY cwd. phpast2cpg.jar needs the exact args from phpjoy/phpast2cpg.sh
    # (-m strict -p predefined.csv) to resolve built-in/CHG call mappings; it then emits
    # cpg_edges.csv/fake_nodes.csv/fake_rels.csv, which neo4j-admin-import.sh expects.
    sh(["php", "php2ast/src/Parser.php", str(project_dir)], cwd=PHPJOY)
    # -Xmx: the JVM default max heap is ~1/4 of RAM (~950MB on this 3.9GB box), which
    # OOM-ed on every large repo (was the single biggest batch failure cause). Neo4j is
    # stopped while this runs, so the headroom is available to the CPG builder.
    sh(["java", f"-Xmx{JVM_HEAP_MB}m", "-jar", "phpast2cpg.jar", "-n", "nodes.csv", "-e", "rels.csv",
        "-m", "strict", "-p", "predefined.csv"], cwd=PHPJOY)


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


class PipelineTimeout(BaseException):
    """Deliberately NOT an Exception subclass: backward_slice.py has several broad
    `except Exception:` blocks (defensive against live-graph API mismatches) that would
    otherwise silently swallow this signal-raised timeout instead of letting it propagate."""
    pass


def _alarm_handler(signum, frame):
    raise PipelineTimeout(f"run_pipeline exceeded {PIPELINE_TIMEOUT_S}s")


def run_pipeline(cwe, sample_id, split, out_fp):
    from apis.analysis_framework import AnalysisFramework
    from apis.cache.thread_pool import BasicCacheGraph
    from apis.linearize import build_ft_dataset
    config = json.load(open(TUT / "neo4j_configure_map.json"))[DB]
    af = AnalysisFramework.from_dict(config, cache_graph=BasicCacheGraph())
    vt = CWE_TO_VT.get(cwe, 1)
    # A minority of real samples trigger a pathologically expensive Cypher query (observed:
    # an unbounded variable-length PARENT_OF path over a huge subtree in a large codebase like
    # magento/magento2) that can block indefinitely with no exception ever raised. The `sh()`
    # subprocess calls (git/php/java) already have a timeout, but this pure-Python traversal
    # doesn't -- bound it so one bad sample can't stall the whole batch forever.
    old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(PIPELINE_TIMEOUT_S)
    try:
        return build_ft_dataset(af, vt, cwe, sample_id, split, out_fp)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


class OutOfScope(Exception):
    """Sample deliberately excluded a-priori by the small/medium-project size gate -- NOT a
    failure. Recorded separately so 'declared out of scope (large project)' is distinct from
    'crashed on this hardware'. See build/THREATS_TO_VALIDITY.md §3 (scope decision)."""
    pass


def _php_source_kb(root: Path) -> int:
    """Total size (KB) of .php source under a checkout -- a cheap a-priori proxy for E-CPG
    build cost, measured before the expensive parse so large repos are skipped, not OOM-ed."""
    total = 0
    for p in root.rglob("*.php"):
        try:
            total += p.stat().st_size
        except OSError:
            pass
    return total // 1024


def process(sample, split, out_fp, max_php_kb=0):
    repo, sha, cwe, sid = sample["repo"], sample["fix_commit"], sample["cwe"], sample["id"]
    for want, tag in ((f"{sha}^1", "vuln"), (sha, "fixed")):
        work = Path(tempfile.mkdtemp(prefix=f"p2_{sid}_{tag}_"))
        try:
            print(f"[{sid}] {tag}: {repo}@{want}")
            prepare_checkout(repo, sha, want, work)
            if max_php_kb and tag == "vuln":           # small/medium scope gate (a-priori)
                kb = _php_source_kb(work)
                if kb > max_php_kb:
                    raise OutOfScope(f"{kb} KB PHP > {max_php_kb} KB gate (large project)")
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
    ap.add_argument("--attempts", default=str(ROOT / "build" / "phase2_attempts.json"),
                    help="per-sample failure counter, used to retire permanent blockers")
    ap.add_argument("--max-attempts", type=int, default=3,
                    help="stop retrying a sample after this many failures (0 = never retire)")
    ap.add_argument("--done-flag", default=str(ROOT / "build" / "phase2_complete.json"),
                    help="sentinel written when no reachable samples remain")
    ap.add_argument("--max-php-kb", type=int, default=0,
                    help="small/medium scope gate (thesis scope = small/medium PHP projects): "
                         "skip a sample whose checkout has more than this many KB of .php source, "
                         "measured BEFORE the E-CPG build so large repos are excluded by design "
                         "rather than after they OOM. 0 = no gate. Tune per hardware.")
    ap.add_argument("--scope-file", default=str(ROOT / "build" / "phase2_out_of_scope.json"),
                    help="records sample ids excluded a-priori by --max-php-kb")
    ap.add_argument("--split", choices=["train", "val", "test", "all"], default="all")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # utf-8-sig: index.json/splits.json were generated by PowerShell (.ps1 scripts) and
    # carry a UTF-8 BOM that plain utf-8 decoding rejects.
    index = json.load(open(DS / "index.json", encoding="utf-8-sig"))
    splits = json.load(open(DS / "splits.json", encoding="utf-8-sig"))["splits"]
    id2split = {i: s for s in ("train", "val", "test") for i in splits[s]["ids"]}
    if args.split != "all":
        index = [s for s in index if id2split.get(s["id"]) == args.split]

    done = set(json.load(open(args.state))) if os.path.exists(args.state) else set()

    # Persistent per-sample attempt counter. Some samples can never succeed on this hardware
    # (e.g. magento/magento2 OOMs phpast2cpg.jar every time) but every restart would re-clone
    # and re-parse them from scratch -- one blocker burned ~20min per restart, 40 times over.
    # Retire a sample after MAX_ATTEMPTS so the batch spends its time on reachable work.
    attempts = json.load(open(args.attempts)) if os.path.exists(args.attempts) else {}
    retired = ({i for i, n in attempts.items() if n >= args.max_attempts}
               if args.max_attempts > 0 else set())

    out_of_scope = (set(json.load(open(args.scope_file)))
                    if os.path.exists(args.scope_file) else set())
    todo = [s for s in index if s["id"] not in done and s["id"] not in retired
            and s["id"] not in out_of_scope]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(todo)} sample(s) to process (split={args.split}, already done={len(done)}, "
          f"retired after {args.max_attempts} failed attempts={len(retired)}, "
          f"out-of-scope (>{args.max_php_kb}KB)={len(out_of_scope)})")

    if args.dry_run:
        for s in todo[:20]:
            print(f"  would process {s['id']} {s['cwe']} {s['repo']}@{s['fix_commit']} "
                  f"vt={CWE_TO_VT.get(s['cwe'],1)} split={id2split.get(s['id'])}")
        return

    with open(args.out, "a", encoding="utf-8") as out_fp:
        for s in todo:
            try:
                process(s, id2split.get(s["id"], "train"), out_fp, args.max_php_kb)
                out_fp.flush()
                done.add(s["id"])
                json.dump(sorted(done), open(args.state, "w"))
            except OutOfScope as e:                       # declared out of scope, not a failure
                out_of_scope.add(s["id"])
                json.dump(sorted(out_of_scope), open(args.scope_file, "w"))
                print(f"   -- {s['id']} out of scope: {e}", flush=True)
            except (Exception, PipelineTimeout) as e:     # keep going; one bad repo shouldn't stop the batch
                attempts[s["id"]] = attempts.get(s["id"], 0) + 1
                json.dump(attempts, open(args.attempts, "w"), indent=0, sort_keys=True)
                retire = " (RETIRED, will not retry)" if attempts[s["id"]] >= args.max_attempts else ""
                print(f"   !! {s['id']} failed (attempt {attempts[s['id']]}){retire}: {e}",
                      flush=True)

    # Nothing reachable left? Drop a sentinel so the cron watchdog stops respawning us.
    # (It must not infer this from the log: that file is append-only across every run, so a
    # "done." line from an earlier pass would disable the watchdog forever.)
    remaining = [s for s in index
                 if s["id"] not in done
                 and not (args.max_attempts > 0 and attempts.get(s["id"], 0) >= args.max_attempts)]
    if remaining:
        print(f"stopping with {len(remaining)} sample(s) still pending -> {args.out}", flush=True)
    else:
        Path(args.done_flag).write_text(
            json.dumps({"done": len(done), "retired": len(retired | {
                i for i, n in attempts.items()
                if args.max_attempts > 0 and n >= args.max_attempts})}, indent=2))
        print(f"ALL DONE. ft_dataset -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
