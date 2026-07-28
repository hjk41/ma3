#!/usr/bin/env bash
# Run one eval scenario round with an agent. Secrets via eval/secrets/*.env only.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EVAL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck disable=SC1091
source "$EVAL_ROOT/scripts/load_secrets.sh"

export PATH="${HOME}/.npm-global/bin:${HOME}/.local/bin:${PATH}"

SCENARIO=""
AGENT=""
ROUND="1"
TIMEOUT_SEC="${EVAL_TIMEOUT_SEC:-1200}"
DRY_RUN=0

usage() {
  echo "Usage: $0 --scenario <id> --agent <claude-code|droid|cursor-cli> [--round N] [--dry-run]"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scenario) SCENARIO="$2"; shift 2 ;;
    --agent) AGENT="$2"; shift 2 ;;
    --round) ROUND="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage ;;
    *) echo "unknown arg: $1"; usage ;;
  esac
done

[[ -n "$SCENARIO" && -n "$AGENT" ]] || usage

SCENARIO_DIR="$EVAL_ROOT/scenarios/$SCENARIO"
RUN_ID="eval-${SCENARIO}-${AGENT}-r${ROUND}"
RESULT_DIR="$EVAL_ROOT/results"
RESULT_FILE="$RESULT_DIR/${RUN_ID}.json"
PROFILE_ROOT="${EVAL_PROFILE_ROOT:-$HOME/ma3-eval/profiles}"

mkdir -p "$RESULT_DIR"

if [[ ! -d "$SCENARIO_DIR" ]]; then
  echo "missing scenario dir: $SCENARIO_DIR" >&2
  exit 1
fi

LOG_OFFSET=0
LOG_DIR="${MA3_OP_LOG_DIR:-$HOME/ma3/data/ops}"
TODAY="$(date -u +%F)"
if [[ -f "$LOG_DIR/$TODAY.jsonl" ]]; then
  LOG_OFFSET=$(wc -l < "$LOG_DIR/$TODAY.jsonl")
fi

START_TS=$(date -u +%s)

echo "==> [$RUN_ID] prepare scenario"
if [[ -x "$SCENARIO_DIR/setup.sh" ]]; then
  (cd "$SCENARIO_DIR" && bash setup.sh)
fi

echo "==> [$RUN_ID] compose up"
if [[ -f "$SCENARIO_DIR/docker-compose.yml" ]]; then
  # Subscription URL injected at runtime — never baked into compose files in git
  export MIHOMO_SUBSCRIPTION_URL="${MIHOMO_SUBSCRIPTION_URL:-}"
  (cd "$SCENARIO_DIR" && docker compose up -d --build)
fi

PROMPT_FILE="$SCENARIO_DIR/README.md"
PROMPT=$(cat "$PROMPT_FILE")
PROMPT="$PROMPT

---
run_id: $RUN_ID
Rules:
- Call ma3_context first (target_product=ma3-eval, target_component=$SCENARIO).
- On every MCP call pass client_version and tool_schema_version from ~/.ma3/ma3-client.json (run bash ~/.ma3/bin/sync_ma3_client.sh sync if missing).
- If structuredContent.server.client_update_required is true: run sync, copy policy to your runtime file, re-call MCP until required is false — do not ma3_report until then.
- Do not modify host global config outside /workspace and scenario containers.
- After solving, ma3_validate then ma3_report if reusable knowledge was produced.
"

