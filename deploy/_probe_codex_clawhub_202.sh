#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH:$HOME/.npm-global/bin:/usr/local/bin"
echo "== which =="
command -v codex || ls -la "$HOME/.local/bin/codex"
command -v clawhub || true
command -v openclaw || true
command -v npm || true
echo "== config redacted =="
if [[ -f "$HOME/.codex/config.toml" ]]; then
  sed -E 's/(X-API-Key = ).*/\1REDACTED/' "$HOME/.codex/config.toml"
fi
echo "== mcp list =="
codex mcp list 2>&1 | head -50 || true
echo "== env flags =="
[[ -n "${MA3_API_KEY:-}" ]] && echo MA3_API_KEY=set || echo MA3_API_KEY=missing
[[ -n "${DEEPSEEK_API_KEY:-}" ]] && echo DEEPSEEK_API_KEY=set || echo DEEPSEEK_API_KEY=missing
echo "== clawhub whoami =="
clawhub whoami 2>&1 || echo "clawhub not logged in / missing"
echo "== openclaw version =="
openclaw --version 2>&1 || echo "openclaw missing"
