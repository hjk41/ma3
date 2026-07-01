#!/usr/bin/env bash
# Run one scenario: setup (broken) -> golden fix -> compose up -> verify -> down.
set -euo pipefail

EVAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$EVAL_ROOT/scripts/load_secrets.sh"

SCENARIO="${1:?scenario id required}"
SCENARIO_DIR="$EVAL_ROOT/scenarios/$SCENARIO"
KEEP_UP="${KEEP_UP:-0}"

[[ -d "$SCENARIO_DIR" ]] || { echo "missing scenario: $SCENARIO" >&2; exit 1; }

cleanup() {
  if [[ "$KEEP_UP" == "1" ]]; then
    return
  fi
  if [[ -f "$SCENARIO_DIR/docker-compose.yml" ]]; then
    (cd "$SCENARIO_DIR" && docker compose down -v --remove-orphans) >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "======== scenario: $SCENARIO ========"
cd "$SCENARIO_DIR"

if [[ -x setup.sh ]]; then
  bash setup.sh
fi

bash "$EVAL_ROOT/scripts/apply_golden_fix.sh" "$SCENARIO"

if [[ -f docker-compose.yml ]]; then
  export MIHOMO_SUBSCRIPTION_URL="${MIHOMO_SUBSCRIPTION_URL:-}"
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
  up_ok=0
  for _attempt in 1 2 3; do
    if docker compose up -d --build; then
      up_ok=1
      break
    fi
    sleep 3
  done
  if [[ "$up_ok" != "1" ]]; then
    echo "docker compose up failed for $SCENARIO" >&2
    exit 1
  fi
  case "$SCENARIO" in
    ssh-key-only|supervisord-service|transparent-gateway|mihomo-proxy)
      sleep 8
      ;;
    *)
      sleep 2
      ;;
  esac
fi

bash verify.sh
echo "PASS: $SCENARIO"
