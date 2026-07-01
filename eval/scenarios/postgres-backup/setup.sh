#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$D/workspace"
cp "$D/broken/backup.sh" "$D/workspace/backup.sh"
chmod +x "$D/workspace/backup.sh"
