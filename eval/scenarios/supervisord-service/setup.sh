#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$D/workspace"
cp "$D/broken/app.py" "$D/workspace/app.py"
cp "$D/broken/supervisord.conf" "$D/workspace/supervisord.conf"
