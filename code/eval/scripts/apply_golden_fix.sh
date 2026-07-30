#!/usr/bin/env bash
# Apply known-good workspace fixes (golden) so verify.sh passes without an agent.
set -euo pipefail

EVAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCENARIO="${1:?scenario id required}"
SCENARIO_DIR="$EVAL_ROOT/scenarios/$SCENARIO"

[[ -d "$SCENARIO_DIR" ]] || { echo "missing scenario dir: $SCENARIO_DIR" >&2; exit 1; }

apply_file() {
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
  echo "  golden: $(basename "$dst")"
}

echo "==> apply golden fix: ${SCENARIO}"

case "${SCENARIO}" in
  mihomo-proxy)
    apply_file "${SCENARIO_DIR}/golden/config.yaml" "${SCENARIO_DIR}/workspace/config.yaml"
    ;;
  compose-network-fix)
    apply_file "${SCENARIO_DIR}/golden/default.conf" "${SCENARIO_DIR}/workspace/default.conf"
    ;;
  nginx-reverse-proxy)
    apply_file "${SCENARIO_DIR}/golden/nginx.conf" "${SCENARIO_DIR}/workspace/nginx.conf"
    ;;
  http-proxy-apt)
    apply_file "${SCENARIO_DIR}/golden/env.sh" "${SCENARIO_DIR}/workspace/env.sh"
    ;;
  trigger-p5)
    apply_file "${SCENARIO_DIR}/golden/.npmrc" "${SCENARIO_DIR}/workspace/.npmrc"
    ;;
  postgres-backup)
    apply_file "${SCENARIO_DIR}/golden/backup.sh" "${SCENARIO_DIR}/workspace/backup.sh"
    chmod +x "${SCENARIO_DIR}/workspace/backup.sh"
    ;;
  ssh-key-only)
    apply_file "${SCENARIO_DIR}/golden/sshd_config" "${SCENARIO_DIR}/workspace/sshd_config"
    ;;
  supervisord-service)
    apply_file "${SCENARIO_DIR}/golden/supervisord.conf" "${SCENARIO_DIR}/workspace/supervisord.conf"
    ;;
  transparent-gateway)
    apply_file "${SCENARIO_DIR}/golden/redirect.sh" "${SCENARIO_DIR}/workspace/redirect.sh"
    chmod +x "${SCENARIO_DIR}/workspace/redirect.sh"
    ;;
  claude-deepseek-byok)
    [[ -n "${DEEPSEEK_API_KEY:-}" ]] || { echo "DEEPSEEK_API_KEY required" >&2; exit 1; }
    mkdir -p "${SCENARIO_DIR}/workspace/.claude"
    python3 - <<PY
import json, os
path = "${SCENARIO_DIR}/workspace/.claude/settings.json"
payload = {
  "env": {
    "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
    "ANTHROPIC_AUTH_TOKEN": os.environ["DEEPSEEK_API_KEY"],
    "ANTHROPIC_MODEL": "deepseek-v4-pro[1m]",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
  }
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2)
    f.write("\n")
print("  golden: settings.json")
PY
    ;;
  droid-deepseek-byok)
    [[ -n "${DEEPSEEK_API_KEY:-}" ]] || { echo "DEEPSEEK_API_KEY required" >&2; exit 1; }
    mkdir -p "${SCENARIO_DIR}/workspace/.factory"
    python3 - <<PY
import json, os
key = os.environ["DEEPSEEK_API_KEY"]
path = "${SCENARIO_DIR}/workspace/.factory/settings.json"
payload = {
  "model": "deepseek-v4-pro",
  "customModels": [{
    "model": "deepseek-v4-pro",
    "displayName": "DeepSeek V4 Pro",
    "baseUrl": "https://api.deepseek.com/v1",
    "apiKey": key,
    "provider": "generic-chat-completion-api",
    "extraArgs": {"thinking": {"type": "disabled"}},
  }],
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2)
    f.write("\n")
print("  golden: settings.json")
PY
    ;;
  *)
    echo "no golden fix for ${SCENARIO}" >&2
    exit 1
    ;;
esac
