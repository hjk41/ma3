#!/usr/bin/env bash
# =============================================================================
# Production / public-URL post-deploy verification for ma3 (ma3.io).
#
# Mandatory after every preserve-mode (production) deploy. Run from a machine
# that can reach the public base URL (through Caddy/TLS), not only loopback.
#
# Usage:
#   export MA3_BASE_URL=https://ma3.io
#   export MA3_EXPECT_INSTANCE_ID=ma3-v1-hk
#   # optional but recommended for authed MCP checks:
#   export MA3_API_KEY=ma3k_...
#   bash deploy/common/verify_ma3_prod.sh
#
# Exit 0 only when every required check passes.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SERVER_DIR="${SERVER_DIR:-${REPO_DIR}/code/server}"

: "${MA3_BASE_URL:?set MA3_BASE_URL (e.g. https://ma3.io)}"
: "${MA3_EXPECT_INSTANCE_ID:?set MA3_EXPECT_INSTANCE_ID (e.g. ma3-v1-hk)}"

MA3_BASE_URL="${MA3_BASE_URL%/}"
MA3_EXPECT_PUBLIC_BASE_URL="${MA3_EXPECT_PUBLIC_BASE_URL:-${MA3_BASE_URL}}"
MA3_EXPECT_FEATURES="${MA3_EXPECT_FEATURES:-postgresql,vector,oidc}"
MA3_EXPECT_MIN_TOOLS="${MA3_EXPECT_MIN_TOOLS:-13}"
MA3_READY_TIMEOUT="${MA3_READY_TIMEOUT:-120}"
RUN_PYTEST="${RUN_PYTEST:-1}"

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy || true

fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "  OK: $*"; }

echo "==> Production verify against ${MA3_BASE_URL}"
echo "    expect instance=${MA3_EXPECT_INSTANCE_ID} public=${MA3_EXPECT_PUBLIC_BASE_URL}"

# ---- 1. healthz -------------------------------------------------------------
echo "==> [1/6] healthz"
deadline=$((SECONDS + MA3_READY_TIMEOUT))
ready=0
while (( SECONDS < deadline )); do
  if curl -sf "${MA3_BASE_URL}/healthz" >/tmp/ma3-prod-healthz.json 2>/dev/null; then
    ready=1
    break
  fi
  sleep 2
done
[[ "${ready}" -eq 1 ]] || fail "healthz not ready at ${MA3_BASE_URL}/healthz after ${MA3_READY_TIMEOUT}s"
python3 -m json.tool /tmp/ma3-prod-healthz.json >/dev/null

python3 - <<'PY'
import json, os, sys
h = json.load(open("/tmp/ma3-prod-healthz.json"))
expect_id = os.environ["MA3_EXPECT_INSTANCE_ID"]
expect_base = os.environ["MA3_EXPECT_PUBLIC_BASE_URL"]
features = set(h.get("features") or [])
need = {f.strip() for f in os.environ.get("MA3_EXPECT_FEATURES", "").split(",") if f.strip()}
errs = []
if h.get("status") != "ok":
    errs.append(f"status={h.get('status')}")
if h.get("instance_id") != expect_id:
    errs.append(f"instance_id={h.get('instance_id')} want {expect_id}")
if h.get("public_base_url") != expect_base:
    errs.append(f"public_base_url={h.get('public_base_url')} want {expect_base}")
missing = sorted(need - features)
if missing:
    errs.append(f"missing features {missing} (have {sorted(features)})")
if "dev_auth" in features:
    errs.append("dev_auth must be off in production")
if errs:
    print("FAIL:", "; ".join(errs), file=sys.stderr)
    sys.exit(1)
print("commit=", h.get("git_commit"), "features=", ",".join(h.get("features") or []))
PY
ok "healthz instance/features/public_base_url"

# ---- 2. UI / Auth smoke -----------------------------------------------------
echo "==> [2/6] UI / Auth smoke"
home_code="$(curl -s -o /dev/null -w '%{http_code}' "${MA3_BASE_URL}/ui/home/")"
[[ "${home_code}" == "200" ]] || fail "/ui/home/ expected 200 got ${home_code}"

