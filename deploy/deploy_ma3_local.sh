#!/usr/bin/env bash
# Deploy ma3 to local dev host (192.168.31.202) with PostgreSQL backend.
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-192.168.31.202}"
REMOTE_USER="${REMOTE_USER:-hct}"
REMOTE_DIR="${REMOTE_DIR:-/home/hct/ma3}"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${MA3_PORT:-8000}"
SSH="ssh -i ${HOME}/.ssh/id_rsa -o ConnectTimeout=15"
RSYNC_SSH="ssh -i ${HOME}/.ssh/id_rsa"

RSYNC_EXCLUDES=(
  --exclude '.git'
  --exclude '.venv'
  --exclude '__pycache__'
  --exclude '*.pyc'
  --exclude '.pytest_cache'
  --exclude 'node_modules'
  --exclude '.env'
  --exclude 'eval/secrets/*.env'
  --exclude 'eval/secrets/mihomo'
  --exclude 'eval/results'
)

echo "==> Syncing ${LOCAL_DIR} -> ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}"
rsync -avz -e "$RSYNC_SSH" --delete "${RSYNC_EXCLUDES[@]}" \
  "${LOCAL_DIR}/" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"

echo "==> PostgreSQL + venv + uvicorn on port ${PORT}"
$SSH "${REMOTE_USER}@${REMOTE_HOST}" bash -s <<REMOTE
set -euo pipefail
cd "${REMOTE_DIR}"

chmod +x deploy/setup_postgres_local.sh
DATABASE_URL=\$(bash deploy/setup_postgres_local.sh)

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r server/requirements.txt

mkdir -p "${REMOTE_DIR}/data/ops" "${REMOTE_DIR}/data/hf-cache"

chmod +x "${REMOTE_DIR}/deploy/prewarm_embedding_model.sh"
bash "${REMOTE_DIR}/deploy/prewarm_embedding_model.sh"

cat > "${REMOTE_DIR}/ma3.env" <<ENV
MA3_API_VERSION=v4
MA3_DEV_AUTH=1
MA3_PORT=${PORT}
MA3_OP_LOG_DIR=${REMOTE_DIR}/data/ops
MA3_DATA_DIR=${REMOTE_DIR}/data
MA3_HF_HOME=${REMOTE_DIR}/data/hf-cache
MA3_DATABASE_URL=\${DATABASE_URL}
ENV

if pgrep -f "uvicorn app.main:app.*--port ${PORT}" >/dev/null 2>&1; then
  pkill -f "uvicorn app.main:app.*--port ${PORT}" || true
  sleep 2
fi

set -a
. "${REMOTE_DIR}/ma3.env"
set +a

nohup .venv/bin/python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port ${PORT} \
  --app-dir server \
  > /tmp/ma3-uvicorn.log 2>&1 &
echo \$! > ma3.pid

sleep 4
curl -sf "http://127.0.0.1:${PORT}/healthz" | head -c 300
echo
curl -sf "http://127.0.0.1:${PORT}/v2/doctor" | python3 -c "import sys,json; d=json.load(sys.stdin); print('db=', d.get('database_backend'))"
REMOTE

echo "==> Done. curl http://${REMOTE_HOST}:${PORT}/healthz"
