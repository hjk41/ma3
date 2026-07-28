#!/usr/bin/env bash
# Start the self-host stack from deploy/self-host/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example — edit secrets before production use."
fi

# shellcheck disable=SC1091
set -a
# Export MA3_PORT / compose vars for health check messaging
source .env
set +a

docker compose up -d --build "$@"
echo
echo "Waiting for healthz..."
PORT="${MA3_PORT:-8000}"
for i in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1; then
    echo "ma3 is up: http://127.0.0.1:${PORT}/healthz"
    echo "First-run setup (local auth): http://127.0.0.1:${PORT}/ui/setup/"
    echo "Bootstrap key (if OIDC off): docker compose exec ma3 cat /data/bootstrap_api_key.txt"
    exit 0
  fi
  sleep 3
done
echo "Timed out waiting for /healthz — check: docker compose logs ma3" >&2
exit 1