AGENT_EXIT=0
AGENT_BACKEND="${AGENT}"
if [[ "$DRY_RUN" -eq 0 ]]; then
  run_claude() {
    export HOME="$1"
    export DEEPSEEK_API_KEY
    timeout "$TIMEOUT_SEC" claude -p --dangerously-skip-permissions "$PROMPT" || AGENT_EXIT=$?
  }
  case "$AGENT" in
    claude-code)
      run_claude "$PROFILE_ROOT/claude"
      ;;
    droid)
      export HOME="$PROFILE_ROOT/droid"
      export DEEPSEEK_API_KEY FACTORY_API_KEY="${FACTORY_API_KEY:-}"
      if [[ -n "${FACTORY_API_KEY:-}" ]] && command -v droid >/dev/null 2>&1; then
        timeout "$TIMEOUT_SEC" droid exec --auto high --model deepseek-v4-pro "$PROMPT" || AGENT_EXIT=$?
      else
        echo "[$RUN_ID] droid unavailable (no FACTORY_API_KEY) - fallback claude+deepseek" >&2
        AGENT_BACKEND="droid-claude-fallback"
        run_claude "$PROFILE_ROOT/droid"
      fi
      ;;
    cursor-cli)
      export HOME="$PROFILE_ROOT/cursor"
      export DEEPSEEK_API_KEY CURSOR_API_KEY="${CURSOR_API_KEY:-}"
      if [[ -n "${CURSOR_API_KEY:-}" ]] && command -v cursor-agent >/dev/null 2>&1; then
        timeout "$TIMEOUT_SEC" cursor-agent -p "$PROMPT" || AGENT_EXIT=$?
      else
        echo "[$RUN_ID] cursor-agent unavailable (no CURSOR_API_KEY) - fallback claude+deepseek" >&2
        AGENT_BACKEND="cursor-claude-fallback"
        run_claude "$PROFILE_ROOT/cursor"
      fi
      ;;
    *) echo "unknown agent: $AGENT"; exit 1 ;;
  esac
fi

VERIFY_EXIT=0
if [[ -x "$SCENARIO_DIR/verify.sh" ]]; then
  echo "==> [$RUN_ID] verify"
  (cd "$SCENARIO_DIR" && bash verify.sh) || VERIFY_EXIT=$?
fi

END_TS=$(date -u +%s)
WATCH_JSON='{}'
if watch_out="$(python3 "$EVAL_ROOT/scripts/ma3_watch.py" --since-line "$LOG_OFFSET" 2>/dev/null)"; then
  WATCH_JSON="$watch_out"
elif [[ -n "$watch_out" ]]; then
  # Non-zero exit but stdout still has JSON (legacy callers); do not append a second blob.
  WATCH_JSON="$watch_out"
fi

export EVAL_RUN_ID="$RUN_ID" EVAL_SCENARIO="$SCENARIO" EVAL_AGENT="$AGENT"
export EVAL_AGENT_BACKEND="$AGENT_BACKEND" EVAL_ROUND="$ROUND"
export EVAL_AGENT_EXIT="$AGENT_EXIT" EVAL_VERIFY_EXIT="$VERIFY_EXIT"
export EVAL_START_TS="$START_TS" EVAL_END_TS="$END_TS" EVAL_RESULT_FILE="$RESULT_FILE"
export EVAL_WATCH_JSON="$WATCH_JSON"

RESULT_WRITE_EXIT=0
python3 - <<'PY' || RESULT_WRITE_EXIT=$?
import json
import os

raw = os.environ.get("EVAL_WATCH_JSON", "").strip()
try:
    watch = json.loads(raw) if raw else {}
except json.JSONDecodeError:
    watch = {"error": "invalid_watch_json", "raw_preview": raw[:200]}

out = {
    "run_id": os.environ["EVAL_RUN_ID"],
    "scenario": os.environ["EVAL_SCENARIO"],
    "agent": os.environ["EVAL_AGENT"],
    "agent_backend": os.environ["EVAL_AGENT_BACKEND"],
    "round": os.environ["EVAL_ROUND"],
    "agent_exit": int(os.environ["EVAL_AGENT_EXIT"]),
    "verify_pass": int(os.environ["EVAL_VERIFY_EXIT"]) == 0,
    "duration_s": int(os.environ["EVAL_END_TS"]) - int(os.environ["EVAL_START_TS"]),
    "ma3": watch,
}
path = os.environ["EVAL_RESULT_FILE"]
with open(path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)
print(json.dumps(out, indent=2))
PY

if [[ "$RESULT_WRITE_EXIT" -ne 0 ]]; then
  echo "[$RUN_ID] WARN: failed to write result json (exit=$RESULT_WRITE_EXIT)" >&2
fi

echo "==> [$RUN_ID] compose down"
if [[ -f "$SCENARIO_DIR/docker-compose.yml" ]]; then
  (cd "$SCENARIO_DIR" && docker compose down -v) || true
fi

exit $VERIFY_EXIT
