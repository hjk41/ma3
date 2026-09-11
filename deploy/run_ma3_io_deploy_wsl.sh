#!/usr/bin/env bash
# Windows/WSL helper: stage LF-normalized tree, then deploy to ma3.io.
set -euo pipefail

SRC=/mnt/c/doc/ma3
if [[ ! -d "${SRC}" ]]; then
  SRC="$(cd "$(dirname "$0")/.." && pwd)"
fi

STAGE="$(mktemp -d /tmp/ma3_stage.XXXXXX)"
TMP="$(mktemp -d /tmp/ma3_deploy_wrap.XXXXXX)"
cleanup() { rm -rf "${STAGE}" "${TMP}"; }
trap cleanup EXIT

echo "==> staging LF-normalized tree at ${STAGE}"
rsync -a \
  --exclude '.git' --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
  --exclude '.pytest_cache' --exclude 'server/data' --exclude 'data/hf-cache' \
  --exclude 'deploy/deploy.*.env' --exclude 'ma3.env' \
  "${SRC}/" "${STAGE}/"

# Normalize line endings for shell/env that the remote will execute.
find "${STAGE}" \( -name '*.sh' -o -name '*.bash' -o -name '*.env' -o -name '*.env.sample' \) \
  -type f -print0 | while IFS= read -r -d '' f; do
  tr -d '\r' < "${f}" > "${f}.lf" && mv "${f}.lf" "${f}"
done

tr -d '\r' < "${SRC}/deploy/deploy.sh" > "${TMP}/deploy.sh"
tr -d '\r' < "${SRC}/deploy/deploy.ma3.io.env" > "${TMP}/deploy.ma3.io.env"
chmod +x "${TMP}/deploy.sh"
sed -i "s|^SCRIPT_DIR=.*|SCRIPT_DIR=${STAGE}/deploy|" "${TMP}/deploy.sh"
sed -i "s|^REPO_DIR=.*|REPO_DIR=${STAGE}|" "${TMP}/deploy.sh"

export SSH_KEY="${SSH_KEY:-${HOME}/.ssh/id_rsa}"
echo "==> deploying staged tree to ma3.io (SSH_KEY=${SSH_KEY})"
bash "${TMP}/deploy.sh" "${TMP}/deploy.ma3.io.env"
