#!/usr/bin/env bash
# Post-deploy verification for ma3_v1. Run on 202 after deploy or from dev machine against remote.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_DIR="${SERVER_DIR:-${SCRIPT_DIR}/../code/server}"
REMOTE_DIR="${REMOTE_DIR:-/home/hct/ma3_v1}"

export MA3_BASE_URL="${MA3_BASE_URL:-http://127.0.0.1:8000}"
export MA3_API_KEY="${MA3_API_KEY:-ma3dev}"
export MA3_EXPECT_INSTANCE_ID="${MA3_EXPECT_INSTANCE_ID:-ma3-v1-202}"
export MA3_EXPECT_MIN_RECORDS="${MA3_EXPECT_MIN_RECORDS:-30}"
export MA3_EXPECT_MIN_CASES="${MA3_EXPECT_MIN_CASES:-20}"
export MA3_EXPECT_MIN_MIHOMO_HITS="${MA3_EXPECT_MIN_MIHOMO_HITS:-1}"
export MA3_EXPECT_MIN_LIBRARIES="${MA3_EXPECT_MIN_LIBRARIES:-2}"

if [[ -f "${REMOTE_DIR}/ma3.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${REMOTE_DIR}/ma3.env"
  set +a
fi

cd "${SERVER_DIR}"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

ready=0
for _ in $(seq 1 30); do
  if curl -sf "${MA3_BASE_URL}/healthz" >/dev/null; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "${ready}" -ne 1 ]]; then
  echo "service not ready at ${MA3_BASE_URL}/healthz" >&2
  exit 1
fi

echo "==> Deploy verification against ${MA3_BASE_URL}"
echo "    records>=${MA3_EXPECT_MIN_RECORDS} cases>=${MA3_EXPECT_MIN_CASES} mihomo_hits>=${MA3_EXPECT_MIN_MIHOMO_HITS}"

.venv/bin/pytest tests/integration/test_deploy_verification.py -v --tb=short -m "deploy or postgres"

echo "==> Verification passed"
