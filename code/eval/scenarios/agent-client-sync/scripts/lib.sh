#!/usr/bin/env bash
# Resolve agent paths from profile (call after setting HOME).
set -euo pipefail

resolve_agent_paths() {
  : "${AGENT_NAME:?AGENT_NAME required}"
  : "${RUNTIME_POLICY_REL:?RUNTIME_POLICY_REL required}"
  MA3_POLICY_RUNTIME="${HOME}/${RUNTIME_POLICY_REL}"
  if [[ -n "${MA3_MCP_JSON_REL:-}" ]]; then
    MA3_MCP_JSON="${HOME}/${MA3_MCP_JSON_REL}"
  else
    MA3_MCP_JSON=""
  fi
}
