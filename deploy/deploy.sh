#!/usr/bin/env bash
# ===========================================================================
# Generic ma3 deploy driver.
#
# Environment specifics live in a config file that is NOT committed to git
# (real hosts / paths / instance ids). Only deploy/deploy.env.sample is tracked.
#
# Usage:
#   ./deploy/deploy.sh <config.env>
#   DEPLOY_CONFIG=deploy/deploy.202.env ./deploy/deploy.sh
#
# Two modes (set ENV_MODE in the config):
#   regenerate  LAN/dev: rebuild the remote ma3.env from LEGACY_ENV_FILE + config
#               (instance id, public base url, dev auth). Runs legacy backfill.
#   preserve    production: NEVER touch the remote ma3.env except to inject
#               MA3_GIT_COMMIT. Asserts production-safe invariants before restart.
#
# A host guard (ALLOWED_HOSTS) refuses to run against an unexpected target, so a
# 202 config can never be pushed to ma3.io (or vice-versa).
# ===========================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

CONFIG="${1:-${DEPLOY_CONFIG:-}}"
if [[ -z "${CONFIG}" ]]; then
  echo "usage: $0 <config.env>   (or set DEPLOY_CONFIG=...)" >&2
  echo "template: ${SCRIPT_DIR}/deploy.env.sample" >&2
  exit 2
fi
[[ -f "${CONFIG}" ]] || { echo "config not found: ${CONFIG}" >&2; exit 2; }

set -a
# shellcheck disable=SC1090
source "${CONFIG}"
set +a

# ---- required config -------------------------------------------------------
: "${DEPLOY_PROFILE:?set DEPLOY_PROFILE in ${CONFIG}}"
: "${REMOTE_HOST:?}"
: "${REMOTE_USER:?}"
: "${REMOTE_DIR:?}"
: "${ALLOWED_HOSTS:?space-separated host allowlist (guard)}"
: "${ENV_MODE:?ENV_MODE must be 'preserve' or 'regenerate'}"

MA3_PORT="${MA3_PORT:-8000}"
SSH_KEY="${SSH_KEY:-${HOME}/.ssh/id_rsa}"
SSH_EXTRA_OPTS="${SSH_EXTRA_OPTS:-}"
UVICORN_HOST="${UVICORN_HOST:-0.0.0.0}"
HEALTHZ_TIMEOUT="${HEALTHZ_TIMEOUT:-240}"
REQUIRE_VECTOR="${REQUIRE_VECTOR:-1}"
RUN_VERIFY="${RUN_VERIFY:-1}"
# Blue-green (preserve + Caddy only). Default off so LAN/regenerate and
# single-port prod keep the classic pkill→restart path.
BLUE_GREEN="${BLUE_GREEN:-0}"
BLUE_GREEN_PORT_A="${BLUE_GREEN_PORT_A:-8000}"
BLUE_GREEN_PORT_B="${BLUE_GREEN_PORT_B:-8001}"
BLUE_GREEN_DRAIN_SEC="${BLUE_GREEN_DRAIN_SEC:-5}"
CADDY_UPSTREAM_FILE="${CADDY_UPSTREAM_FILE:-${REMOTE_DIR}/data/bluegreen/upstream.caddy}"
CADDY_RELOAD_CMD="${CADDY_RELOAD_CMD:-caddy reload --config /etc/caddy/Caddyfile}"
# When blue-green is on, smoke the public URL after Caddy switch (rollback on fail).
BLUE_GREEN_PUBLIC_SMOKE_URL="${BLUE_GREEN_PUBLIC_SMOKE_URL:-}"
SSH="ssh -i ${SSH_KEY} -o ConnectTimeout=15 ${SSH_EXTRA_OPTS}"
RSYNC_SSH="ssh -i ${SSH_KEY} ${SSH_EXTRA_OPTS}"

# ---- host guard ------------------------------------------------------------
guard_ok=0
for h in ${ALLOWED_HOSTS}; do [[ "${REMOTE_HOST}" == "${h}" ]] && guard_ok=1; done
if [[ "${guard_ok}" -ne 1 ]]; then
  echo "REFUSING: REMOTE_HOST=${REMOTE_HOST} not in ALLOWED_HOSTS='${ALLOWED_HOSTS}' (profile ${DEPLOY_PROFILE})." >&2
  exit 2
fi