me_code="$(curl -s -o /dev/null -w '%{http_code}' "${MA3_BASE_URL}/ui/me/")"
[[ "${me_code}" == "302" ]] || fail "/ui/me/ expected 302 (login) got ${me_code}"

obs_code="$(curl -s -o /dev/null -w '%{http_code}' "${MA3_BASE_URL}/ui/observatory/")"
[[ "${obs_code}" == "302" ]] || fail "/ui/observatory/ expected 302 got ${obs_code}"

keys_code="$(curl -s -o /dev/null -w '%{http_code}' "${MA3_BASE_URL}/ui/keys/")"
[[ "${keys_code}" == "302" ]] || fail "/ui/keys/ expected 302 got ${keys_code}"

login_code="$(curl -s -o /dev/null -w '%{http_code}' "${MA3_BASE_URL}/auth/login?next=/ui/me/")"
login_loc="$(curl -s -o /dev/null -w '%{redirect_url}' "${MA3_BASE_URL}/auth/login?next=/ui/me/")"
[[ "${login_code}" == "302" ]] || fail "/auth/login expected 302 got ${login_code}"
echo "${login_loc}" | grep -Eqi 'authing|/oidc/auth|auth%2Fcallback|/auth/callback' \
  || fail "/auth/login redirect unexpected: ${login_loc}"
ok "home/me/observatory/keys/login"

# ---- 3. Client bundle -------------------------------------------------------
echo "==> [3/6] client bundle"
for path in \
  /client/manifest.json \
  /client/agent-onboarding.md \
  /client/templates/ma3-agent-policy.mdc \
  /client/templates/ma3-client.env.example \
  /client/mcp-tools.json \
  /client/scripts/sync_ma3_client.sh \
  /client/scripts/sync_ma3_client.py \
  /client/lib/ma3_sync_core.py
do
  code="$(curl -s -o /tmp/ma3-prod-asset -w '%{http_code}' "${MA3_BASE_URL}${path}")"
  [[ "${code}" == "200" ]] || fail "${path} expected 200 got ${code}"
  [[ -s /tmp/ma3-prod-asset ]] || fail "${path} empty body"
done
grep -q 'MA3_BASE_URL' /tmp/ma3-prod-asset || true
# re-fetch onboarding specifically for content gate
curl -sf "${MA3_BASE_URL}/client/agent-onboarding.md" -o /tmp/ma3-prod-onboarding.md
grep -q 'MA3_BASE_URL' /tmp/ma3-prod-onboarding.md || fail "onboarding missing MA3_BASE_URL"
ok "client bundle URLs"

# ---- 4. MCP anonymous / discovery -------------------------------------------
echo "==> [4/6] MCP anonymous denial + discovery"
tools="$(curl -sf -X POST "${MA3_BASE_URL}/mcp" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | python3 -c "import sys,json; print(len(json.load(sys.stdin)['result']['tools']))")"
[[ "${tools}" -ge "${MA3_EXPECT_MIN_TOOLS}" ]] || fail "tools/list=${tools} want >=${MA3_EXPECT_MIN_TOOLS}"

curl -sf -X POST "${MA3_BASE_URL}/mcp" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"ma3_whoami","arguments":{}}}' \
  >/tmp/ma3-prod-anon-whoami.json
python3 - <<'PY'
import json, sys
d = json.load(open("/tmp/ma3-prod-anon-whoami.json"))
sc = d["result"]["structuredContent"]
assert sc["caller"]["type"] == "anonymous", sc
assert sc.get("readable_library_ids") == [], sc
assert sc.get("writable_library_ids") == [], sc
PY

curl -s -o /tmp/ma3-prod-anon-ctx.json -X POST "${MA3_BASE_URL}/mcp" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"ma3_context","arguments":{"problem":"mihomo proxy docker","max_cases":3}}}'
python3 - <<'PY'
import json, sys
d = json.load(open("/tmp/ma3-prod-anon-ctx.json"))
err = d.get("error") or {}
assert err.get("code") == -32001, d
assert "authentication required" in str(err.get("message", "")).lower(), err
PY

