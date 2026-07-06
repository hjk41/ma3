#!/usr/bin/env bash
# Sync eval to 202 and run all 10 scenario verify scripts (golden path).
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-192.168.31.202}"
REMOTE_USER="${REMOTE_USER:-hct}"
REMOTE_DIR="${REMOTE_DIR:-/home/hct/ma3_deploy}"
LOCAL_EVAL="$(cd "$(dirname "$0")/../code/eval" && pwd)"
SSH="ssh -i ${HOME}/.ssh/id_rsa -o ConnectTimeout=30"

echo "==> rsync eval -> ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/code/eval"
rsync -avz -e "ssh -i ${HOME}/.ssh/id_rsa" \
  --exclude 'results/*' --exclude 'secrets/*.env' \
  "$LOCAL_EVAL/" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/code/eval/"

echo "==> run all scenario verifies on 202"
$SSH "${REMOTE_USER}@${REMOTE_HOST}" bash -s <<REMOTE
set -euo pipefail
# secrets from legacy path if not copied
if [[ ! -f /home/hct/ma3_deploy/code/eval/secrets/secrets.env ]]; then
  mkdir -p /home/hct/ma3_deploy/code/eval/secrets
  cp /home/hct/ma3/eval/secrets/secrets.env /home/hct/ma3_deploy/code/eval/secrets/ 2>/dev/null || true
  cp /home/hct/ma3/eval/secrets/agent-keys.env /home/hct/ma3_deploy/code/eval/secrets/ 2>/dev/null || true
fi
cd /home/hct/ma3_deploy/code/eval/scripts
chmod +x *.sh
export HTTP_PROXY="\${HTTP_PROXY:-http://192.168.31.200:1080}"
export HTTPS_PROXY="\${HTTPS_PROXY:-http://192.168.31.200:1080}"
bash run_all_scenarios_verify.sh
REMOTE

echo "==> all scenarios passed on 202"
