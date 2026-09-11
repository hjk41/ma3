#!/usr/bin/env bash
# Windows/WSL helper: stage LF-normalized tree, deploy to LAN 202.
set -euo pipefail

SRC=/mnt/c/doc/ma3
STAGE="$(mktemp -d /tmp/ma3_stage.XXXXXX)"
TMP="$(mktemp -d /tmp/ma3_deploy_wrap.XXXXXX)"
cleanup() { rm -rf "${STAGE}" "${TMP}"; }
trap cleanup EXIT

echo "==> staging LF-normalized tree at ${STAGE}"
rsync -a \
  --exclude '.git' --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
  --exclude '.pytest_cache' --exclude 'server/data' --exclude 'data/hf-cache' \
  --exclude 'deploy/deploy.*.env' --exclude 'ma3.env' \
  --exclude 'data/' \
  "${SRC}/" "${STAGE}/"

find "${STAGE}" \( -name '*.sh' -o -name '*.bash' \) -type f -print0 \
  | while IFS= read -r -d '' f; do
      tr -d '\r' < "${f}" > "${f}.lf" && mv "${f}.lf" "${f}"
    done

tr -d '\r' < "${SRC}/deploy/deploy.sh" > "${TMP}/deploy.sh"
tr -d '\r' < "${SRC}/deploy/deploy.202.env" > "${TMP}/deploy.202.env"
chmod +x "${TMP}/deploy.sh"
sed -i "s|^SCRIPT_DIR=.*|SCRIPT_DIR=${STAGE}/deploy|" "${TMP}/deploy.sh"
sed -i "s|^REPO_DIR=.*|REPO_DIR=${STAGE}|" "${TMP}/deploy.sh"

export SSH_KEY="${SSH_KEY:-${HOME}/.ssh/id_rsa}"
echo "==> deploying staged tree to 202 (SSH_KEY=${SSH_KEY})"
bash "${TMP}/deploy.sh" "${TMP}/deploy.202.env"
