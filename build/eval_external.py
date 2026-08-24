#!/usr/bin/env python
"""
Sample-level comparison of prior detectors against the cross-module dataset (Phase-3, §3).

26-week-plan comparison targets: RealVul, VulEye, DeepTective, and PHPJoy's own static
analysis. (NAVEX / TChecker are Phase-2 source/sink cross-check tools, not Phase-3 targets.)
This adapter is tool-agnostic: feed each system's output as the normalized findings.jsonl
below; `parse_progpilot` is one example converter you can adapt per tool.

External tools emit *findings*, we have *labeled samples*. This aligns them at the CVE/sample
level on the held-out test split so precision/recall/F1 are comparable to the LLM classifier.

INPUT
  --dataset  dataset_xmodule/            (index.json + splits.json)
  --findings findings.jsonl              normalized tool output, one finding per line:
       {"tool":"TChecker","repo":"owner/name","commit":"<fix_sha>",
        "version":"vuln"|"fixed","file":"htdocs/.../x.php","line":123}
     You convert each tool's raw output into this schema once (a Progpilot parser is included
     as `parse_progpilot`). `version` = which checkout the tool ran on (fix-commit parent vs
     fix commit). `line` is optional (file-level matching is used).

SCORING (per tool, restricted to --split)
  positive sample (vuln)  = detected  if the tool has a version=="vuln" finding on one of the
                            sample's changed_php files (same repo+commit)
  negative sample (fixed) = false pos if the tool has a version=="fixed" finding on such a file
  precision=TP/(TP+FP)  recall=TP/(TP+FN)  F1  -- overall and per CWE.

Run: python eval_external.py --dataset dataset_xmodule --findings findings.jsonl --split test
"""
import argparse, json, os
from collections import defaultdict


# ---- optional: convert a Progpilot JSON report into the normalized findings schema ---------
def parse_progpilot(report_json_path, repo, commit, version):
    """Progpilot `--output` JSON is a list of {sink_file, sink_line, ...}. Adapt as needed."""
    data = json.load(open(report_json_path, encoding="utf-8"))
    out = []
    for f in data:
        out.append({"tool": "Progpilot", "repo": repo, "commit": commit, "version": version,
                    "file": f.get("sink_file") or f.get("file"), "line": f.get("sink_line")})
    return out


# ---- matching ------------------------------------------------------------------------------
def _file_match(sample_file, finding_file):
    if not finding_file:
        return False
    a, b = sample_file.replace("\\", "/"), str(finding_file).replace("\\", "/")
    return a == b or a.endswith(b) or b.endswith(a) or os.path.basename(a) == os.path.basename(b)


def _hits(findings_index, repo, commit, version, changed_php):
    for f in findings_index.get((repo, commit, version), []):
        if any(_file_match(cf, f.get("file")) for cf in changed_php):
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset_xmodule")
    ap.add_argument("--findings", required=True)
    ap.add_argument("--split", default="test", choices=["train", "val", "test", "all"])
    args = ap.parse_args()

    index = json.load(open(os.path.join(args.dataset, "index.json"), encoding="utf-8"))
    by_id = {s["id"]: s for s in index}
    if args.split != "all":
        splits = json.load(open(os.path.join(args.dataset, "splits.json"), encoding="utf-8"))
        keep = set(splits["splits"][args.split]["ids"])
        index = [s for s in index if s["id"] in keep]
    print(f"scoring {len(index)} samples on split={args.split}")

    # index findings by (repo, commit, version) and by tool
    tools = set()
    fidx = defaultdict(list)
    for line in open(args.findings, encoding="utf-8"):
        if not line.strip():
            continue
        f = json.loads(line)
        tools.add(f["tool"])
        fidx[(f["tool"], f["repo"], f["commit"], f["version"])].append(f)

    def tool_index(tool):
        return {k[1:]: v for k, v in fidx.items() if k[0] == tool}   # (repo,commit,version)->[f]

    def prf(tp, fp, fn):
        p = tp / (tp + fp) if tp + fp else float("nan")
        r = tp / (tp + fn) if tp + fn else float("nan")
        f1 = 2 * p * r / (p + r) if p and r and not (p != p or r != r) else float("nan")
        return round(p, 4), round(r, 4), round(f1, 4)

    print(f"\n{'tool':12s} {'CWE':10s} {'n':>4s} {'TP':>4s} {'FP':>4s} {'FN':>4s} "
          f"{'P':>7s} {'R':>7s} {'F1':>7s}")
    for tool in sorted(tools):
        fi = tool_index(tool)
        per = defaultdict(lambda: [0, 0, 0, 0])            # cwe -> [tp,fp,fn,n]
        overall = [0, 0, 0, 0]
        for s in index:
            det = _hits(fi, s["repo"], s["fix_commit"], "vuln", s["changed_php"])
            fpos = _hits(fi, s["repo"], s["fix_commit"], "fixed", s["changed_php"])
            for acc in (per[s["cwe"]], overall):
                acc[3] += 1
                if det:
                    acc[0] += 1                            # TP
                else:
                    acc[2] += 1                            # FN
                if fpos:
                    acc[1] += 1                            # FP (flagged the patched file)
        for cwe in sorted(per):
            tp, fp, fn, n = per[cwe]
            p, r, f1 = prf(tp, fp, fn)
            print(f"{tool:12s} {cwe:10s} {n:>4d} {tp:>4d} {fp:>4d} {fn:>4d} "
                  f"{str(p):>7s} {str(r):>7s} {str(f1):>7s}")
        tp, fp, fn, n = overall
        p, r, f1 = prf(tp, fp, fn)
        print(f"{tool:12s} {'ALL':10s} {n:>4d} {tp:>4d} {fp:>4d} {fn:>4d} "
              f"{str(p):>7s} {str(r):>7s} {str(f1):>7s}")


if __name__ == "__main__":
    main()
