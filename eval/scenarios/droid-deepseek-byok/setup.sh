#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$D/workspace/.factory"
cp "$D/broken/settings.json" "$D/workspace/.factory/settings.json"
