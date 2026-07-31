#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$D/workspace/.factory"
export FACTORY_HOME="$D/workspace/.factory"
# Start clean so agent must install/configure (not reuse host ~/.factory).
rm -f "$FACTORY_HOME/settings.json" "$FACTORY_HOME/mcp.json" 2>/dev/null || true
echo "FACTORY_HOME=$FACTORY_HOME"
