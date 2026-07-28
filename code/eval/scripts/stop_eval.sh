#!/usr/bin/env bash
# Stop eval agents on remote/local host without pkill self-match.
set -euo pipefail
EVAL_ROOT="${EVAL_ROOT:-$HOME/ma3/eval}"
for sig in TERM TERM KILL; do
  pgrep -f "$EVAL_ROOT/orchestrator/run_all_eval" >/dev/null && pkill -$sig -f "$EVAL_ROOT/orchestrator/run_all_eval" || true
  pgrep -f "$EVAL_ROOT/orchestrator/run_eval.sh --scenario" >/dev/null && pkill -$sig -f "$EVAL_ROOT/orchestrator/run_eval.sh --scenario" || true
  pgrep -f "$EVAL_ROOT/scripts/watchdog.sh" >/dev/null && pkill -$sig -f "$EVAL_ROOT/scripts/watchdog.sh" || true
  sleep 1
done
echo "eval agents stopped"
