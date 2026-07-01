#!/usr/bin/env bash
# Deploy ma3_v1 to 192.168.31.202: stop legacy :8000, migrate in-place, start v1.
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-192.168.31.202}"
REMOTE_USER="${REMOTE_USER:-hct}"
REMOTE_DIR="${REMOTE_DIR:-/home/hct/ma3_v1}"
LEGACY_DIR="${LEGACY_DIR:-/home/hct/ma3}"
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
  --exclude 'server/data'
  --exclude 'server/.venv'
  --filter 'P ma3.env'
  --filter 'P ma3.pid'
  --filter 'P data/'
)

echo "==> Sync ma3_v1 -> ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}"
rsync -avz -e "$RSYNC_SSH" --delete "${RSYNC_EXCLUDES[@]}" \
  "${LOCAL_DIR}/" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"

echo "==> Remote: stop legacy, deploy v1, migrate in-place"
$SSH "${REMOTE_USER}@${REMOTE_HOST}" bash -s <<REMOTE
set -euo pipefail
LEGACY_DIR="${LEGACY_DIR}"
REMOTE_DIR="${REMOTE_DIR}"
PORT="${PORT}"

set -a
source "\${LEGACY_DIR}/ma3.env"
set +a

echo "==> Stop legacy uvicorn on port \${PORT}"
pkill -f "uvicorn app.main:app.*--port \${PORT}" || true
sleep 2

cd "\${REMOTE_DIR}/code/server"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

mkdir -p "\${REMOTE_DIR}/data"
if [[ -d "\${LEGACY_DIR}/data/hf-cache" ]]; then
  ln -sfn "\${LEGACY_DIR}/data/hf-cache" "\${REMOTE_DIR}/data/hf-cache"
fi

cat > "\${REMOTE_DIR}/ma3.env" <<ENV
MA3_DEV_AUTH=1
MA3_DEV_API_KEY=ma3dev
MA3_PORT=\${PORT}
MA3_DATABASE_URL=\${MA3_DATABASE_URL}
MA3_DISABLE_EMBEDDINGS=1
MA3_INSTANCE_ID=ma3-v1-202
MA3_HF_HOME=\${LEGACY_DIR}/data/hf-cache
HF_HUB_OFFLINE=1
ENV

echo "==> Migrate legacy tables to v1 schema in same DB"
export MA3_DATABASE_URL="\${MA3_DATABASE_URL}"
export MA3_MIGRATE_RENAME=1
.venv/bin/python scripts/migrate_legacy_pg.py

echo "==> Start ma3_v1 uvicorn"
set -a
source "\${REMOTE_DIR}/ma3.env"
set +a
nohup .venv/bin/python -m uvicorn app.main:app \
  --host 0.0.0.0 --port "\${PORT}" --app-dir . \
  > /tmp/ma3-v1-uvicorn.log 2>&1 &
echo \$! > "\${REMOTE_DIR}/ma3.pid"
sleep 4

echo "==> healthz"
curl -sf "http://127.0.0.1:\${PORT}/healthz" | python3 -m json.tool

echo "==> Integration verification"
export MA3_BASE_URL="http://127.0.0.1:\${PORT}"
export MA3_API_KEY=ma3dev
export MA3_EXPECT_INSTANCE_ID=ma3-v1-202
export MA3_EXPECT_MIN_RECORDS=30
export MA3_EXPECT_MIN_CASES=20
export MA3_EXPECT_MIN_MIHOMO_HITS=1
export MA3_EXPECT_MIN_LIBRARIES=2
bash "\${REMOTE_DIR}/deploy/verify_ma3_v1.sh"
REMOTE

echo "==> Done: http://${REMOTE_HOST}:${PORT}/healthz"
