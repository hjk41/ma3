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
export MA3_CLIENT_CONFIG="${HOME}/.ma3/ma3-client.env"

bash "${HOME}/.ma3/bin/sync_ma3_client.sh" sync
install -D -m 0644 "${HOME}/.ma3/policy/ma3-agent-policy.mdc" "${MA3_POLICY_RUNTIME}"
configure_agent_mcp

echo "upgraded agent=${AGENT_NAME} skill=$(jq -r .skill_bundle_version "${HOME}/.ma3/ma3-client.json")"

