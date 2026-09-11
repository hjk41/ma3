#!/usr/bin/env bash
# Thin launcher — logic lives in probe_ma3.py (Linux/macOS/Windows).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec python3 "${ROOT}/probe_ma3.py" "$@"
