#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$D/workspace/.claude"
cp "$D/broken/settings.json" "$D/workspace/.claude/settings.json"
