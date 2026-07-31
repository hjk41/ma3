#!/usr/bin/env bash
# Run one trigger matrix cell in an isolated worker HOME (for parallel scheduling).
set -euo pipefail

WORKER_ID="${1:?worker id}"
ARM="${2:?arm}"
RUNTIME="${3:?runtime}"
SCENARIO="${4:?scenario}"
ROUND="${5:?round}"

EVAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST_HOME="${TRIGGER_HOST_HOME:-/home/hct}"
# shellcheck disable=SC1091
# When running inside Docker, secrets are already injected as env; host secrets.env may be absent.
if [[ -f "$EVAL_ROOT/scripts/load_secrets.sh" ]]; then
  set +e
  # shellcheck disable=SC1091
  source "$EVAL_ROOT/scripts/load_secrets.sh" || true
  set -e
fi

WORKER_ROOT="${TRIGGER_WORKER_ROOT:-$EVAL_ROOT/results/trigger/workers}/w${WORKER_ID}"
export HOME="${WORKER_ROOT}/home"
CELL_LOG="${WORKER_ROOT}/cell.log"
mkdir -p "$HOME"/{.cursor,.ma3,.factory,.claude,.codex,.config/cursor,.local/bin}

export MA3_KEY_REMOTE="${MA3_KEY_REMOTE:-${MA3_KEY_CURSOR_CLI:-}}"
if [[ -z "${MA3_KEY_REMOTE}" ]]; then
  echo "MA3_KEY_REMOTE or MA3_KEY_CURSOR_CLI required (no hardcoded default)" >&2
  exit 1
fi
export MA3_KEY_LOCAL="${MA3_KEY_LOCAL:-${MA3_DEV_API_KEY:-ma3dev}}"
export PATH="${HOME}/.local/bin:${HOME}/.npm-global/bin:${HOST_HOME}/.local/bin:${HOST_HOME}/.npm-global/bin:${PATH}"
export NO_PROXY="127.0.0.1,localhost,192.168.0.0/16,10.0.0.0/8,${NO_PROXY:-}"
export no_proxy="$NO_PROXY"

# Agent API auth (worker HOME is empty — seed from host / secrets).
export DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}"
export CURSOR_API_KEY="${CURSOR_API_KEY:-}"
export FACTORY_API_KEY="${FACTORY_API_KEY:-}"
export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-https://api.deepseek.com/anthropic}"
export ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_AUTH_TOKEN:-${DEEPSEEK_API_KEY}}"
export ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-deepseek-v4-pro[1m]}"
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="${CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC:-1}"

if [[ -f "${HOST_HOME}/.config/cursor/auth.json" ]]; then
  cp -a "${HOST_HOME}/.config/cursor/auth.json" "${HOME}/.config/cursor/auth.json"
fi
if [[ -f "${HOST_HOME}/.cursor/cli-config.json" ]]; then
  cp -a "${HOST_HOME}/.cursor/cli-config.json" "${HOME}/.cursor/cli-config.json"
fi

python3 - <<PY
import json, os
home = os.environ["HOME"]
deepseek = os.environ.get("DEEPSEEK_API_KEY", "")
claude_settings = {
    "env": {
        "ANTHROPIC_BASE_URL": os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic"),
        "ANTHROPIC_AUTH_TOKEN": deepseek,
        "ANTHROPIC_MODEL": os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-pro[1m]"),
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }
}
droid_settings = {
    "model": "deepseek-v4-pro",
    "customModels": [{
        "model": "deepseek-v4-pro",
        "displayName": "DeepSeek V4 Pro",
        "baseUrl": "https://api.deepseek.com/v1",
        "apiKey": deepseek,
        "provider": "generic-chat-completion-api",
        "extraArgs": {"thinking": {"type": "disabled"}},
    }],
}
os.makedirs(f"{home}/.claude", exist_ok=True)
os.makedirs(f"{home}/.factory", exist_ok=True)
with open(f"{home}/.claude/settings.json", "w", encoding="utf-8") as f:
    json.dump(claude_settings, f, indent=2)
with open(f"{home}/.factory/settings.json", "w", encoding="utf-8") as f:
    json.dump(droid_settings, f, indent=2)
PY

for bin in cursor-agent droid claude codex; do
  host_bin="$(command -v "$bin" 2>/dev/null || true)"
  [[ -z "$host_bin" && "$bin" == "claude" ]] && host_bin="${HOST_HOME}/.npm-global/bin/claude"
  [[ -z "$host_bin" && "$bin" == "codex" ]] && host_bin="${HOST_HOME}/.local/bin/codex"
  if [[ -n "$host_bin" && ! -e "${HOME}/.local/bin/$bin" ]]; then
    ln -sf "$host_bin" "${HOME}/.local/bin/$bin"
  fi
done

# Codex uses ~/.codex (provider + MCP bridge); seed from host then arm setup rewrites MCP.
mkdir -p "${HOME}/.codex"
if [[ -f "${HOST_HOME}/.codex/config.toml" ]]; then
  cp -a "${HOST_HOME}/.codex/config.toml" "${HOME}/.codex/config.toml"
fi
# DuckCoding token for Codex provider env_key
if [[ -z "${DUCKCODING_CODEX_TOKEN:-}" && -f "${HOST_HOME}/.bashrc" ]]; then
  eval "$(grep -E '^export DUCKCODING_CODEX_TOKEN=' "${HOST_HOME}/.bashrc" | head -1)" || true
fi
export DUCKCODING_CODEX_TOKEN
export DUCKCODING_HTTPS_PROXY="${DUCKCODING_HTTPS_PROXY:-http://192.168.31.200:1080}"

{
  echo "===== cell ${ARM}-${RUNTIME}-${SCENARIO}-r${ROUND} $(date -u +%Y-%m-%dT%H:%M:%SZ) ====="
  bash "$EVAL_ROOT/scripts/setup_trigger_arm.sh" "$ARM"
  TRIGGER_ARM="$ARM" TRIGGER_RUNTIME="$RUNTIME" TRIGGER_SCENARIOS="$SCENARIO" TRIGGER_ROUND="$ROUND" \
    TRIGGER_WORKER_MODE=1 \
    bash "$EVAL_ROOT/scripts/run_trigger_experiment.sh"
} >>"$CELL_LOG" 2>&1