if [[ "${BLUE_GREEN}" == "1" && "${ENV_MODE}" != "preserve" ]]; then
  echo "REFUSING: BLUE_GREEN=1 is only supported with ENV_MODE=preserve (Caddy cutover)." >&2
  exit 2
fi

DEPLOY_GIT_COMMIT="$(git -C "${REPO_DIR}" rev-parse --short HEAD 2>/dev/null || true)"
echo "==> profile=${DEPLOY_PROFILE} mode=${ENV_MODE} blue_green=${BLUE_GREEN} -> ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR} port=${MA3_PORT} commit=${DEPLOY_GIT_COMMIT}"

RSYNC_EXCLUDES=(
  --exclude '.git' --exclude '.venv*' --exclude '__pycache__' --exclude '*.pyc'
  --exclude '.cursor'
  --exclude '.pytest_cache' --exclude 'server/data' --exclude 'server/.venv'
  # Top-level data contains host-owned blue-green state and must never be synced or deleted.
  --exclude '/data/***' --filter 'P /data/***' --exclude 'ma3db_*.sql.gz'
  # Local deploy configs may contain VERIFY_API_KEY / host secrets — never rsync them.
  --exclude 'deploy/deploy.*.env' --exclude 'deploy/.env'
  # ma3.env is host-specific; never overwrite/delete it from the source tree.
  --exclude 'ma3.env' --filter 'P ma3.env' --filter 'P ma3.pid'
)

echo "==> [1/3] rsync ${REPO_DIR} -> remote"
rsync -avz -e "${RSYNC_SSH}" --delete "${RSYNC_EXCLUDES[@]}" \
  "${REPO_DIR}/" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"

# ===========================================================================
if [[ "${ENV_MODE}" == "preserve" ]]; then
# ---------------------------------------------------------------------------
  EXPECT_INSTANCE_ID="${EXPECT_INSTANCE_ID:?preserve mode needs EXPECT_INSTANCE_ID}"
  EXPECT_PUBLIC_BASE_URL="${EXPECT_PUBLIC_BASE_URL:?preserve mode needs EXPECT_PUBLIC_BASE_URL}"
  ASSERT_DEV_AUTH_OFF="${ASSERT_DEV_AUTH_OFF:-1}"
  ASSERT_NO_LAN_PROXY="${ASSERT_NO_LAN_PROXY:-1}"

  if [[ "${BLUE_GREEN}" == "1" ]]; then
    UVICORN_HOST="${UVICORN_HOST:-127.0.0.1}"
    if [[ -z "${BLUE_GREEN_PUBLIC_SMOKE_URL}" ]]; then
      BLUE_GREEN_PUBLIC_SMOKE_URL="${EXPECT_PUBLIC_BASE_URL}"
    fi
    echo "==> [2/3] preserve-env deploy (assert invariants, inject commit, Caddy blue-green cutover)"
  else
    echo "==> [2/3] preserve-env deploy (assert invariants, inject commit, restart)"
  fi
  $SSH "${REMOTE_USER}@${REMOTE_HOST}" bash -s <<REMOTE
set -euo pipefail
REMOTE_DIR="${REMOTE_DIR}"; PORT="${MA3_PORT}"; UVICORN_HOST="${UVICORN_HOST}"
DEPLOY_GIT_COMMIT="${DEPLOY_GIT_COMMIT:-}"; REQUIRE_VECTOR="${REQUIRE_VECTOR}"
HEALTHZ_TIMEOUT="${HEALTHZ_TIMEOUT}"
EXPECT_INSTANCE_ID="${EXPECT_INSTANCE_ID}"; EXPECT_PUBLIC_BASE_URL="${EXPECT_PUBLIC_BASE_URL}"
ASSERT_DEV_AUTH_OFF="${ASSERT_DEV_AUTH_OFF}"; ASSERT_NO_LAN_PROXY="${ASSERT_NO_LAN_PROXY}"
BLUE_GREEN="${BLUE_GREEN}"
BLUE_GREEN_PORT_A="${BLUE_GREEN_PORT_A}"; BLUE_GREEN_PORT_B="${BLUE_GREEN_PORT_B}"
BLUE_GREEN_DRAIN_SEC="${BLUE_GREEN_DRAIN_SEC}"
CADDY_UPSTREAM_FILE="${CADDY_UPSTREAM_FILE}"
CADDY_RELOAD_CMD="${CADDY_RELOAD_CMD}"
BLUE_GREEN_PUBLIC_SMOKE_URL="${BLUE_GREEN_PUBLIC_SMOKE_URL}"
ENV="\${REMOTE_DIR}/ma3.env"

