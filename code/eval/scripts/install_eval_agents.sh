#!/usr/bin/env bash
# Install Claude Code, Factory Droid, Cursor CLI on eval host (202).
# Does not modify global shell profile except optional ~/.local/bin PATH.
set -euo pipefail

EVAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$EVAL_ROOT/scripts/load_secrets.sh"

export PATH="${HOME}/.local/bin:${HOME}/.npm-global/bin:${PATH}"

install_node_if_needed() {
  if command -v node >/dev/null 2>&1; then
    return
  fi
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get install -y nodejs npm 2>/dev/null || true
  fi
}

install_claude() {
  if command -v claude >/dev/null 2>&1; then
    echo "claude: $(claude --version 2>/dev/null || echo present)"
    return
  fi
  install_node_if_needed
  npm config set prefix "${HOME}/.npm-global" 2>/dev/null || true
  npm install -g @anthropic-ai/claude-code
}

install_droid() {
  if command -v droid >/dev/null 2>&1; then
    echo "droid: present"
    return
  fi
  curl -fsSL https://app.factory.ai/cli | bash || npm install -g droid
}

install_cursor() {
  if command -v cursor >/dev/null 2>&1 || command -v cursor-agent >/dev/null 2>&1; then
    ln -sf "${HOME}/.local/bin/cursor-agent" "${HOME}/.local/bin/cursor" 2>/dev/null || true
    echo "cursor: present"
    return
  fi
  curl -fsSL https://cursor.com/install | bash || true
  ln -sf "${HOME}/.local/bin/cursor-agent" "${HOME}/.local/bin/cursor" 2>/dev/null || true
}

install_deepseek_proxy() {
  local venv="${HOME}/.local/share/ma3-eval/deepseek-proxy-venv"
  if [[ ! -d "$venv" ]]; then
    python3 -m venv "$venv"
    "$venv/bin/pip" install -q --upgrade pip httpx uvicorn fastapi
  fi
  cat > "${HOME}/.local/share/ma3-eval/deepseek_proxy.py" <<'PY'
"""Minimal OpenAI-compatible proxy for Cursor CLI + DeepSeek (no reasoning round-trip)."""
from __future__ import annotations
import os
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
UPSTREAM = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
API_KEY = os.environ["DEEPSEEK_API_KEY"]

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(path: str, request: Request):
    url = f"{UPSTREAM.rstrip('/')}/{path}"
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in {"host", "content-length"}}
    headers["Authorization"] = f"Bearer {API_KEY}"
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.request(request.method, url, content=body, headers=headers)
    if "text/event-stream" in r.headers.get("content-type", ""):
        return StreamingResponse(r.aiter_bytes(), status_code=r.status_code, headers=dict(r.headers))
    return JSONResponse(content=r.json() if r.content else {}, status_code=r.status_code)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("DEEPSEEK_PROXY_PORT", "9000")))
PY
  if ! pgrep -f "deepseek_proxy.py" >/dev/null 2>&1; then
    nohup "$venv/bin/python" "${HOME}/.local/share/ma3-eval/deepseek_proxy.py" \
      > /tmp/deepseek-proxy.log 2>&1 &
    sleep 2
  fi
  echo "deepseek proxy on http://127.0.0.1:9000"
}

install_claude
install_droid
install_cursor
install_deepseek_proxy

bash "$EVAL_ROOT/scripts/setup_agent_profiles.sh"

# Register Claude MCP if claude available
if command -v claude >/dev/null 2>&1 && [[ -n "${MA3_KEY_CLAUDE_CODE:-}" ]]; then
  export HOME="${EVAL_PROFILE_ROOT:-/home/hct/ma3-eval/profiles}/claude"
  claude mcp remove ma3 2>/dev/null || true
  claude mcp add --scope user --transport http ma3 \
    "${MA3_BASE_URL:-http://127.0.0.1:8000}/mcp" \
    --header "X-API-Key: ${MA3_KEY_CLAUDE_CODE}" || echo "warn: claude mcp add failed" >&2
fi

echo "==> Agent install complete"
command -v claude && claude --version 2>/dev/null || echo "claude missing"
command -v droid && echo droid ok || echo "droid missing"
command -v cursor && cursor --version 2>/dev/null || command -v cursor-agent && echo cursor-agent ok || echo "cursor missing"
