#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/configure_mcp.sh"

PROFILE="${1:?profile path required}"
EXPECTED_SKILL="${2:?expected skill version required}"
# shellcheck disable=SC1090
source "${PROFILE}"

AGENT_HOME="${AGENT_HOME:-${AGENTS_ROOT:-/agents}/${AGENT_NAME}/home}"
export HOME="${AGENT_HOME}"
export MA3_BASE_URL
resolve_agent_paths

STATE="${HOME}/.ma3/ma3-client.json"

[[ -f "${STATE}" ]] || { echo "FAIL ${AGENT_NAME}: missing state ${STATE}" >&2; exit 1; }
[[ -f "${MA3_POLICY_RUNTIME}" ]] || { echo "FAIL ${AGENT_NAME}: missing runtime policy ${MA3_POLICY_RUNTIME}" >&2; exit 1; }
[[ -f "${HOME}/.ma3/bin/sync_ma3_client.sh" ]] || { echo "FAIL ${AGENT_NAME}: missing sync script" >&2; exit 1; }
[[ -f "${HOME}/.ma3/mcp-tools.json" ]] || { echo "FAIL ${AGENT_NAME}: missing mcp-tools cache" >&2; exit 1; }

ACTUAL_SKILL="$(jq -r .skill_bundle_version "${STATE}")"
if [[ "${ACTUAL_SKILL}" != "${EXPECTED_SKILL}" ]]; then
  echo "FAIL ${AGENT_NAME}: skill_bundle_version=${ACTUAL_SKILL} expected=${EXPECTED_SKILL}" >&2
  exit 1
fi

grep -q "ma3 agent policy" "${MA3_POLICY_RUNTIME}" || {
  echo "FAIL ${AGENT_NAME}: policy content missing at ${MA3_POLICY_RUNTIME}" >&2
  exit 1
}

verify_agent_binary || {
  echo "FAIL ${AGENT_NAME}: real binary / MCP verification failed" >&2
  exit 1
}

echo "OK ${AGENT_NAME} skill=${ACTUAL_SKILL} policy=${MA3_POLICY_RUNTIME} binary=verified"

