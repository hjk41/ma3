#!/usr/bin/env bash
# Watchdog: every 5 minutes check ma3 + eval on 202; auto-fix and resume.
set -euo pipefail

INTERVAL="${WATCHDOG_INTERVAL_SEC:-60}"
EVAL_ROOT="${EVAL_ROOT:-/home/hct/ma3/eval}"
MA3_DIR="${MA3_DIR:-/home/hct/ma3}"
LOG="/tmp/ma3-eval-watchdog.log"
EVAL_LOG="/tmp/ma3-eval-full.log"
EXPECTED_LIVE_RUNS=30
export PATH="${HOME}/.npm-global/bin:${HOME}/.local/bin:${PATH}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG"; }

FAIL_FILE="/tmp/ma3-health-fail-count"
GRACE_SEC="${MA3_WATCHDOG_GRACE_SEC:-180}"

ma3_health_ok() {
  local timeout="${1:-5}"
  curl -sf -m "$timeout" http://127.0.0.1:8000/healthz >/dev/null 2>&1
}

ma3_in_grace_period() {
  local pid_file="$MA3_DIR/ma3.pid"
  [[ -f "$pid_file" ]] || return 1
  local started
  started=$(stat -c %Y "$pid_file" 2>/dev/null || echo 0)
  local age=$(( $(date +%s) - started ))
  [[ "$age" -lt "$GRACE_SEC" ]]
}

record_health_failure() {
  local fails
  fails=$(cat "$FAIL_FILE" 2>/dev/null || echo 0)
  fails=$((fails + 1))
  echo "$fails" > "$FAIL_FILE"
  echo "$fails"
}

clear_health_failures() {
  echo 0 > "$FAIL_FILE"
}

maybe_restart_ma3() {
  if ma3_in_grace_period; then
    if ma3_health_ok 30; then
      clear_health_failures
      return 0
    fi
    log "ma3 slow during grace period — skip restart"
    return 1
  fi
  if ma3_health_ok 5; then
    clear_health_failures
    return 0
  fi
  local fails
  fails=$(record_health_failure)
  log "ma3 health fail count=$fails"
  if [[ "$fails" -lt 3 ]]; then
    return 1
  fi
  clear_health_failures
  restart_ma3
  return 0
}

restart_ma3() {
  log "RESTART ma3 (health check failed or hung)"
  pkill -9 -f "uvicorn app.main:app" 2>/dev/null || true
  sleep 2
  export MA3_OP_LOG_DIR="$MA3_DIR/data/ops"
  export MA3_DATA_DIR="$MA3_DIR/data"
  export MA3_HF_HOME="$MA3_DIR/data/hf-cache"
  mkdir -p "$MA3_OP_LOG_DIR" "$MA3_DATA_DIR" "$MA3_HF_HOME"
  if [[ -f "$MA3_DIR/ma3.env" ]]; then set -a; . "$MA3_DIR/ma3.env"; set +a; fi
  if [[ ! -d "$MA3_HF_HOME/hub/models--sentence-transformers--all-MiniLM-L6-v2" ]] \
    && [[ ! -d "$MA3_HF_HOME/models--sentence-transformers--all-MiniLM-L6-v2" ]]; then
    log "prewarm embedding model (cache miss)"
    bash "$MA3_DIR/deploy/prewarm_embedding_model.sh" >> "$LOG" 2>&1 || true
  fi
  cd "$MA3_DIR"
  nohup .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir server \
    >> /tmp/ma3-uvicorn.log 2>&1 &
  echo $! > "$MA3_DIR/ma3.pid"
  sleep 5
  if ma3_health_ok; then
    log "ma3 restarted OK pid=$(pgrep -f 'uvicorn app.main' | head -1)"
    # Keys may be invalid after hard restart on fresh DB — re-bootstrap if MCP fails
    # shellcheck disable=SC1091
    source "$EVAL_ROOT/scripts/load_secrets.sh" 2>/dev/null || true
    if [[ -n "${MA3_KEY_CLAUDE_CODE:-}" ]]; then
      if ! curl -sf -m 5 -X POST http://127.0.0.1:8000/mcp \
        -H "Content-Type: application/json" \
        -H "X-API-Key: $MA3_KEY_CLAUDE_CODE" \
        -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"ma3_whoami","arguments":{}}}' \
        | grep -q '"isError":false'; then
        log "MCP auth failed — re-bootstrap eval tenant"
        bash "$EVAL_ROOT/scripts/bootstrap_eval_tenant.sh" >> "$LOG" 2>&1 || true
        bash "$EVAL_ROOT/scripts/setup_agent_profiles.sh" >> "$LOG" 2>&1 || true
      fi
    fi
  else
    log "ERROR ma3 still unhealthy after restart"
  fi
}

count_live_runs() {
  python3 - <<'PY'
import json, glob
n = 0
for p in glob.glob("/home/hct/ma3/eval/results/eval-*.json"):
    try:
        d = json.load(open(p))
    except Exception:
        continue
    # live run: agent invoked (not dry-run compose-only)
    dur = d.get("duration_s", 0)
    if dur >= 15 and d.get("round") is not None:
        n += 1
print(n)
PY
}

eval_running() {
  pgrep -f "run_all_eval.sh" >/dev/null || pgrep -f "run_eval.sh --scenario" >/dev/null
}

start_eval() {
  log "START run_all_eval.sh (resume mode)"
  cd "$MA3_DIR"
  nohup bash "$EVAL_ROOT/orchestrator/run_all_eval.sh" --resume \
    >> "$EVAL_LOG" 2>&1 &
  disown $! 2>/dev/null || true
  log "eval pid=$!"
}

fix_once() {
  maybe_restart_ma3 || true
  local live
  live=$(count_live_runs)
  log "status: ma3=$(ma3_health_ok && echo ok || echo bad) live_runs=$live/$EXPECTED_LIVE_RUNS eval_running=$(eval_running && echo yes || echo no)"
  if [[ "$live" -ge "$EXPECTED_LIVE_RUNS" ]]; then
    log "DONE all live runs complete"
    python3 "$EVAL_ROOT/scripts/generate_report.py" >> "$LOG" 2>&1 || true
    return 0
  fi
  if ! eval_running; then
    start_eval
  fi
  return 1
}

log "watchdog started interval=${INTERVAL}s"
while true; do
  if fix_once; then
    log "watchdog exiting — eval complete"
    exit 0
  fi
  sleep "$INTERVAL"
done
