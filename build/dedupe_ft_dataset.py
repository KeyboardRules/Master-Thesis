#!/usr/bin/env python3
"""
De-duplicate build/ft_dataset.jsonl before fine-tuning.

Two sources of duplicate rows accumulate during a long `run_phase2.py` batch:

1. **Retried partial samples.** `process()` runs two checkouts (vuln, then fixed). If the
   second one fails (timeout / phpast2cpg crash / OOM), the exception escapes before the
   sample is recorded in `phase2_state.json`, so the sample is retried on the next run --
   but the rows the *first* checkout already wrote and flushed stay in the file. The retry
   then writes them again.
2. **Byte-identical vuln/fixed renderings.** When a fix touches code outside the slice, the
   pre-fix and post-fix graphs linearize to exactly the same record with the same verdict,
   so the row carries no train/eval signal while being counted twice.

Both are removed by keying on the full row content. Rows are otherwise left untouched and
their original order is preserved (first occurrence wins).

    python build/dedupe_ft_dataset.py                      # writes ft_dataset.dedup.jsonl
    python build/dedupe_ft_dataset.py --in-place           # overwrites, keeps a .bak
    python build/dedupe_ft_dataset.py --report-only        # just print the stats
"""
import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IN = ROOT / "build" / "ft_dataset.jsonl"


def row_key(row: dict) -> tuple:
    """Identity of a training item: same seed, same rendering, same supervision."""
    return (row.get("id"), row.get("variant"), row.get("label"),
            row.get("prompt"), row.get("target"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DEFAULT_IN))
    ap.add_argument("--out", default=None)
    ap.add_argument("--in-place", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--state", default=str(ROOT / "build" / "phase2_state.json"))
    args = ap.parse_args()

    src = Path(args.data)
    rows, bad = [], 0
    with open(src, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1          # a row torn in half by a mid-write kill/reboot

    seen, kept = set(), []
    for r in rows:
        k = row_key(r)
        if k in seen:
            continue
        seen.add(k)
        kept.append(r)

    # Rows whose sample never completed both checkouts are partial: the vuln side may be
    # present without its matching fixed side. Report them so the imbalance is visible.
    try:
        done = set(json.load(open(args.state)))
    except (OSError, json.JSONDecodeError):
        done = set()
    ids = Counter(r["id"] for r in kept)
    partial_ids = sorted(i for i in ids if i not in done)
    partial_rows = sum(ids[i] for i in partial_ids)

    print(f"input rows          : {len(rows)}" + (f"  (+{bad} unparseable)" if bad else ""))
    print(f"after de-duplication: {len(kept)}   (removed {len(rows) - len(kept)})")
    print(f"distinct sample ids : {len(ids)}")
    print(f"incomplete samples  : {len(partial_ids)} ids / {partial_rows} rows "
          f"(present in data but not in phase2_state.json)")
    print("by variant          : " + ", ".join(
        f"{k}={v}" for k, v in sorted(Counter(r["variant"] for r in kept).items())))
    print("by label            : " + ", ".join(
        f"{k}={v}" for k, v in sorted(Counter(r["label"] for r in kept).items())))
    print("by boundary         : " + ", ".join(
        f"{k}={v}" for k, v in sorted(Counter(r["boundary"] for r in kept).items())))

    if args.report_only:
        return

    if args.in_place:
        shutil.copy2(src, src.with_suffix(".jsonl.bak"))
        dst = src
    else:
        dst = Path(args.out) if args.out else src.with_suffix(".dedup.jsonl")
    with open(dst, "w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r) + "\n")
    print(f"wrote -> {dst}")


if __name__ == "__main__":
    main()
