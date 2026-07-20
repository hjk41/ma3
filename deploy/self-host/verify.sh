#!/usr/bin/env bash
# Minimal self-host smoke: healthz + MCP tools/list with bootstrap key.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

BASE_URL="${MA3_BASE_URL:-http://127.0.0.1:${MA3_PORT:-8000}}"
echo "GET $BASE_URL/healthz"
curl -fsS "$BASE_URL/healthz" | head -c 500 || true
echo

KEY_FILE_HOST=""
if docker compose ps --status running 2>/dev/null | grep -q ma3; then
  KEY="$(docker compose exec -T ma3 sh -c 'grep ^plaintext_key= /data/bootstrap_api_key.txt 2>/dev/null | cut -d= -f2-' || true)"
else
  KEY="${MA3_API_KEY:-}"
fi

if [[ -z "${KEY}" ]]; then
  echo "No API key found. Set MA3_API_KEY or ensure bootstrap file exists in the container." >&2
  exit 1
fi

echo "POST $BASE_URL/mcp tools/list"
curl -fsS -X POST "$BASE_URL/mcp" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | head -c 800 || true
echo
echo "OK"