[[ -f "\${ENV}" ]] || { echo "FATAL: \${ENV} missing; provision production ma3.env first." >&2; exit 1; }
get() { grep -E "^\$1=" "\${ENV}" | tail -1 | cut -d= -f2- || true; }
fail=0
[[ "\${ASSERT_DEV_AUTH_OFF}" == "1" && "\$(get MA3_DEV_AUTH)" == "1" ]] && { echo "ASSERT FAIL: MA3_DEV_AUTH=1 in production" >&2; fail=1; }
[[ "\$(get MA3_INSTANCE_ID)" != "\${EXPECT_INSTANCE_ID}" ]] && { echo "ASSERT FAIL: instance_id \$(get MA3_INSTANCE_ID) != \${EXPECT_INSTANCE_ID}" >&2; fail=1; }
[[ "\$(get MA3_PUBLIC_BASE_URL)" != "\${EXPECT_PUBLIC_BASE_URL}" ]] && { echo "ASSERT FAIL: public_base_url \$(get MA3_PUBLIC_BASE_URL) != \${EXPECT_PUBLIC_BASE_URL}" >&2; fail=1; }
if [[ "\${ASSERT_NO_LAN_PROXY}" == "1" ]] && grep -qE "^(HTTP_PROXY|HTTPS_PROXY|MA3_HTTP_PROXY|MA3_HTTPS_PROXY)=" "\${ENV}"; then
  echo "ASSERT FAIL: LAN proxy vars present in production ma3.env" >&2; fail=1
fi
[[ "\${fail}" -ne 0 ]] && { echo "Aborting: production ma3.env failed invariants." >&2; exit 1; }

cd "\${REMOTE_DIR}/code/server"
[[ -d .venv ]] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

if [[ -n "\${DEPLOY_GIT_COMMIT}" ]]; then
  if grep -q '^MA3_GIT_COMMIT=' "\${ENV}"; then
    sed -i "s/^MA3_GIT_COMMIT=.*/MA3_GIT_COMMIT=\${DEPLOY_GIT_COMMIT}/" "\${ENV}"
  else
    echo "MA3_GIT_COMMIT=\${DEPLOY_GIT_COMMIT}" >> "\${ENV}"
  fi
fi

if [[ "\${BLUE_GREEN}" == "1" ]]; then
  # shellcheck disable=SC1091
  source "\${REMOTE_DIR}/deploy/common/bluegreen_remote.sh"
  mkdir -p "\$(dirname "\${CADDY_UPSTREAM_FILE}")"
  if [[ ! -f "\${CADDY_UPSTREAM_FILE}" ]]; then
    echo "==> seeding CADDY_UPSTREAM_FILE=\${CADDY_UPSTREAM_FILE} (ensure Caddyfile imports it)"
    cp -f "\${REMOTE_DIR}/deploy/caddy/upstream.caddy.example" "\${CADDY_UPSTREAM_FILE}"
  fi
  bluegreen_cutover
else
  pkill -f "uvicorn app.main:app.*--port \${PORT}" || true
  sleep 3
  set -a; source "\${ENV}"; set +a
  unset MA3_DISABLE_EMBEDDINGS || true
  nohup .venv/bin/python -m uvicorn app.main:app --host "\${UVICORN_HOST}" --port "\${PORT}" --app-dir . \
    > /tmp/ma3-v1-uvicorn.log 2>&1 &
  echo \$! > "\${REMOTE_DIR}/ma3.pid"

  ready=0; deadline=\$((SECONDS + HEALTHZ_TIMEOUT))
  while (( SECONDS < deadline )); do
    if curl -sf "http://127.0.0.1:\${PORT}/healthz" >/tmp/ma3-healthz.json 2>/dev/null; then
      if [[ "\${REQUIRE_VECTOR}" != "1" ]]; then ready=1; break; fi
      feats=\$(python3 -c "import json;print(','.join(json.load(open('/tmp/ma3-healthz.json')).get('features',[])))")
      [[ "\${feats}" == *vector* ]] && { ready=1; break; }
    fi
    sleep 2
  done
  [[ "\${ready}" -eq 1 ]] || { echo "healthz not ready after \${HEALTHZ_TIMEOUT}s" >&2; tail -40 /tmp/ma3-v1-uvicorn.log >&2; exit 1; }
  python3 -m json.tool /tmp/ma3-healthz.json
