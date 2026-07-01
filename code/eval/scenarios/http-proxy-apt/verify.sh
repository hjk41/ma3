#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
CID=$(docker compose -f "$D/docker-compose.yml" ps -q client)
[[ -n "$CID" ]] || { echo "client container not running"; exit 1; }
for i in $(seq 1 10); do
  if docker exec "$CID" sh -c '. /workspace/env.sh && curl -4sf -m 20 http://example.com/ >/dev/null'; then
    echo verify ok
    exit 0
  fi
  sleep 2
done
echo "http-proxy-apt curl failed"
exit 1
