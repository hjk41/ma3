#!/usr/bin/env bash
# Bootstrap ~/.ma3 client sync for one eval agent profile (claude|droid|cursor|codex).
# Pulls policy + tooling from the live ma3 server and installs into the agent HOME.
set -euo pipefail

EVAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "${EVAL_ROOT}/scripts/load_secrets.sh"

AGENT="${1:?agent required: claude|droid|cursor|codex}"
PROFILE_ROOT="${EVAL_PROFILE_ROOT:-$HOME/ma3-eval/profiles}"
MA3_BASE_URL="${MA3_BASE_URL:-http://127.0.0.1:8000}"
AGENT_HOME="${PROFILE_ROOT}/${AGENT}"

case "${AGENT}" in
  claude)
    POLICY_RUNTIME="${AGENT_HOME}/.claude/CLAUDE.md"
    ;;
  droid)
    POLICY_RUNTIME="${AGENT_HOME}/.factory/AGENTS.md"
    mkdir -p "${AGENT_HOME}/.factory"
    ;;
  cursor)
    POLICY_RUNTIME="${AGENT_HOME}/.cursor/rules/ma3-agent-policy.mdc"
    mkdir -p "${AGENT_HOME}/.cursor/rules"
    ;;
  codex)
    POLICY_RUNTIME="${AGENT_HOME}/.codex/model_instructions.md"
    mkdir -p "${AGENT_HOME}/.codex"
    ;;
  hermes)
    # Hermes auto-loads rules from $HERMES_HOME/rules/*.md
    POLICY_RUNTIME="${AGENT_HOME}/.hermes/rules/ma3-agent-policy.md"
    mkdir -p "${AGENT_HOME}/.hermes/rules"
    ;;
  *)
    echo "unknown agent: ${AGENT}" >&2
    exit 1
    ;;
esac

export HOME="${AGENT_HOME}"
mkdir -p "${HOME}/.ma3/bin" "${HOME}/.ma3/lib"
mkdir -p "$(dirname "${POLICY_RUNTIME}")"

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

install -D -m 0644 "${HOME}/.ma3/policy/ma3-agent-policy.mdc" "${POLICY_RUNTIME}"

echo "bootstrapped agent=${AGENT} home=${HOME} policy=${POLICY_RUNTIME} skill=$(jq -r .skill_bundle_version "${HOME}/.ma3/ma3-client.json")"
