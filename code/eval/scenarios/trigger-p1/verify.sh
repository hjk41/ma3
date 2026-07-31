#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
export FACTORY_HOME="${FACTORY_HOME:-$D/workspace/.factory}"

if [[ "${MA3_TRIGGER_DRY_RUN:-0}" == "1" ]]; then
  echo "verify ok (dry run)"
  exit 0
fi

if command -v droid >/dev/null 2>&1 && [[ -f "$FACTORY_HOME/mcp.json" ]]; then
  if grep -q 'ma3' "$FACTORY_HOME/mcp.json" 2>/dev/null; then
    echo verify ok
    exit 0
  fi
fi

# Fallback: host-wide install (eval profile on 202)
if command -v droid >/dev/null 2>&1 && [[ -f "${HOME}/.factory/mcp.json" ]]; then
  if grep -q 'ma3' "${HOME}/.factory/mcp.json" 2>/dev/null; then
    echo verify ok
    exit 0
  fi
fi

echo "P1 verify fail: need droid CLI and ma3 entry in mcp.json (FACTORY_HOME or ~/.factory)"
exit 1
