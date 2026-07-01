#!/usr/bin/env bash
# ma3 client sync wrapper — sources YOUR local ma3-client.env (agent fills at onboarding).
set -euo pipefail

CONFIG="${MA3_CLIENT_CONFIG:-${HOME}/.ma3/ma3-client.env}"
if [[ -f "${CONFIG}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${CONFIG}"
  set +a
fi

BIN_DIR="${MA3_BIN_DIR:-${HOME}/.ma3/bin}"
LIB_DIR="${MA3_LIB_DIR:-${HOME}/.ma3/lib}"
PY="${MA3_SYNC_PYTHON:-python3}"
SCRIPT="${BIN_DIR}/sync_ma3_client.py"

if [[ ! -f "${SCRIPT}" ]]; then
  echo "ERROR: ${SCRIPT} not found. Bootstrap from server:" >&2
  echo "  mkdir -p \"${BIN_DIR}\" \"${LIB_DIR}\"" >&2
  echo "  curl -fsSL \"\${MA3_BASE_URL}/client/scripts/sync_ma3_client.py\" -o \"${SCRIPT}\"" >&2
  echo "  curl -fsSL \"\${MA3_BASE_URL}/client/lib/ma3_sync_core.py\" -o \"${LIB_DIR}/ma3_sync_core.py\"" >&2
  exit 1
fi

exec "${PY}" "${SCRIPT}" "$@"
