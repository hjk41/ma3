#!/usr/bin/env bash
# Post-deploy verification for ma3. Env-agnostic: parameterized via MA3_* vars so the
# same script serves every environment. Run on the remote box or from a dev machine.
# Policy: deploy/README.md — must pass before reporting "deploy complete" to users.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# deploy/common/ -> repo root is two levels up
SERVER_DIR="${SERVER_DIR:-${SCRIPT_DIR}/../../code/server}"
REMOTE_DIR="${REMOTE_DIR:-/home/hct/ma3_deploy}"

export MA3_BASE_URL="${MA3_BASE_URL:-http://127.0.0.1:8000}"
export MA3_API_KEY="${MA3_API_KEY:-ma3dev}"
export MA3_EXPECT_INSTANCE_ID="${MA3_EXPECT_INSTANCE_ID:-ma3-v1-202}"
export MA3_EXPECT_MIN_RECORDS="${MA3_EXPECT_MIN_RECORDS:-}"
export MA3_EXPECT_MIN_CASES="${MA3_EXPECT_MIN_CASES:-20}"
export MA3_EXPECT_MIN_MIHOMO_HITS="${MA3_EXPECT_MIN_MIHOMO_HITS:-1}"
export MA3_EXPECT_MIN_LIBRARIES="${MA3_EXPECT_MIN_LIBRARIES:-2}"
export MA3_READY_TIMEOUT="${MA3_READY_TIMEOUT:-180}"
# Root redirect target differs per env: LAN lands on /ui/me/, ma3.io on /ui/home/ (public landing).
export MA3_EXPECT_ROOT_REDIRECT="${MA3_EXPECT_ROOT_REDIRECT:-/ui/me/}"