fi
REMOTE

  if [[ "${RUN_VERIFY}" == "1" ]]; then
    # Resolve loopback port: blue-green uses recorded active_port; classic uses MA3_PORT.
    VERIFY_LOOPBACK_PORT="${MA3_PORT}"
    if [[ "${BLUE_GREEN}" == "1" ]]; then
      VERIFY_LOOPBACK_PORT="$($SSH "${REMOTE_USER}@${REMOTE_HOST}" \
        "tr -d '[:space:]' < '${REMOTE_DIR}/data/bluegreen/active_port' 2>/dev/null || echo '${BLUE_GREEN_PORT_A}'")"
      VERIFY_LOOPBACK_PORT="${VERIFY_LOOPBACK_PORT:-${BLUE_GREEN_PORT_A}}"
    fi
    echo "==> [3/3a] production remote loopback smoke (127.0.0.1:${VERIFY_LOOPBACK_PORT})"
    $SSH "${REMOTE_USER}@${REMOTE_HOST}" bash -s <<REMOTE
set -euo pipefail
PORT="${VERIFY_LOOPBACK_PORT}"; EXPECT_INSTANCE_ID="${EXPECT_INSTANCE_ID}"; EXPECT_PUBLIC_BASE_URL="${EXPECT_PUBLIC_BASE_URL}"
BASE="http://127.0.0.1:\${PORT}"
feats=\$(python3 -c "import json;print(','.join(json.load(open('/tmp/ma3-healthz.json')).get('features',[])))")
inst=\$(python3 -c "import json;print(json.load(open('/tmp/ma3-healthz.json')).get('instance_id',''))")
base=\$(python3 -c "import json;print(json.load(open('/tmp/ma3-healthz.json')).get('public_base_url',''))")
[[ "\${feats}" == *vector* ]]   || { echo "FAIL: vector missing (\${feats})" >&2; exit 1; }
[[ "\${feats}" != *dev_auth* ]] || { echo "FAIL: dev_auth enabled in production" >&2; exit 1; }
[[ "\${inst}" == "\${EXPECT_INSTANCE_ID}" ]] || { echo "FAIL: instance_id \${inst}" >&2; exit 1; }
[[ "\${base}" == "\${EXPECT_PUBLIC_BASE_URL}" ]] || { echo "FAIL: public_base_url \${base}" >&2; exit 1; }
curl -s -o /tmp/ma3-devprobe.json -X POST "\${BASE}/mcp" -H 'Content-Type: application/json' -H 'X-API-Key: ma3dev' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"ma3_whoami","arguments":{}}}' || true
grep -q '"code":-32001' /tmp/ma3-devprobe.json || { echo "FAIL: ma3dev not rejected (dev backdoor open)" >&2; exit 1; }
login_loc=\$(curl -s -o /dev/null -w '%{redirect_url}' "\${BASE}/auth/login")
[[ "\${login_loc}" == *"/auth/callback"* || "\${login_loc}" == *"auth%2Fcallback"* ]] || { echo "FAIL: /auth/login redirect \${login_loc}" >&2; exit 1; }
tools=\$(curl -sf -X POST "\${BASE}/mcp" -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | python3 -c "import sys,json;print(len(json.load(sys.stdin)['result']['tools']))")
[[ "\${tools}" -ge 13 ]] || { echo "FAIL: MCP tools/list=\${tools}" >&2; exit 1; }
echo "    remote smoke OK (instance=\${inst} base=\${base} tools=\${tools} port=\${PORT})"
REMOTE

    echo "==> [3/3b] production public-URL verify (deploy/common/verify_ma3_prod.sh)"
    export MA3_BASE_URL="${EXPECT_PUBLIC_BASE_URL}"
    export MA3_EXPECT_INSTANCE_ID="${EXPECT_INSTANCE_ID}"
    export MA3_EXPECT_PUBLIC_BASE_URL="${EXPECT_PUBLIC_BASE_URL}"
    export MA3_EXPECT_FEATURES="${MA3_EXPECT_FEATURES:-postgresql,vector,oidc}"
    export MA3_READY_TIMEOUT="${HEALTHZ_TIMEOUT}"
    # Optional: set VERIFY_API_KEY in deploy.ma3.io.env for authed MCP pytest.
    if [[ -n "${VERIFY_API_KEY:-}" ]]; then
      export MA3_API_KEY="${VERIFY_API_KEY}"
    fi
    bash "${SCRIPT_DIR}/common/verify_ma3_prod.sh"
  fi

