#!/usr/bin/env bash
# Install isolated agent profiles under /home/hct/ma3-eval/profiles (not in git).
# Reads API keys from eval/secrets/agent-keys.env
set -euo pipefail

EVAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$EVAL_ROOT/scripts/load_secrets.sh"

PROFILE_ROOT="${EVAL_PROFILE_ROOT:-/home/hct/ma3-eval/profiles}"
MA3_MCP_URL="${MA3_BASE_URL:-http://127.0.0.1:8000}/mcp"

mkdir -p "$PROFILE_ROOT"/{claude/.claude,droid/.claude,droid/.factory,cursor/.claude,cursor/.cursor}

CLAUDE_SETTINGS=$(cat <<EOF
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
    "ANTHROPIC_AUTH_TOKEN": "${DEEPSEEK_API_KEY}",
    "ANTHROPIC_MODEL": "deepseek-v4-pro[1m]",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "deepseek-v4-pro[1m]",
    "CLAUDE_CODE_SUBAGENT_MODEL": "deepseek-v4-flash",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"
  }
}
EOF
)

for agent in claude droid cursor; do
  mkdir -p "$PROFILE_ROOT/$agent/.claude"
  echo "$CLAUDE_SETTINGS" > "$PROFILE_ROOT/$agent/.claude/settings.json"
done

# Legacy path for claude-only reference
echo "$CLAUDE_SETTINGS" > "$PROFILE_ROOT/claude/.claude/settings.json"

# Droid BYOK (requires FACTORY_API_KEY for platform auth; BYOK model when logged in)
cat > "$PROFILE_ROOT/droid/.factory/settings.json" <<EOF
{
  "model": "deepseek-v4-pro",
  "customModels": [{
    "model": "deepseek-v4-pro",
    "displayName": "DeepSeek V4 Pro",
    "baseUrl": "https://api.deepseek.com/v1",
    "apiKey": "${DEEPSEEK_API_KEY}",
    "provider": "generic-chat-completion-api",
    "extraArgs": { "thinking": { "type": "disabled" } }
  }]
}
EOF

# Cursor CLI MCP
cat > "$PROFILE_ROOT/cursor/.cursor/mcp.json" <<EOF
{
  "mcpServers": {
    "ma3": {
      "url": "${MA3_MCP_URL}",
      "headers": { "X-API-Key": "${MA3_KEY_CURSOR_CLI}" }
    }
  }
}
EOF

cat > "$PROFILE_ROOT/droid/.factory/mcp.json" <<EOF
{
  "mcpServers": {
    "ma3": {
      "type": "http",
      "url": "${MA3_MCP_URL}",
      "headers": { "X-API-Key": "${MA3_KEY_DROID}" },
      "disabled": false
    }
  }
}
EOF

POLICY="$(cat "$EVAL_ROOT/templates/MA3_AGENT_POLICY.md" 2>/dev/null || true)"
if [[ -n "$POLICY" ]]; then
  cp "$EVAL_ROOT/templates/MA3_AGENT_POLICY.md" "$PROFILE_ROOT/claude/.claude/CLAUDE.md"
  cp "$EVAL_ROOT/templates/MA3_AGENT_POLICY.md" "$PROFILE_ROOT/droid/.factory/AGENTS.md"
fi

mkdir -p "$PROFILE_ROOT/cursor/.cursor"
cat > "$PROFILE_ROOT/cursor/.cursor/cli-config.json" <<EOF
{
  "permissions": {
    "allow": ["Shell(**)", "Mcp(ma3, **)"]
  },
  "model": {
    "baseUrl": "http://127.0.0.1:9000/v1",
    "apiKey": "${DEEPSEEK_API_KEY}",
    "modelId": "deepseek-chat"
  }
}
EOF

echo "Profiles written under $PROFILE_ROOT"
if command -v claude >/dev/null 2>&1; then
  for agent_key_label in "claude:MA3_KEY_CLAUDE_CODE" "droid:MA3_KEY_DROID" "cursor:MA3_KEY_CURSOR_CLI"; do
    agent="${agent_key_label%%:*}"
    key_var="${agent_key_label##*:}"
    eval "key=\${${key_var}:-}"
    [[ -z "$key" ]] && continue
    export HOME="$PROFILE_ROOT/$agent"
    claude mcp remove ma3 2>/dev/null || true
    claude mcp add --scope user --transport http ma3 "$MA3_MCP_URL" \
      --header "X-API-Key: ${key}" 2>/dev/null || true
  done
  export HOME="$PROFILE_ROOT/claude"
fi
