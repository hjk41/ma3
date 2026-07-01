#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
[[ -n "${DEEPSEEK_API_KEY:-}" ]] || { echo "DEEPSEEK_API_KEY required"; exit 1; }
SETTINGS="$D/workspace/.factory/settings.json"
python3 - <<PY
import json, os, sys
with open("$SETTINGS") as f:
    cfg = json.load(f)
models = cfg.get("customModels") or []
if not models:
    sys.exit("customModels required")
m = models[0]
if "deepseek.com" not in m.get("baseUrl", ""):
    sys.exit("baseUrl must point at DeepSeek")
if m.get("apiKey") != os.environ["DEEPSEEK_API_KEY"]:
    sys.exit("apiKey must match DEEPSEEK_API_KEY")
extra = m.get("extraArgs") or {}
thinking = (extra.get("thinking") or {}).get("type")
if thinking != "disabled":
    sys.exit("thinking.type must be disabled")
print("settings ok")
PY
curl -sf -m 15 \
  -H "Authorization: Bearer ${DEEPSEEK_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"ping"}],"max_tokens":8}' \
  https://api.deepseek.com/v1/chat/completions >/dev/null
echo verify ok
