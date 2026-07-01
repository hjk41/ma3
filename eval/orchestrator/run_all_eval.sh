#!/usr/bin/env bash
# Run full eval matrix (or subset). Secrets from eval/secrets/*.env only.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH="$ROOT/orchestrator/run_eval.sh"
MAP="$ROOT/orchestrator/scenarios.json"

AGENTS_ONLY=""
SCENARIOS_ONLY=""
DRY_RUN=0
RESUME=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agents) AGENTS_ONLY="$2"; shift 2 ;;
    --scenarios) SCENARIOS_ONLY="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --resume) RESUME=1; shift ;;
    *) echo "unknown: $1"; exit 1 ;;
  esac
done

python3 - <<'PY' "$MAP" "$AGENTS_ONLY" "$SCENARIOS_ONLY"
import json, subprocess, sys
cfg = json.load(open(sys.argv[1]))
agents_filter = sys.argv[2].split(",") if sys.argv[2] else None
scenarios_filter = sys.argv[3].split(",") if sys.argv[3] else None
order = cfg["agent_order"]
runs = []
for item in cfg["rotation"]:
    sid = item["id"]
    if scenarios_filter and sid not in scenarios_filter:
        continue
    first = item["first"]
    idx = order.index(first)
    seq = [order[(idx + i) % 3] for i in range(3)]
    for r, agent in enumerate(seq, start=1):
        if agents_filter and agent not in agents_filter:
            continue
        runs.append((sid, agent, r))
for sid, agent, r in runs:
    print(f"{sid}\t{agent}\t{r}")
PY

while IFS=$'\t' read -r sid agent round; do
  [[ -z "$sid" ]] && continue
  RUN_ID="eval-${sid}-${agent}-r${round}"
  RESULT_FILE="$ROOT/results/${RUN_ID}.json"
  if [[ "$RESUME" -eq 1 && -f "$RESULT_FILE" ]]; then
    if python3 - <<PY "$RESULT_FILE"
import json, sys
d = json.load(open(sys.argv[1]))
# Skip successful live runs; retry failed ones
if d.get("verify_pass") and d.get("duration_s", 0) >= 10:
    sys.exit(0)
sys.exit(1)
PY
    then
      echo "SKIP (done): $RUN_ID"
      continue
    fi
  fi
  echo "======== $sid / $agent / round $round ========"
  ARGS=(--scenario "$sid" --agent "$agent" --round "$round")
  [[ "$DRY_RUN" -eq 1 ]] && ARGS+=(--dry-run)
  bash "$ORCH" "${ARGS[@]}" || echo "FAILED: $sid $agent r$round" >&2
done < <(python3 - "$MAP" "$AGENTS_ONLY" "$SCENARIOS_ONLY" <<'PY'
import json, sys
cfg = json.load(open(sys.argv[1]))
agents_filter = sys.argv[2].split(",") if len(sys.argv) > 2 and sys.argv[2] else None
scenarios_filter = sys.argv[3].split(",") if len(sys.argv) > 3 and sys.argv[3] else None
order = cfg["agent_order"]
for item in cfg["rotation"]:
    sid = item["id"]
    if scenarios_filter and sid not in scenarios_filter:
        continue
    first = item["first"]
    idx = order.index(first)
    seq = [order[(idx + i) % 3] for i in range(3)]
    for r, agent in enumerate(seq, start=1):
        if agents_filter and agent not in agents_filter:
            continue
        print(f"{sid}\t{agent}\t{r}")
PY
)
