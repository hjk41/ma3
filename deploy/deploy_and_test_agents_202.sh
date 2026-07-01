#!/usr/bin/env bash
# Deploy latest ma3_v1 to 202, then run Docker agent test (host ma3 + real CLIs in containers).
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-192.168.31.202}"
REMOTE_USER="${REMOTE_USER:-hct}"
REMOTE_DIR="${REMOTE_DIR:-/home/hct/ma3_v1}"
MA3_PORT="${MA3_PORT:-8000}"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SSH="ssh -i ${HOME}/.ssh/id_rsa -o ConnectTimeout=30"
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

echo "==> Remote: ensure ma3 deps + run docker agent test (ma3 stays on host)"
$SSH "${REMOTE_USER}@${REMOTE_HOST}" bash -s <<REMOTE
set -euo pipefail
REMOTE_DIR="${REMOTE_DIR}"
PORT="${MA3_PORT}"
LEGACY_DIR="/home/hct/ma3"

if [[ -f "\${LEGACY_DIR}/ma3.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "\${LEGACY_DIR}/ma3.env"
  set +a
fi

cd "\${REMOTE_DIR}/code/server"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo "==> Docker agent-client-sync (host ma3 at :${MA3_PORT})"
cd "\${REMOTE_DIR}/code/eval/scenarios/agent-client-sync"
chmod +x run.sh scripts/*.sh
export DOCKER_BUILDKIT=1
export HTTP_PROXY="\${HTTP_PROXY:-http://192.168.31.200:1080}"
export HTTPS_PROXY="\${HTTPS_PROXY:-http://192.168.31.200:1080}"
bash run.sh
REMOTE

echo "==> Done: http://${REMOTE_HOST}:${MA3_PORT} (restored to MA3_RESTORE_VERSION)"
