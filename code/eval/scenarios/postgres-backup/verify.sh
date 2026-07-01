#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
CID=$(docker compose -f "$D/docker-compose.yml" ps -q backup)
[[ -n "$CID" ]] || { echo "backup container not running"; exit 1; }
docker exec "$CID" sh /workspace/backup.sh
docker exec "$CID" grep -q seed-row /backup/dump.sql
echo verify ok
