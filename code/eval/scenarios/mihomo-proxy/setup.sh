#!/usr/bin/env bash
# Copy broken config into workspace and optionally fetch subscription proxies.
set -euo pipefail
SCENARIO_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$SCENARIO_DIR/workspace"
cp "$SCENARIO_DIR/broken/config.yaml" "$SCENARIO_DIR/workspace/config.yaml"

if [[ -n "${MIHOMO_SUBSCRIPTION_URL:-}" ]]; then
  echo "subscription URL provided (not logged)" >&2
  # Agent task: merge subscription into config — verify only checks port/listen
fi