# ===========================================================================
elif [[ "${ENV_MODE}" == "regenerate" ]]; then
# ---------------------------------------------------------------------------
  LEGACY_ENV_FILE="${LEGACY_ENV_FILE:?regenerate mode needs LEGACY_ENV_FILE (remote path)}"
  WRITE_INSTANCE_ID="${WRITE_INSTANCE_ID:?regenerate mode needs WRITE_INSTANCE_ID}"
  WRITE_PUBLIC_BASE_URL="${WRITE_PUBLIC_BASE_URL:-http://${REMOTE_HOST}:${MA3_PORT}}"
  DEV_AUTH="${DEV_AUTH:-0}"
  HF_CACHE_SOURCE="${HF_CACHE_SOURCE:-}"
  RUN_MIGRATION="${RUN_MIGRATION:-1}"

  echo "==> [2/3] regenerate-env deploy (rebuild ma3.env, migrate, restart)"
  $SSH "${REMOTE_USER}@${REMOTE_HOST}" bash -s <<REMOTE
set -euo pipefail
REMOTE_DIR="${REMOTE_DIR}"; PORT="${MA3_PORT}"; UVICORN_HOST="${UVICORN_HOST}"
DEPLOY_GIT_COMMIT="${DEPLOY_GIT_COMMIT:-}"; REQUIRE_VECTOR="${REQUIRE_VECTOR}"; HEALTHZ_TIMEOUT="${HEALTHZ_TIMEOUT}"
LEGACY_ENV_FILE="${LEGACY_ENV_FILE}"; WRITE_INSTANCE_ID="${WRITE_INSTANCE_ID}"
WRITE_PUBLIC_BASE_URL="${WRITE_PUBLIC_BASE_URL}"; DEV_AUTH="${DEV_AUTH}"
HF_CACHE_SOURCE="${HF_CACHE_SOURCE}"; RUN_MIGRATION="${RUN_MIGRATION}"
ENV="\${REMOTE_DIR}/ma3.env"

[[ -f "\${LEGACY_ENV_FILE}" ]] || { echo "FATAL: LEGACY_ENV_FILE \${LEGACY_ENV_FILE} missing" >&2; exit 1; }
set -a; source "\${LEGACY_ENV_FILE}"; set +a

cd "\${REMOTE_DIR}/code/server"
[[ -d .venv ]] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo "==> Pre-deploy DB inventory"
export MA3_DATABASE_URL="\${MA3_DATABASE_URL}"
.venv/bin/python scripts/db_inventory.py -o /tmp/ma3-deploy-pre.json

pkill -f "uvicorn app.main:app.*--port \${PORT}" || true
sleep 2

mkdir -p "\${REMOTE_DIR}/data"
if [[ -n "\${HF_CACHE_SOURCE}" && -d "\${HF_CACHE_SOURCE}" ]]; then
  ln -sfn "\${HF_CACHE_SOURCE}" "\${REMOTE_DIR}/data/hf-cache"
fi

AUTHING_CONFIGURED=0
[[ -n "\${MA3_AUTHING_APP_ID:-}" && -n "\${MA3_AUTHING_APP_SECRET:-}" ]] && AUTHING_CONFIGURED=1

cat > "\${ENV}" <<ENVFILE
MA3_PORT=\${PORT}
MA3_DATABASE_URL=\${MA3_DATABASE_URL}
MA3_INSTANCE_ID=\${WRITE_INSTANCE_ID}
MA3_HF_HOME=\${MA3_HF_HOME:-\${HF_CACHE_SOURCE}}
HF_HOME=\${HF_HOME:-\${HF_CACHE_SOURCE}}
HF_HUB_OFFLINE=1
ENVFILE
[[ -n "\${DEPLOY_GIT_COMMIT}" ]] && echo "MA3_GIT_COMMIT=\${DEPLOY_GIT_COMMIT}" >> "\${ENV}"

if [[ "\${AUTHING_CONFIGURED}" -eq 1 ]]; then
  cat >> "\${ENV}" <<AUTHING
