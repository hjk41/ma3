#!/usr/bin/env bash
# Register MCP + runtime policy using each agent's real CLI/config layout.
set -euo pipefail

configure_agent_mcp() {
  : "${AGENT_NAME:?}"
  : "${MA3_BASE_URL:?}"
  : "${HOME:?}"

  case "${AGENT_NAME}" in
    claude)
      command -v claude >/dev/null || { echo "FAIL: claude binary missing" >&2; exit 1; }
      claude mcp remove ma3 2>/dev/null || true
      claude mcp add --scope user --transport http ma3 \
        "${MA3_BASE_URL}/mcp" \
        --header "X-API-Key: ${MA3_API_KEY:-ma3dev}"
      ;;
    codex)
      command -v codex >/dev/null || { echo "FAIL: codex binary missing" >&2; exit 1; }
      mkdir -p "${HOME}/.codex"
      cat > "${HOME}/.codex/config.toml" <<EOF
[mcp_servers.ma3]
url = "${MA3_BASE_URL}/mcp"
enabled = true

[mcp_servers.ma3.http_headers]
X-API-Key = "${MA3_API_KEY:-ma3dev}"
EOF
      ;;
    cursor)
      if command -v cursor-agent >/dev/null; then
        CURSOR_BIN=cursor-agent
      elif command -v agent >/dev/null; then
        CURSOR_BIN=agent
      elif command -v cursor >/dev/null; then
        CURSOR_BIN=cursor
      else
        echo "FAIL: cursor-agent/agent/cursor binary missing" >&2
        exit 1
      fi
      mkdir -p "$(dirname "${MA3_MCP_JSON}")"
      cat > "${MA3_MCP_JSON}" <<EOF
{
  "mcpServers": {
    "ma3": {
      "url": "${MA3_BASE_URL}/mcp",
      "headers": { "X-API-Key": "${MA3_API_KEY:-ma3dev}" }
    }
  }
}
EOF
      "${CURSOR_BIN}" --version >/dev/null 2>&1 || "${CURSOR_BIN}" version >/dev/null 2>&1 || true
      ;;
    droid)
      command -v droid >/dev/null || { echo "FAIL: droid binary missing" >&2; exit 1; }
      mkdir -p "$(dirname "${MA3_MCP_JSON}")"
      cat > "${MA3_MCP_JSON}" <<EOF
{
  "mcpServers": {
    "ma3": {
      "type": "http",
      "url": "${MA3_BASE_URL}/mcp",
      "headers": { "X-API-Key": "${MA3_API_KEY:-ma3dev}" },
      "disabled": false
    }
  }
}
EOF
      droid --version >/dev/null 2>&1 || droid version >/dev/null 2>&1 || true
      ;;
    *)
      echo "FAIL: unknown agent ${AGENT_NAME}" >&2
      exit 1
      ;;
  esac
}

verify_agent_binary() {
  : "${AGENT_NAME:?}"
  : "${HOME:?}"
  : "${MA3_POLICY_RUNTIME:?}"

  case "${AGENT_NAME}" in
    claude)
      command -v claude >/dev/null
      claude --version >/dev/null 2>&1 || true
      claude mcp list 2>&1 | grep -qi ma3
      ;;
    codex)
      command -v codex >/dev/null
      codex --version >/dev/null 2>&1
      grep -q '^\[mcp_servers\.ma3\]' "${HOME}/.codex/config.toml"
      grep -q "${MA3_BASE_URL}/mcp" "${HOME}/.codex/config.toml"
      ;;
    cursor)
      if command -v cursor-agent >/dev/null; then
        cursor-agent --version >/dev/null 2>&1 || cursor-agent version >/dev/null 2>&1 || true
      elif command -v agent >/dev/null; then
        agent --version >/dev/null 2>&1 || agent version >/dev/null 2>&1 || true
      else
        cursor --version >/dev/null 2>&1 || true
      fi
      jq -e '.mcpServers.ma3.url' "${MA3_MCP_JSON}" >/dev/null
      ;;
    droid)
      command -v droid >/dev/null
      droid --version >/dev/null 2>&1 || droid version >/dev/null 2>&1 || true
      jq -e '.mcpServers.ma3.url' "${MA3_MCP_JSON}" >/dev/null
      ;;
    *)
      return 1
      ;;
  esac
}
