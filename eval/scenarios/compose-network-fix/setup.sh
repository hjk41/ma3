#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$D/workspace"
cp "$D/broken/default.conf" "$D/workspace/default.conf"
