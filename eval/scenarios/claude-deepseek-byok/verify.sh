#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
[[ -n "${DEEPSEEK_API_KEY:-}" ]] || { echo "DEEPSEEK_API_KEY required"; exit 1; }
SETTINGS="$D/workspace/.claude/settings.json"
python3 - <<PY
import json, os, sys
with open("$SETTINGS") as f:
    cfg = json.load(f)
env = cfg.get("env", {})
base = env.get("ANTHROPIC_BASE_URL", "")
token = env.get("ANTHROPIC_AUTH_TOKEN", "")
if "deepseek.com" not in base:
    sys.exit("ANTHROPIC_BASE_URL must point at DeepSeek anthropic endpoint")
if token in ("", "wrong-token", "sk-your-deepseek-key-here"):
    sys.exit("ANTHROPIC_AUTH_TOKEN must be set to DEEPSEEK_API_KEY value")
if token != os.environ["DEEPSEEK_API_KEY"]:
    sys.exit("ANTHROPIC_AUTH_TOKEN must match DEEPSEEK_API_KEY")
print("settings ok")
PY
curl -sf -m 15 \
  -H "Authorization: Bearer ${DEEPSEEK_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"ping"}],"max_tokens":8}' \
  https://api.deepseek.com/v1/chat/completions >/dev/null
echo verify ok
