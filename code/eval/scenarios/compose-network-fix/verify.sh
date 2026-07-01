#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
for i in $(seq 1 15); do
  if curl -sf -m 10 http://127.0.0.1:18081/ 2>/dev/null | grep -q hello-from-compose-backend; then
    echo verify ok
    exit 0
  fi
  sleep 1
done
echo "frontend not reachable on :18081"
exit 1
