#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
CID="$(docker compose -f "$D/docker-compose.yml" ps -q client)"
if [[ -z "$CID" ]]; then
  echo "client container not running"
  exit 1
fi
for i in $(seq 1 30); do
  if docker exec "$CID" sh -c 'command -v iptables >/dev/null && command -v curl >/dev/null'; then
    break
  fi
  sleep 1
done
for i in $(seq 1 8); do
  if docker exec "$CID" sh -c 'sh /workspace/redirect.sh && curl -4sf -m 12 http://example.com/ >/dev/null'; then
    echo "verify ok"
    exit 0
  fi
  sleep 2
done
echo "transparent gateway curl failed"
exit 1
