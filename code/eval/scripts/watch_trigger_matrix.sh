#!/usr/bin/env bash
# Append matrix progress every 2 minutes until runner exits.
set -uo pipefail
PROGRESS="/home/hct/ma3/code/eval/results/trigger/progress.log"
while pgrep -f "run_trigger_parallel_matrix.py" >/dev/null 2>&1 || pgrep -f "run_full_trigger_matrix.sh" >/dev/null 2>&1; do
  python3 "$EVAL_ROOT/scripts/snapshot_trigger_progress.py"
  sleep 120
done
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) matrix runner exited" >>"$PROGRESS"
