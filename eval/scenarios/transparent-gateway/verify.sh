#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
CID=$(docker compose -f "$D/docker-compose.yml" ps -q client)
[[ -n "$CID" ]] || { echo "client container not running"; exit 1; }
docker exec "$CID" sh -c 'sh /workspace/redirect.sh && curl -sf -m 20 http://httpbin.org/get >/dev/null'
echo verify ok
