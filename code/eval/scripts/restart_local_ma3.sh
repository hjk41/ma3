#!/usr/bin/env bash
# Restart local ma3 uvicorn with optional trigger experiment env flags.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
MA3_ENV="${MA3_ENV_FILE:-$REPO_ROOT/ma3.env}"
PORT="${MA3_LOCAL_PORT:-8000}"
LOG="${MA3_UVICORN_LOG:-/tmp/ma3-local-uvicorn.log}"

# Extra env: MA3_TRIGGER_ENHANCED_TOOL_DESC=1 MA3_TRIGGER_SOFT_SIGNALS=1 etc.
EXTRA_ENV=("$@")

if [[ ! -f "$MA3_ENV" ]]; then
  echo "missing ma3.env at $MA3_ENV" >&2
  exit 1
fi

kill_port() {
  local pids
  pids=$(pgrep -f "uvicorn app.main:app.*--port ${PORT}" 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    echo "stopping uvicorn on :${PORT}: $pids"
    kill $pids 2>/dev/null || true
    sleep 2
  fi
}

kill_port

cd "$REPO_ROOT/code/server"
set -a
# shellcheck disable=SC1090
source "$MA3_ENV"
set +a

for kv in "${EXTRA_ENV[@]}"; do
  export "$kv"
done

export NO_PROXY="127.0.0.1,localhost,192.168.0.0/16,10.0.0.0/8,${NO_PROXY:-}"
export no_proxy="$NO_PROXY"

nohup env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  "${EXTRA_ENV[@]}" \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --app-dir . \
  >>"$LOG" 2>&1 &
echo "started pid=$! log=$LOG flags=${EXTRA_ENV[*]:-<none>}"

for i in $(seq 1 30); do
  if curl -sf --noproxy '*' "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1; then
    curl -sf --noproxy '*' "http://127.0.0.1:${PORT}/healthz" | python3 -c "import sys,json; h=json.load(sys.stdin); print('health ok skill_bundle', h.get('skill_bundle_version'))"
    exit 0
  fi
  sleep 1
done

echo "local ma3 failed to become healthy on :${PORT}" >&2
tail -20 "$LOG" >&2 || true
exit 1
