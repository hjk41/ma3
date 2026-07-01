#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/configure_mcp.sh"

PROFILE="${1:?profile path required}"
# shellcheck disable=SC1090
source "${PROFILE}"

AGENT_HOME="${AGENT_HOME:-${AGENTS_ROOT:-/agents}/${AGENT_NAME}/home}"
export HOME="${AGENT_HOME}"
export MA3_BASE_URL
resolve_agent_paths

mkdir -p "${HOME}/.ma3/bin" "${HOME}/.ma3/lib"
mkdir -p "$(dirname "${MA3_POLICY_RUNTIME}")"

ENV_FILE="${HOME}/.ma3/ma3-client.env"
curl -fsSL "${MA3_BASE_URL}/client/templates/ma3-client.env.example" -o "${ENV_FILE}.tmp"
sed -i "s|^MA3_BASE_URL=.*|MA3_BASE_URL=${MA3_BASE_URL}|" "${ENV_FILE}.tmp"
mv "${ENV_FILE}.tmp" "${ENV_FILE}"

curl -fsSL "${MA3_BASE_URL}/client/scripts/sync_ma3_client.py" -o "${HOME}/.ma3/bin/sync_ma3_client.py"
curl -fsSL "${MA3_BASE_URL}/client/lib/ma3_sync_core.py" -o "${HOME}/.ma3/lib/ma3_sync_core.py"
curl -fsSL "${MA3_BASE_URL}/client/scripts/sync_ma3_client.sh" -o "${HOME}/.ma3/bin/sync_ma3_client.sh"
chmod +x "${HOME}/.ma3/bin/sync_ma3_client.sh"

export MA3_CLIENT_CONFIG="${ENV_FILE}"
bash "${HOME}/.ma3/bin/sync_ma3_client.sh" sync

install -D -m 0644 "${HOME}/.ma3/policy/ma3-agent-policy.mdc" "${MA3_POLICY_RUNTIME}"

configure_agent_mcp

echo "installed agent=${AGENT_NAME} home=${HOME} policy=${MA3_POLICY_RUNTIME}"

