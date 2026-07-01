#!/usr/bin/env bash
# Stop eval agents on remote/local host without pkill self-match.
set -euo pipefail
for sig in TERM TERM KILL; do
  pgrep -f '/home/hct/ma3/eval/orchestrator/run_all_eval' >/dev/null && pkill -$sig -f '/home/hct/ma3/eval/orchestrator/run_all_eval' || true
  pgrep -f '/home/hct/ma3/eval/orchestrator/run_eval.sh --scenario' >/dev/null && pkill -$sig -f '/home/hct/ma3/eval/orchestrator/run_eval.sh --scenario' || true
  pgrep -f '/home/hct/ma3/eval/scripts/watchdog.sh' >/dev/null && pkill -$sig -f '/home/hct/ma3/eval/scripts/watchdog.sh' || true
  sleep 1
done
echo "eval agents stopped"
