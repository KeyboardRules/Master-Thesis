#!/usr/bin/env bash
# Watchdog for the Phase-2 batch (build/run_phase2.py --split test).
#
# Installed in crontab twice:
#   @reboot            -> restart after the VM reboots
#   */10 * * * *       -> restart if the batch died for ANY other reason
#
# The */10 entry matters because a VM reboot is not the only thing that kills the run: the
# batch is launched from a Claude Code shell, so a desktop-app/CLI restart tears down the
# process group too (that is what stopped it on 2026-09-11, with no reboot involved).
#
# Safe to run at any time: it exits immediately if the batch is already up, and
# run_phase2.py itself resumes from build/phase2_state.json, so nothing is redone.
set -uo pipefail
ROOT="/home/kali/thesis/Master-Thesis"
LOG="$ROOT/build/run_phase2_batch.log"

# only the @reboot invocation needs to wait for the system to settle
if [ "${1:-}" = "--boot" ]; then
    sleep 30
fi

# Match the real interpreter process only. A plain `pgrep -f run_phase2.py` also matches any
# shell whose command line merely mentions the script (including this script's own caller),
# which made the watchdog think the batch was up when it was not.
is_running() {
    pgrep -f "python[0-9.]* -u build/run_phase2\.py" | grep -qv "^$$\$"
}
if is_running; then
    exit 0                      # already running: stay quiet, cron runs this every 10 min
fi

# Don't respawn forever once the split is finished. This must be a real state sentinel, not
# a log grep: the log is append-only across runs, so a "done." line from an earlier pass
# would disable the watchdog permanently (it did).
if [ -f "$ROOT/build/phase2_complete.json" ]; then
    exit 0
fi

echo "[watchdog] $(date): batch not running, (re)starting" >> "$LOG"

# A kill mid-pipeline can leave a half-built Neo4j dir, a stray server, and stale CSVs.
pkill -f "org.neo4j.server.CommunityEntryPoint" >/dev/null 2>&1
sleep 2
rm -f "$ROOT"/phpjoy/nodes.csv "$ROOT"/phpjoy/rels.csv "$ROOT"/phpjoy/predefined.csv \
      "$ROOT"/phpjoy/cpg_edges.csv "$ROOT"/phpjoy/fake_nodes.csv "$ROOT"/phpjoy/fake_rels.csv \
      "$ROOT"/phpjoy/import.report
rm -rf "$ROOT/example"
rm -rf /tmp/p2_* 2>/dev/null

cd "$ROOT" || exit 1
# setsid: fully detach into a new session so the run survives the parent shell / app restart.
# python -u: unbuffered, so the "!! <id> failed" lines reach the log instead of dying in a
# buffer when the process is killed (that is why the failure history was unreadable before).
setsid nohup "$ROOT/.venv/bin/python" -u build/run_phase2.py --split test >> "$LOG" 2>&1 &
echo "[watchdog] started pid $!" >> "$LOG"
