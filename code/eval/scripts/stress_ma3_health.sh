#!/usr/bin/env bash
# Stress-test ma3 healthz while embedding backfill may be running.
set -euo pipefail
BASE="${MA3_BASE_URL:-http://127.0.0.1:8000}"
FAIL=0
for i in $(seq 1 "${1:-30}"); do
  if ! curl -sf -m 2 "${BASE}/healthz" >/dev/null; then
    echo "FAIL healthz attempt $i"
    FAIL=$((FAIL + 1))
  fi
done
echo "failures=$FAIL / $1"
exit $(( FAIL > 0 ? 1 : 0 ))
