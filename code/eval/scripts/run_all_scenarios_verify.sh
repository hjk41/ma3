#!/usr/bin/env bash
# Verify all 10 infra eval scenarios (golden fix path, no agent required).
set -euo pipefail

EVAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNNER="$EVAL_ROOT/scripts/run_scenario_verify.sh"

SCENARIOS=(
  mihomo-proxy
  compose-network-fix
  nginx-reverse-proxy
  http-proxy-apt
  postgres-backup
  ssh-key-only
  supervisord-service
  transparent-gateway
  claude-deepseek-byok
  droid-deepseek-byok
)

ONLY="${1:-}"
PASSED=0
FAILED=0
FAIL_LIST=()

run_one() {
  local s="$1"
  if bash "$RUNNER" "$s"; then
    PASSED=$((PASSED + 1))
  else
    FAILED=$((FAILED + 1))
    FAIL_LIST+=("$s")
  fi
}

if [[ -n "$ONLY" ]]; then
  run_one "$ONLY"
else
  for s in "${SCENARIOS[@]}"; do
    run_one "$s" || true
  done
fi

echo ""
echo "======== summary ========"
echo "passed: $PASSED  failed: $FAILED"
if [[ ${#FAIL_LIST[@]} -gt 0 ]]; then
  echo "failed: ${FAIL_LIST[*]}"
  exit 1
fi
echo "all scenarios verified"
exit 0
