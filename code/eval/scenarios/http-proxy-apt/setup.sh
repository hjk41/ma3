#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$D/workspace"
cp "$D/broken/env.sh" "$D/workspace/env.sh"
