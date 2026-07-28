#!/usr/bin/env bash
# Live verification for Compose self-host (bootstrap API key, no OIDC).
# Usage (from repo):
#   bash deploy/self-host/verify_integration.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE_DIR="${ROOT}/deploy/self-host"
SERVER_DIR="${ROOT}/code/server"

cd "${COMPOSE_DIR}"
# Prefer explicit self-host target; do not inherit a stale MA3_BASE_URL (e.g. ma3.io).
export MA3_PORT="${MA3_PORT:-8010}"
if [[ -z "${MA3_SELFHOST_BASE_URL:-}" ]]; then
  export MA3_BASE_URL="http://127.0.0.1:${MA3_PORT}"
else
  export MA3_BASE_URL="${MA3_SELFHOST_BASE_URL}"
fi
# Drop inherited production gates unless the caller opts in.
if [[ -z "${MA3_SELFHOST_KEEP_EXPECT:-}" ]]; then
  unset MA3_EXPECT_MIN_RECORDS MA3_EXPECT_MIN_CASES \
    MA3_EXPECT_MIN_MIHOMO_HITS MA3_EXPECT_MIN_NGINX_HITS \
    MA3_EXPECT_MIN_LIBRARIES MA3_EXPECT_CALLER_TYPE \
    MA3_EXPECT_INSTANCE_ID MA3_EXPECT_FEATURES || true
fi
export MA3_EXPECT_INSTANCE_ID="${MA3_EXPECT_INSTANCE_ID:-ma3-selfhost-202}"
export MA3_EXPECT_CALLER_TYPE="${MA3_EXPECT_CALLER_TYPE:-api_key}"
# Fresh greenfield instances start at 0 records; raise after seeding if desired.
export MA3_EXPECT_MIN_RECORDS="${MA3_EXPECT_MIN_RECORDS:-0}"
export MA3_EXPECT_MIN_CASES="${MA3_EXPECT_MIN_CASES:-0}"
export MA3_EXPECT_MIN_MIHOMO_HITS="${MA3_EXPECT_MIN_MIHOMO_HITS:-0}"
export MA3_EXPECT_MIN_NGINX_HITS="${MA3_EXPECT_MIN_NGINX_HITS:-0}"
export MA3_EXPECT_MIN_LIBRARIES="${MA3_EXPECT_MIN_LIBRARIES:-2}"
export MA3_EXPECT_FEATURES="${MA3_EXPECT_FEATURES:-postgresql,vector,bootstrap_selfhost}"
export MA3_READY_TIMEOUT="${MA3_READY_TIMEOUT:-60}"

if [[ -z "${MA3_API_KEY:-}" ]]; then
  MA3_API_KEY="$(docker compose exec -T ma3 sh -c 'grep ^plaintext_key= /data/bootstrap_api_key.txt | cut -d= -f2-')"
  export MA3_API_KEY
fi

echo "==> Self-host smoke (verify.sh)"
MA3_BASE_URL="${MA3_BASE_URL}" MA3_PORT="${MA3_PORT}" bash ./verify.sh

echo "==> Bootstrap UI expectations (no OIDC)"
me_code="$(curl -s -o /dev/null -w '%{http_code}' "${MA3_BASE_URL}/ui/me/")"
login_code="$(curl -s -o /tmp/ma3-auth-login.html -w '%{http_code}' "${MA3_BASE_URL}/auth/login?next=http://192.168.1.100:8010/ui/me/")"
onb_code="$(curl -s -o /tmp/ma3-onboarding.md -w '%{http_code}' "${MA3_BASE_URL}/client/agent-onboarding.md")"
home_code="$(curl -s -o /dev/null -w '%{http_code}' "${MA3_BASE_URL}/ui/home/")"
[[ "${me_code}" == "503" ]] || { echo "FAIL: /ui/me/ expected 503 (bootstrap) got ${me_code}" >&2; exit 1; }
[[ "${login_code}" == "503" ]] || { echo "FAIL: /auth/login expected 503 (bootstrap) got ${login_code}" >&2; exit 1; }
grep -qi 'html' /tmp/ma3-auth-login.html || { echo "FAIL: /auth/login should return HTML" >&2; exit 1; }
grep -q 'Authing auth is not configured' /tmp/ma3-auth-login.html && { echo "FAIL: raw Authing JSON still shown" >&2; exit 1; }
[[ "${onb_code}" == "200" ]] || { echo "FAIL: onboarding expected 200 got ${onb_code}" >&2; exit 1; }
[[ "${home_code}" == "200" ]] || { echo "FAIL: /ui/home/ expected 200 got ${home_code}" >&2; exit 1; }
grep -q 'MA3_BASE_URL' /tmp/ma3-onboarding.md || { echo "FAIL: onboarding missing MA3_BASE_URL" >&2; exit 1; }
echo "    UI bootstrap OK (me=${me_code} login=${login_code} home=${home_code} onboarding=${onb_code} bytes=$(wc -c </tmp/ma3-onboarding.md))"

echo "==> Deploy verification pytest against ${MA3_BASE_URL}"
cd "${SERVER_DIR}"
# shellcheck disable=SC1091
source .venv/bin/activate
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
pytest tests/integration/test_deploy_verification.py -v --tb=short \
  -m deploy \
  -k "not test_deploy_database_migration_state and not test_deploy_eval_claude_db_api_key"

echo "==> Self-host integration verification passed"
