#!/usr/bin/env bash
set -euo pipefail
SCENARIO_DIR="$(cd "$(dirname "$0")" && pwd)"
CID=$(docker compose -f "$SCENARIO_DIR/docker-compose.yml" ps -q client)
[[ -n "$CID" ]] || { echo "client container not running"; exit 1 }
# mixed-port must listen — broken config may use wrong port
docker exec "$CID" curl -sf -m 10 -x http://mihomo:7890 http://httpbin.org/get >/dev/null
echo "verify ok"
