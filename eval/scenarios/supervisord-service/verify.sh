#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
for i in $(seq 1 30); do
  if curl -sf -m 2 http://127.0.0.1:18082/hello 2>/dev/null | grep -q hello-supervisord; then
    echo verify ok
    exit 0
  fi
  sleep 1
done
echo "service not ready on :18082"
exit 1
