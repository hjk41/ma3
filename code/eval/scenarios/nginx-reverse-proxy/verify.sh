#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
for i in $(seq 1 15); do
  if curl -sf -m 5 http://127.0.0.1:18080/ 2>/dev/null | grep -q hello-from-backend; then
    echo verify ok
    exit 0
  fi
  sleep 1
done
echo "backend not reachable on :18080"
exit 1
