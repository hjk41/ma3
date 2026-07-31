#!/usr/bin/env bash
# Probe: ask Claude Code a ma3-specific question and check if it calls ma3_context.
set -euo pipefail

EVAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$EVAL_ROOT/../.." && pwd)"
RESULT_DIR="$EVAL_ROOT/results/trigger"
LOG="$RESULT_DIR/claude-visibility-probe.log"
OUT="$RESULT_DIR/claude-visibility-probe.json"
export PATH="${HOME}/.npm-global/bin:${HOME}/.local/bin:${PATH}"

# shellcheck disable=SC1091
source "$EVAL_ROOT/scripts/load_secrets.sh"
export MA3_KEY_LOCAL="${MA3_KEY_LOCAL:-ma3dev}"

mkdir -p "${HOME}/.claude/skills/ma3"
cp "$REPO/code/client/skills/ma3/SKILL.md" "${HOME}/.claude/skills/ma3/SKILL.md"
cat > "${HOME}/.claude/CLAUDE.md" <<'EOF'
# Project notes

ma3 MCP server `ma3` is configured. On **non-trivial** tasks (debugging, infra, multi-step fixes),
follow the **ma3** skill: query `ma3_context` before mutating actions, then write back with
`ma3_feedback` / `ma3_report` when done.
EOF

bash "$EVAL_ROOT/scripts/setup_trigger_arm.sh" B0-local-skill-mcp
# shellcheck disable=SC1091
source "${HOME}/.ma3/trigger-experiment-backup/current-arm.env"
export NO_PROXY="127.0.0.1,localhost,192.168.0.0/16,10.0.0.0/8,${NO_PROXY:-}"
export no_proxy="$NO_PROXY"
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

claude mcp remove ma3 2>/dev/null || true
claude mcp add --scope user --transport http ma3 \
  "${MA3_BASE_URL%/}/mcp" \
  --header "X-API-Key: ${MA3_API_KEY}"

PROMPT='为什么我往 ma3 写的某条知识，别人看不到？'
PROBE_DIR="$RESULT_DIR/probes/visibility-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$PROBE_DIR"
cd "$PROBE_DIR"

echo "=== Claude visibility probe $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee "$LOG"
echo "cwd: $PROBE_DIR" | tee -a "$LOG"
echo "prompt: $PROMPT" | tee -a "$LOG"
claude mcp list 2>&1 | head -5 | tee -a "$LOG"

T0=$(date +%s)
timeout 300 claude -p --dangerously-skip-permissions "$PROMPT" >"$OUT" 2>"${OUT}.err" || true
DURATION=$(( $(date +%s) - T0 ))

echo "" | tee -a "$LOG"
echo "--- claude stdout (${DURATION}s) ---" | tee -a "$LOG"
head -c 4000 "$OUT" | tee -a "$LOG"
echo "" | tee -a "$LOG"

LATEST_TX=$(find "${HOME}/.claude/projects" -name '*.jsonl' -mmin -10 2>/dev/null | sort | tail -1 || true)
echo "--- transcript metrics ---" | tee -a "$LOG"
if [[ -n "$LATEST_TX" ]]; then
  python3 "$EVAL_ROOT/scripts/analyze_trigger_run.py" \
    --transcript "$LATEST_TX" --scenario visibility-probe --expects-read yes 2>/dev/null | tee -a "$LOG" || true
  echo "transcript: $LATEST_TX" | tee -a "$LOG"
  grep -E 'ma3_context|ma3_whoami|ma3_report|ma3_feedback|mcp__ma3' "$LATEST_TX" | head -20 | tee -a "$LOG" || echo "(no ma3 tool lines in transcript)" | tee -a "$LOG"
else
  echo "no transcript" | tee -a "$LOG"
fi
