#!/usr/bin/env bash
# Auto-resume the Phase-2 batch (build/run_phase2.py --split test) after a VM reboot.
# Installed via `crontab -e` as an @reboot entry. Safe to run even if the batch is already
# running (checks for an existing process first) or already finished (script just exits quietly
# once run_phase2.py's own todo list is empty).
set -uo pipefail
ROOT="/home/kali/thesis/Master-Thesis"
LOG="$ROOT/build/run_phase2_batch.log"

# give the system a bit to settle (network, disk) right after boot
sleep 30

if pgrep -f "build/run_phase2.py" >/dev/null 2>&1; then
    echo "[resume_after_reboot] already running, nothing to do" >> "$LOG"
    exit 0
fi

echo "[resume_after_reboot] $(date): reboot detected, resuming batch" >> "$LOG"

# a reboot mid-import can leave a half-built Neo4j dir / stray CSVs from the interrupted sample
rm -f "$ROOT"/phpjoy/nodes.csv "$ROOT"/phpjoy/rels.csv "$ROOT"/phpjoy/predefined.csv \
      "$ROOT"/phpjoy/cpg_edges.csv "$ROOT"/phpjoy/fake_nodes.csv "$ROOT"/phpjoy/fake_rels.csv \
      "$ROOT"/phpjoy/import.report
rm -rf "$ROOT/example"
rm -rf /tmp/p2_* 2>/dev/null

cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate
nohup python build/run_phase2.py --split test >> "$LOG" 2>&1 &
disown
echo "[resume_after_reboot] relaunched, pid $!" >> "$LOG"
