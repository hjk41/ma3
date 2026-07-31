#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
EVAL_ROOT="$(cd "$D/../.." && pwd)"
WRAP="$EVAL_ROOT/scenarios/compose-network-fix"

bash "$WRAP/setup.sh"
if [[ -f "$WRAP/docker-compose.yml" ]]; then
  (
    cd "$WRAP"
    docker compose down -v --remove-orphans >/dev/null 2>&1 || true
    docker compose up -d --build
  )
  sleep 2
fi
