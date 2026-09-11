#!/usr/bin/env bash
set -euo pipefail
cp -a ~/.codex/config.toml ~/.codex/config.toml.bak."$(date +%Y%m%d%H%M%S)"

python3 <<'PY'
import json, os, urllib.request
key = os.environ["DEEPSEEK_API_KEY"]
req = urllib.request.Request(
    "https://api.deepseek.com/v1/chat/completions",
    data=json.dumps(
        {
            "model": "deepseek-flash",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
        }
    ).encode(),
    headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    },
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()[:200]
        print("chat_ok", r.status, body)
except Exception as e:
    print("chat_err", e)
PY

python3 <<'PY'
import os
from pathlib import Path

key = os.environ.get("MA3_API_KEY", "")
if not key:
    raise SystemExit("MA3_API_KEY missing")
cfg = f"""model = "deepseek-flash"
model_provider = "deepseek"
approval_policy = "never"
sandbox_mode = "danger-full-access"

[model_providers.deepseek]
name = "DeepSeek"
base_url = "https://api.deepseek.com/v1"
env_key = "DEEPSEEK_API_KEY"
wire_api = "responses"

[model_providers.duckcoding]
name = "DuckCoding"
base_url = "https://api.duckcoding.ai/v1"
env_key = "DUCKCODING_CODEX_TOKEN"
wire_api = "responses"

[mcp_servers.ma3]
url = "https://ma3.io/mcp"
enabled = true

[mcp_servers.ma3.http_headers]
X-API-Key = "{key}"

[projects."/home/hct/ma3"]
trust_level = "trusted"
"""
Path.home().joinpath(".codex/config.toml").write_text(cfg, encoding="utf-8")
print("wrote config.toml ok")
PY

~/.local/bin/codex mcp list 2>&1 | head -50
echo "--- doctor ---"
~/.local/bin/codex doctor 2>&1 | head -80
