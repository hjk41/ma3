#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"

if [[ ! -f "$D/docker-compose.yml" ]]; then
  echo "missing docker-compose.yml" >&2
  exit 1
fi

(
  cd "$D"
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
  docker compose up -d --build
)

for i in $(seq 1 20); do
  if env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
    curl -sf -m 5 http://127.0.0.1:18082/ 2>/dev/null | grep -q hello-from-trigger-p3; then
    echo verify ok
    exit 0
  fi
  sleep 1
done

echo "P3 verify fail: nginx not serving on :18082 (is http3 directive still present?)"
docker compose -f "$D/docker-compose.yml" logs --tail 20 web 2>&1 || true
exit 1
