#!/usr/bin/env bash
# Run full trigger experiment matrix: all arms × runtimes × scenarios.
set -euo pipefail

EVAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$EVAL_ROOT/scripts/load_secrets.sh"

ROUNDS="${TRIGGER_ROUNDS:-3}"
CSV="${TRIGGER_CSV:-$EVAL_ROOT/results/trigger/runs.csv}"
LOG="${TRIGGER_MATRIX_LOG:-$EVAL_ROOT/results/trigger/experiment-matrix.log}"
MANIFEST="$EVAL_ROOT/scenarios/trigger/manifest.json"
ARMS_JSON="$EVAL_ROOT/scenarios/trigger/arms.json"
SKIP_DONE="${TRIGGER_SKIP_DONE:-1}"
DRY_RUN="${TRIGGER_DRY_RUN:-0}"
PARALLEL_WORKERS="${TRIGGER_PARALLEL_WORKERS:-1}"

export MA3_KEY_REMOTE="${MA3_KEY_REMOTE:-${MA3_KEY_CURSOR_CLI:-}}"
if [[ -z "${MA3_KEY_REMOTE}" ]]; then
  echo "MA3_KEY_REMOTE or MA3_KEY_CURSOR_CLI required (no hardcoded default)" >&2
  exit 1
fi
export MA3_KEY_LOCAL="${MA3_KEY_LOCAL:-${MA3_DEV_API_KEY:-ma3dev}}"
export PATH="${HOME}/.local/bin:${HOME}/.npm-global/bin:${PATH}"

mkdir -p "$(dirname "$LOG")" "$(dirname "$CSV")"

ALL_ARMS=(
  A0-baseline
  A1-gate
  C0-skill
  C1-gate-skill
)
ALL_RUNTIMES=(cursor-agent claude codex)
ALL_SCENARIOS=(
  trigger-p1 trigger-p2 trigger-p3 trigger-p4 trigger-p5 trigger-p6
)

pick_scenarios() {
  python3 - <<'PY'
import json, os
manifest = json.load(open(os.environ["MANIFEST"]))
order = ["P1","P2","P4","P5","P6","P3"]
by_pid = {s["prompt_id"]: s["id"] for s in manifest["scenarios"]}
for pid in order:
    if pid in by_pid:
        print(by_pid[pid])
PY
}

is_done() {
  local run_id="$1"
  [[ -f "$CSV" ]] || return 1
  grep -q "^${run_id}," "$CSV" 2>/dev/null
}

runtime_available() {
  case "$1" in
  cursor-agent) command -v cursor-agent >/dev/null ;;
  droid) command -v droid >/dev/null ;;
  claude) command -v claude >/dev/null || [[ -x "${HOME}/.npm-global/bin/claude" ]] ;;
  codex) command -v codex >/dev/null ;;
  *) return 1 ;;
  esac
}

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG"
}

kill_stale() {
  pkill -f "run_trigger_experiment.sh" 2>/dev/null || true
  sleep 1
}

export MANIFEST
SCENARIOS="${TRIGGER_SCENARIOS:-$(pick_scenarios)}"

# Optional filters: TRIGGER_ARMS="A0-baseline A1-policy-1.6" TRIGGER_RUNTIMES="cursor-agent"
ARMS=(${TRIGGER_ARMS:-${ALL_ARMS[*]}})
RUNTIMES=(${TRIGGER_RUNTIMES:-${ALL_RUNTIMES[*]}})

total=0
planned=0
skipped=0

for arm in "${ARMS[@]}"; do
  for runtime in "${RUNTIMES[@]}"; do
    if ! runtime_available "$runtime"; then
      log "skip runtime unavailable: $runtime"
      continue
    fi
    for scenario in $SCENARIOS; do
      for round in $(seq 1 "$ROUNDS"); do
        total=$((total + 1))
        run_id="${arm}-${runtime}-${scenario}-r${round}"
        if [[ "$SKIP_DONE" == "1" ]] && is_done "$run_id"; then
          skipped=$((skipped + 1))
          continue
        fi
        planned=$((planned + 1))
        log "PLAN $run_id"
      done
    done
  done
done

log "matrix total=$total planned=$planned skipped=$skipped rounds=$ROUNDS log=$LOG"

if [[ "$DRY_RUN" == "1" ]]; then
  log "DRY_RUN=1 — exiting"
  exit 0
fi

kill_stale

# Restart local ma3 once with current code before local arms (skip when using docker :8010)
if [[ "${TRIGGER_SKIP_LOCAL_RESTART:-0}" != "1" ]]; then
  bash "$EVAL_ROOT/scripts/restart_local_ma3.sh" 2>&1 | tee -a "$LOG" || log "warn: local ma3 restart failed"
else
  log "TRIGGER_SKIP_LOCAL_RESTART=1 — keeping existing ma3 (expect :8010 self-host)"
fi

if [[ "$PARALLEL_WORKERS" -gt 1 ]]; then
  log "using parallel scheduler workers=$PARALLEL_WORKERS"
  set +e
  TRIGGER_PARALLEL_WORKERS="$PARALLEL_WORKERS" \
    python3 "$EVAL_ROOT/scripts/run_trigger_parallel_matrix.py" 2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  set -e
  python3 "$EVAL_ROOT/scripts/generate_trigger_report.py" >>"$LOG" 2>&1 || true
  log "parallel matrix complete rc=$rc skipped=$skipped"
  exit "$rc"
fi

done_count=0
fail_count=0

for arm in "${ARMS[@]}"; do
  for runtime in "${RUNTIMES[@]}"; do
    if ! runtime_available "$runtime"; then
      continue
    fi
    for scenario in $SCENARIOS; do
      for round in $(seq 1 "$ROUNDS"); do
        run_id="${arm}-${runtime}-${scenario}-r${round}"
        if [[ "$SKIP_DONE" == "1" ]] && is_done "$run_id"; then
          continue
        fi
        log "RUN $run_id ($((done_count + 1))/$planned)"
        CELL_RUNNER="${TRIGGER_CELL_RUNNER:-$EVAL_ROOT/scripts/run_trigger_cell_docker.sh}"
        if bash "$CELL_RUNNER" 0 "$arm" "$runtime" "$scenario" "$round" >>"$LOG" 2>&1; then
          done_count=$((done_count + 1))
        else
          fail_count=$((fail_count + 1))
          log "FAIL $run_id"
        fi
      done
    done
  done
done

python3 "$EVAL_ROOT/scripts/generate_trigger_report.py" >>"$LOG" 2>&1 || true
log "matrix complete done=$done_count fail=$fail_count skipped=$skipped"
