#!/usr/bin/env bash
set -euo pipefail
SCENARIO_DIR="$(cd "$(dirname "$0")" && pwd)"
CID="$(docker compose -f "$SCENARIO_DIR/docker-compose.yml" ps -q client)"
if [[ -z "$CID" ]]; then
  echo "client container not running"
  exit 1
fi
# Wait for mihomo mixed-port; use example.com (httpbin often 503 via direct stub)
for i in $(seq 1 20); do
  if docker exec "$CID" curl -sf -m 15 -x "http://mihomo:7890" "http://example.com/" >/dev/null 2>&1; then
    echo "verify ok"
    exit 0
  fi
  sleep 1
done
echo "proxy curl failed"
exit 1