MA3_DEV_AUTH=\${DEV_AUTH}
MA3_AUTHING_ENABLED=\${MA3_AUTHING_ENABLED:-1}
MA3_AUTHING_ISSUER=\${MA3_AUTHING_ISSUER}
MA3_AUTHING_APP_ID=\${MA3_AUTHING_APP_ID}
MA3_AUTHING_APP_SECRET=\${MA3_AUTHING_APP_SECRET}
MA3_PUBLIC_BASE_URL=\${WRITE_PUBLIC_BASE_URL}
MA3_AUTHING_REDIRECT_URI=\${MA3_AUTHING_REDIRECT_URI:-\${WRITE_PUBLIC_BASE_URL}/auth/callback}
MA3_AUTH_ADMIN_USERS=\${MA3_AUTH_ADMIN_USERS:?MA3_AUTH_ADMIN_USERS required when Authing enabled}
AUTHING
else
  printf 'MA3_DEV_AUTH=1\nMA3_DEV_API_KEY=ma3dev\n' >> "\${ENV}"
fi

echo "==> Ensure pgvector extension"
MA3_DBNAME="\${MA3_DATABASE_URL##*/}"; MA3_DBNAME="\${MA3_DBNAME%%\?*}"
sudo -n -u postgres psql -d "\${MA3_DBNAME}" -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null 2>&1 \
  && echo "   pgvector ensured" || echo "   WARN: could not ensure pgvector (search falls back to FTS)"

if [[ "\${RUN_MIGRATION}" == "1" ]]; then
  echo "==> Backfill legacy tables into v1 schema"
  export MA3_DATABASE_URL="\${MA3_DATABASE_URL}" MA3_MIGRATE_RENAME=0 MA3_MIGRATE_BACKFILL=1 MA3_DISABLE_EMBEDDINGS=1
  .venv/bin/python scripts/migrate_legacy_pg.py | tee /tmp/ma3-backfill.json >/dev/null
  .venv/bin/python scripts/db_inventory.py --compare /tmp/ma3-deploy-pre.json --backfill /tmp/ma3-backfill.json \
    -o /tmp/ma3-deploy-post-backfill.json || true
fi

echo "==> Start uvicorn"
set -a; source "\${ENV}"; set +a
nohup .venv/bin/python -m uvicorn app.main:app --host "\${UVICORN_HOST}" --port "\${PORT}" --app-dir . \
  > /tmp/ma3-v1-uvicorn.log 2>&1 &
echo \$! > "\${REMOTE_DIR}/ma3.pid"

ready=0; deadline=\$((SECONDS + HEALTHZ_TIMEOUT))
while (( SECONDS < deadline )); do
  curl -sf "http://127.0.0.1:\${PORT}/healthz" >/tmp/ma3-healthz.json 2>/dev/null && { ready=1; break; }
  sleep 2
done
[[ "\${ready}" -eq 1 ]] || { echo "healthz not ready after \${HEALTHZ_TIMEOUT}s" >&2; tail -40 /tmp/ma3-v1-uvicorn.log >&2; exit 1; }
python3 -m json.tool /tmp/ma3-healthz.json
.venv/bin/python scripts/db_inventory.py --compare /tmp/ma3-deploy-pre.json -o /tmp/ma3-deploy-post.json || true
REMOTE

  if [[ "${RUN_VERIFY}" == "1" ]]; then
    echo "==> [3/3] verification via deploy/common/verify_ma3.sh (remote)"
    $SSH "${REMOTE_USER}@${REMOTE_HOST}" bash -s <<REMOTE
set -euo pipefail
export MA3_BASE_URL="http://127.0.0.1:${MA3_PORT}"
export MA3_API_KEY="${VERIFY_API_KEY:-ma3dev}"
export MA3_EXPECT_INSTANCE_ID="${WRITE_INSTANCE_ID}"
export MA3_EXPECT_ROOT_REDIRECT="${EXPECT_ROOT_REDIRECT:-/ui/me/}"
export MA3_READY_TIMEOUT="${HEALTHZ_TIMEOUT}"
export REMOTE_DIR="${REMOTE_DIR}"
export SERVER_DIR="${REMOTE_DIR}/code/server"
if [[ -f /tmp/ma3-deploy-post.json ]]; then
  export MA3_EXPECT_MIN_RECORDS="\$(python3 -c "import json;print(json.load(open('/tmp/ma3-deploy-post.json'))['v1_records'])" 2>/dev/null || echo 1)"
fi
bash "${REMOTE_DIR}/deploy/common/verify_ma3.sh"
REMOTE
  fi

else
  echo "FATAL: unknown ENV_MODE='${ENV_MODE}' (use 'preserve' or 'regenerate')" >&2
  exit 2
fi

echo "==> Done: profile=${DEPLOY_PROFILE} commit=${DEPLOY_GIT_COMMIT}"
