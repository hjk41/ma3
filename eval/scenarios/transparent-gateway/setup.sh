#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$D/workspace"
cp "$D/broken/redirect.sh" "$D/workspace/redirect.sh"
chmod +x "$D/workspace/redirect.sh"
