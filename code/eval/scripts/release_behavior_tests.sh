#!/usr/bin/env bash
# Release-gate agent behavior tests (T0-T5) — see docs/08-quality/testing/release-agent-behavior-tests.md
# Runs ONE agent through the behavior scenarios on the 202 host.
#
# Usage:
#   release_behavior_tests.sh <claude|codex|hermes> <T0|T4|T5|whoami> [prompt]
#
# This script only abstracts *how to invoke each agent non-interactively* and the
# shared env (proxy for codex LLM, deepseek for hermes, NO_PROXY for localhost MCP).
# Heavy scenario orchestration (T1/T2/T3) is driven by the caller.
set -uo pipefail

AGENT="${1:?agent required: claude|codex|hermes}"
MODE="${2:?mode required: run|whoami}"
PROMPT="${3:-}"

PROFILE_ROOT="${EVAL_PROFILE_ROOT:-/home/hct/ma3-eval/profiles}"
MA3_BASE_URL="${MA3_BASE_URL:-http://127.0.0.1:8000}"
PROXY="${MA3_EVAL_PROXY:-http://192.168.31.200:1080}"
export PATH="$HOME/.npm-global/bin:$HOME/.local/bin:$PATH"

# localhost MCP must never go through the proxy
export NO_PROXY="127.0.0.1,localhost,192.168.31.202"

# shellcheck disable=SC1091
source /home/hct/ma3/eval/secrets/secrets.env 2>/dev/null || true
# shellcheck disable=SC1091
source /home/hct/ma3/eval/secrets/agent-keys.env 2>/dev/null || true

run_agent() {
  local prompt="$1"
  case "$AGENT" in
    claude)
      export HOME="$PROFILE_ROOT/claude"
      export DEEPSEEK_API_KEY
      # Claude's own API needs no proxy in this env; MCP is localhost.
      timeout "${AGENT_TIMEOUT:-280}" claude -p --dangerously-skip-permissions "$prompt" < /dev/null
      ;;
    codex)
      export HOME="$PROFILE_ROOT/codex"
      # Codex LLM (duckcoding) is blocked from 202 egress -> use proxy; MCP localhost via NO_PROXY.
      export HTTP_PROXY="$PROXY" HTTPS_PROXY="$PROXY"
      timeout "${AGENT_TIMEOUT:-280}" codex exec --skip-git-repo-check \
        --dangerously-bypass-approvals-and-sandbox "$prompt" < /dev/null
      ;;
    hermes)
      export HERMES_HOME="$PROFILE_ROOT/hermes/.hermes"
      # Hermes LLM (deepseek) via proxy; MCP localhost via NO_PROXY.
      export HTTP_PROXY="$PROXY" HTTPS_PROXY="$PROXY"
      timeout "${AGENT_TIMEOUT:-280}" hermes chat -q "$prompt" --yolo 2>&1
      ;;
    *) echo "unknown agent: $AGENT" >&2; exit 1 ;;
  esac
}

case "$MODE" in
  whoami)
    run_agent "Call the ma3 MCP tool ma3_whoami (use the MCP tool directly, not shell/curl) with empty arguments. Print exactly one line: 'PASS principal_id=<id>' from the tool result, or 'FAIL'."
    ;;
  run)
    [[ -n "$PROMPT" ]] || { echo "prompt required for run mode" >&2; exit 1; }
    run_agent "$PROMPT"
    ;;
  *) echo "unknown mode: $MODE" >&2; exit 1 ;;
esac