if [[ -f "${REMOTE_DIR}/ma3.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${REMOTE_DIR}/ma3.env"
  set +a
fi
if [[ -f "/home/hct/ma3/ma3.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "/home/hct/ma3/ma3.env"
  set +a
fi

cd "${SERVER_DIR}"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

echo "==> Waiting for ${MA3_BASE_URL}/healthz (timeout ${MA3_READY_TIMEOUT}s; embedding warm-up may take 1–3 min)"
ready=0
deadline=$((SECONDS + MA3_READY_TIMEOUT))
while (( SECONDS < deadline )); do
  if curl -sf "${MA3_BASE_URL}/healthz" >/tmp/ma3-healthz.json 2>/dev/null; then
    ready=1
    break
  fi
  sleep 2
done
if [[ "${ready}" -ne 1 ]]; then
  echo "service not ready at ${MA3_BASE_URL}/healthz after ${MA3_READY_TIMEOUT}s" >&2
  tail -30 /tmp/ma3-v1-uvicorn.log 2>/dev/null || true
  exit 1
fi
python3 -m json.tool /tmp/ma3-healthz.json

echo "==> UI/auth smoke"
features="$(python3 -c "import json; print(','.join(json.load(open('/tmp/ma3-healthz.json'))['features']))")"
echo "    features: ${features}"
if [[ "${features}" != *"vector"* ]] && [[ "${MA3_DISABLE_EMBEDDINGS:-0}" != "1" ]]; then
  echo "WARN: vector not in healthz features (embeddings may be disabled)" >&2
fi

login_code="$(curl -s -o /dev/null -w '%{http_code}' "${MA3_BASE_URL}/auth/login?next=/ui/me/")"
root_code="$(curl -s -o /dev/null -w '%{http_code}' "${MA3_BASE_URL}/")"
root_loc="$(curl -s -o /dev/null -w '%{redirect_url}' "${MA3_BASE_URL}/")"
me_code="$(curl -s -o /dev/null -w '%{http_code}' "${MA3_BASE_URL}/ui/me/")"
pub_lib_code="$(curl -s -o /dev/null -w '%{http_code}' "${MA3_BASE_URL}/ui/libraries/lib_default/")"
obs_code="$(curl -s -o /dev/null -w '%{http_code}' "${MA3_BASE_URL}/ui/observatory/")"
keys_code="$(curl -s -o /dev/null -w '%{http_code}' "${MA3_BASE_URL}/ui/keys/")"
manifest_code="$(curl -s -o /dev/null -w '%{http_code}' "${MA3_BASE_URL}/client/manifest.json")"
[[ "${login_code}" == "302" ]] || { echo "FAIL: /auth/login expected 302 got ${login_code}" >&2; exit 1; }
[[ "${root_code}" == "302" ]] || { echo "FAIL: / expected 302 got ${root_code}" >&2; exit 1; }
[[ "${root_loc}" == *"${MA3_EXPECT_ROOT_REDIRECT}"* ]] || { echo "FAIL: / redirect expected ${MA3_EXPECT_ROOT_REDIRECT} got ${root_loc}" >&2; exit 1; }
[[ "${me_code}" == "302" ]] || { echo "FAIL: /ui/me/ expected 302 got ${me_code}" >&2; exit 1; }
[[ "${pub_lib_code}" == "200" ]] || { echo "FAIL: anonymous lib_default expected 200 got ${pub_lib_code}" >&2; exit 1; }
[[ "${obs_code}" == "302" ]] || { echo "FAIL: /ui/observatory/ expected 302 got ${obs_code}" >&2; exit 1; }
[[ "${keys_code}" == "302" ]] || { echo "FAIL: /ui/keys/ expected 302 got ${keys_code}" >&2; exit 1; }
[[ "${manifest_code}" == "200" ]] || { echo "FAIL: /client/manifest.json expected 200 got ${manifest_code}" >&2; exit 1; }

mcp_tools="$(curl -sf -X POST "${MA3_BASE_URL}/mcp" \
  -H 'Content-Type: application/json' -H "X-API-Key: ${MA3_API_KEY}" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | python3 -c "import sys,json; print(len(json.load(sys.stdin)['result']['tools']))")"
[[ "${mcp_tools}" -ge 13 ]] || { echo "FAIL: MCP tools/list expected >=13 got ${mcp_tools}" >&2; exit 1; }
echo "    UI/auth smoke OK (root=${root_code} me=${me_code} pub_lib=${pub_lib_code} login=${login_code} obs=${obs_code} keys=${keys_code} mcp_tools=${mcp_tools})"

echo "==> Deploy verification pytest against ${MA3_BASE_URL}"
if [[ -z "${MA3_EXPECT_MIN_RECORDS}" && -f /tmp/ma3-deploy-post.json ]]; then
  export MA3_EXPECT_MIN_RECORDS="$(python3 -c "import json; print(json.load(open('/tmp/ma3-deploy-post.json'))['v1_records'])")"
fi
if [[ -z "${MA3_EXPECT_MIN_RECORDS}" ]]; then
  echo "WARN: MA3_EXPECT_MIN_RECORDS unset; defaulting pytest gate to 1" >&2
  export MA3_EXPECT_MIN_RECORDS=1
fi
echo "    records>=${MA3_EXPECT_MIN_RECORDS} cases>=${MA3_EXPECT_MIN_CASES} mihomo_hits>=${MA3_EXPECT_MIN_MIHOMO_HITS}"

.venv/bin/pytest tests/integration/test_deploy_verification.py -v --tb=short -m "deploy or postgres" \
  -k "not test_deploy_database_migration_state"

.venv/bin/pytest tests/integration/test_user_portal.py \
  tests/integration/test_user_portal_nav.py \
  tests/integration/test_user_portal_writes.py \
  tests/integration/test_user_portal_votes.py \
  tests/integration/test_portal_html_regression.py \
  -q --tb=short

if [[ "${MA3_BASE_URL}" == http://127.0.0.1:* && "${MA3_PUBLIC_BASE_URL:-}" == http://192.168.* ]]; then
  echo "==> SKIP test_ui_create_key_form_post (TestClient uses testserver; MA3_PUBLIC_BASE_URL=${MA3_PUBLIC_BASE_URL})"
else
  .venv/bin/pytest tests/integration/test_self_service_onboarding.py::test_ui_create_key_form_post -q --tb=short
fi

if [[ -n "${AUTHING_TEST_USER:-}" && -n "${AUTHING_TEST_PASS:-}" ]]; then
  echo "==> Authing browser E2E (login + keys form create)"
  if ! .venv/bin/python -c "import playwright" 2>/dev/null; then
    .venv/bin/pip install -q playwright
    .venv/bin/playwright install chromium 2>/dev/null || true
  fi
  export MA3_E2E_BASE_URL="${MA3_BASE_URL}"
  .venv/bin/python scripts/e2e_authing_ui.py
else
  echo "==> SKIP Authing browser E2E (set AUTHING_TEST_USER and AUTHING_TEST_PASS to enable)"
fi

echo "==> Verification passed (see deploy/README.md reporting template)"
