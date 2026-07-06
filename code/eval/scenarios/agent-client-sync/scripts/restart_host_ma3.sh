#!/usr/bin/env bash
# Restart ma3_v1 on the HOST (202) with a given MA3_SKILL_VERSION for upgrade tests.
set -euo pipefail

VERSION="${1:?skill version required, e.g. 1.0.0}"
MA3_DIR="${MA3_DIR:-/home/hct/ma3_deploy}"
LEGACY_ENV="${LEGACY_ENV:-/home/hct/ma3/ma3.env}"
PORT="${MA3_PORT:-8000}"
SERVER="${MA3_DIR}/code/server"

if [[ ! -d "${SERVER}/.venv" ]]; then
  echo "FAIL: ${SERVER}/.venv missing" >&2
  exit 1
fi

echo "==> restart host ma3 skill_version=${VERSION} port=${PORT}"

pkill -f "uvicorn app.main:app.*--port ${PORT}" || true
sleep 2

set -a
[[ -f "${LEGACY_ENV}" ]] && source "${LEGACY_ENV}"
[[ -f "${MA3_DIR}/ma3.env" ]] && source "${MA3_DIR}/ma3.env"
set +a

export MA3_SKILL_VERSION="${VERSION}"
export MA3_DEV_AUTH="${MA3_DEV_AUTH:-1}"
export MA3_DEV_API_KEY="${MA3_DEV_API_KEY:-ma3dev}"
export MA3_DISABLE_EMBEDDINGS="${MA3_DISABLE_EMBEDDINGS:-1}"
export MA3_INSTANCE_ID="${MA3_INSTANCE_ID:-ma3-v1-202}"

cd "${SERVER}"
nohup .venv/bin/python -m uvicorn app.main:app \
  --host 0.0.0.0 --port "${PORT}" --app-dir . \
  >> /tmp/ma3-v1-uvicorn.log 2>&1 &
echo $! > "${MA3_DIR}/ma3.pid"

for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${PORT}/healthz" >/dev/null; then
    break
  fi
  sleep 1
done

curl -sf "http://127.0.0.1:${PORT}/healthz" | jq -r '.skill_bundle_version // .version // .status'
MANIFEST="$(curl -sf "http://127.0.0.1:${PORT}/client/manifest.json" | jq -r .skill_bundle_version)"
if [[ "${MANIFEST}" != "${VERSION}" ]]; then
  echo "FAIL: manifest skill_bundle_version=${MANIFEST} expected=${VERSION}" >&2
  exit 1
fi
echo "==> host ma3 ready skill_bundle_version=${MANIFEST}"