curl -s -o /tmp/ma3-prod-devprobe.json -X POST "${MA3_BASE_URL}/mcp" \
  -H 'Content-Type: application/json' -H 'X-API-Key: ma3dev' \
  -d '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"ma3_whoami","arguments":{}}}' || true
grep -q '"code":-32001' /tmp/ma3-prod-devprobe.json \
  || fail "ma3dev must be rejected on production"
ok "tools=${tools}; anon denied; ma3dev rejected"

# ---- 5. pytest (public URL) -------------------------------------------------
echo "==> [5/6] deploy pytest against ${MA3_BASE_URL}"
if [[ "${RUN_PYTEST}" != "1" ]]; then
  echo "    SKIP pytest (RUN_PYTEST=${RUN_PYTEST})"
else
  cd "${SERVER_DIR}"
  if [[ ! -d .venv ]]; then
    python3 -m venv .venv
    .venv/bin/pip install -q --upgrade pip
    .venv/bin/pip install -q -r requirements.txt
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  export MA3_BASE_URL MA3_EXPECT_INSTANCE_ID
  export MA3_EXPECT_FEATURES
  export MA3_EXPECT_CALLER_TYPE="${MA3_EXPECT_CALLER_TYPE:-api_key}"
  export MA3_EXPECT_MIN_RECORDS="${MA3_EXPECT_MIN_RECORDS:-1}"
  export MA3_EXPECT_MIN_CASES="${MA3_EXPECT_MIN_CASES:-1}"
  export MA3_EXPECT_MIN_MIHOMO_HITS="${MA3_EXPECT_MIN_MIHOMO_HITS:-0}"
  export MA3_EXPECT_MIN_NGINX_HITS="${MA3_EXPECT_MIN_NGINX_HITS:-0}"
  export MA3_EXPECT_MIN_LIBRARIES="${MA3_EXPECT_MIN_LIBRARIES:-1}"
  export MA3_READY_TIMEOUT

  # Keyless gates (anon denial is covered by bash [4/6]; the pytest anon case
  # also needs a valid key for the positive path, so it runs only when keyed).
  pytest tests/integration/test_deploy_verification.py \
    -v --tb=short -m deploy \
    -k "test_deploy_healthz or test_deploy_client_bundle_usable or test_deploy_auth_login_friendly_when_oidc_off"

  if [[ -n "${MA3_API_KEY:-}" ]]; then
    echo "    + authed MCP deploy tests (MA3_API_KEY set)"
    pytest tests/integration/test_deploy_verification.py \
      -v --tb=short -m deploy \
      -k "not test_deploy_database_migration_state and not test_deploy_eval_claude_db_api_key"
  else
    echo "    SKIP authed MCP suite (set MA3_API_KEY / VERIFY_API_KEY to enable doctor/context)"
  fi
fi
ok "pytest gates"

# ---- 5b. /metrics must not be public (decision A) ---------------------------
echo "==> [5b] /metrics not publicly exposed"
metrics_code="$(curl -s -o /dev/null -w '%{http_code}' "${MA3_BASE_URL}/metrics" || true)"
# Accept 404 (disabled or not proxied) or any non-200. A public 200 Prometheus
# text exposition would leak operational data.
if [[ "${metrics_code}" == "200" ]]; then
  body="$(curl -sf "${MA3_BASE_URL}/metrics" | head -c 200 || true)"
  if echo "${body}" | grep -q 'ma3_http_requests_total\|TYPE ma3_'; then
    fail "/metrics is publicly scraping Prometheus text (status 200) — Caddy must not proxy it"
  fi
fi
ok "/metrics not publicly exposing Prometheus text (http=${metrics_code})"

# ---- 6. summary -------------------------------------------------------------
echo "==> [6/6] Production verification PASSED"
echo "    url=${MA3_BASE_URL} instance=${MA3_EXPECT_INSTANCE_ID} commit=$(python3 -c 'import json;print(json.load(open("/tmp/ma3-prod-healthz.json")).get("git_commit"))')"
