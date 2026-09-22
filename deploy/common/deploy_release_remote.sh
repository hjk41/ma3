#!/usr/bin/env bash
# Deploy one already-prepared release on the application host.
# Called by deploy/deploy.sh with compact positional arguments so no repository
# or large shell heredoc crosses the operator SSH connection.
set -euo pipefail

if [[ "$#" -ne 20 ]]; then
  echo "usage: $0 REMOTE_DIR APP_DIR DEPLOY_SOURCE SHORT_SHA FULL_SHA PORT UVICORN_HOST REQUIRE_VECTOR HEALTHZ_TIMEOUT EXPECT_INSTANCE_ID EXPECT_PUBLIC_BASE_URL ASSERT_DEV_AUTH_OFF ASSERT_NO_LAN_PROXY BLUE_GREEN PORT_A PORT_B DRAIN CADDY_UPSTREAM_FILE CADDY_RELOAD_CMD_B64 PUBLIC_SMOKE_URL" >&2
  exit 2
fi

REMOTE_DIR="$1"
APP_DIR="$2"
DEPLOY_SOURCE="$3"
DEPLOY_GIT_COMMIT="$4"
DEPLOY_GIT_COMMIT_FULL="$5"
PORT="$6"
UVICORN_HOST="$7"
REQUIRE_VECTOR="$8"
HEALTHZ_TIMEOUT="$9"
EXPECT_INSTANCE_ID="${10}"
EXPECT_PUBLIC_BASE_URL="${11}"
ASSERT_DEV_AUTH_OFF="${12}"
ASSERT_NO_LAN_PROXY="${13}"
BLUE_GREEN="${14}"
BLUE_GREEN_PORT_A="${15}"
BLUE_GREEN_PORT_B="${16}"
BLUE_GREEN_DRAIN_SEC="${17}"
CADDY_UPSTREAM_FILE="${18}"
CADDY_RELOAD_CMD="$(printf '%s' "${19}" | base64 -d)"
BLUE_GREEN_PUBLIC_SMOKE_URL="${20}"
if [[ "${BLUE_GREEN_PUBLIC_SMOKE_URL}" == "__MA3_EMPTY__" ]]; then
  BLUE_GREEN_PUBLIC_SMOKE_URL=""
fi
ENV="${REMOTE_DIR}/ma3.env"

[[ -f "${ENV}" ]] || {
  echo "FATAL: ${ENV} missing; provision production ma3.env first." >&2
  exit 1
}
if [[ "${DEPLOY_SOURCE}" == "git" ]]; then
  [[ -f "${APP_DIR}/.ma3-release-commit" ]] || {
    echo "FATAL: release marker missing in ${APP_DIR}" >&2
    exit 1
  }
  [[ "$(tr -d '[:space:]' <"${APP_DIR}/.ma3-release-commit")" == "${DEPLOY_GIT_COMMIT_FULL}" ]] || {
    echo "FATAL: release marker does not match ${DEPLOY_GIT_COMMIT_FULL}" >&2
    exit 1
  }
fi

get() { grep -E "^$1=" "${ENV}" | tail -1 | cut -d= -f2- || true; }
fail=0
[[ "${ASSERT_DEV_AUTH_OFF}" == "1" && "$(get MA3_DEV_AUTH)" == "1" ]] && {
  echo "ASSERT FAIL: MA3_DEV_AUTH=1 in production" >&2
  fail=1
}
[[ "$(get MA3_INSTANCE_ID)" != "${EXPECT_INSTANCE_ID}" ]] && {
  echo "ASSERT FAIL: instance_id $(get MA3_INSTANCE_ID) != ${EXPECT_INSTANCE_ID}" >&2
  fail=1
}
[[ "$(get MA3_PUBLIC_BASE_URL)" != "${EXPECT_PUBLIC_BASE_URL}" ]] && {
  echo "ASSERT FAIL: public_base_url $(get MA3_PUBLIC_BASE_URL) != ${EXPECT_PUBLIC_BASE_URL}" >&2
  fail=1
}
if [[ "${ASSERT_NO_LAN_PROXY}" == "1" ]] && grep -qE \
  '^(HTTP_PROXY|HTTPS_PROXY|MA3_HTTP_PROXY|MA3_HTTPS_PROXY)=' "${ENV}"; then
  echo "ASSERT FAIL: LAN proxy vars present in production ma3.env" >&2
  fail=1
fi
[[ "${fail}" -eq 0 ]] || {
  echo "Aborting: production ma3.env failed invariants." >&2
  exit 1
}

activate_git_release() {
  [[ "${DEPLOY_SOURCE}" == "git" ]] || return 0
  local current="${REMOTE_DIR}/current" previous="${REMOTE_DIR}/previous"
  local old="" tmp=""
  mkdir -p "${REMOTE_DIR}/data"
  if [[ -L "${current}" ]]; then old="$(readlink -f "${current}")"; fi
  if [[ -n "${old}" && "${old}" != "${APP_DIR}" ]]; then
    tmp="${REMOTE_DIR}/.previous.tmp.$$"
    ln -s "${old}" "${tmp}"
    mv -Tf "${tmp}" "${previous}"
  fi
  tmp="${REMOTE_DIR}/.current.tmp.$$"
  ln -s "${APP_DIR}" "${tmp}"
  mv -Tf "${tmp}" "${current}"
  printf '%s\n' "${DEPLOY_GIT_COMMIT_FULL}" >"${REMOTE_DIR}/data/deployed_commit"
  mkdir -p "${REMOTE_DIR}/bin"
  install -m 0755 "${APP_DIR}/deploy/common/prepare_git_release.sh" \
    "${REMOTE_DIR}/bin/prepare_git_release.sh"
  echo "==> activated release ${APP_DIR}"
}

persist_deploy_commit() {
  if grep -q '^MA3_GIT_COMMIT=' "${ENV}"; then
    sed -i "s/^MA3_GIT_COMMIT=.*/MA3_GIT_COMMIT=${DEPLOY_GIT_COMMIT}/" "${ENV}"
  else
    echo "MA3_GIT_COMMIT=${DEPLOY_GIT_COMMIT}" >>"${ENV}"
  fi
}

cd "${APP_DIR}/code/server"
[[ -d .venv ]] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

if [[ "${BLUE_GREEN}" == "1" ]]; then
  # shellcheck disable=SC1091
  source "${APP_DIR}/deploy/common/bluegreen_remote.sh"
  mkdir -p "$(dirname "${CADDY_UPSTREAM_FILE}")"
  if [[ ! -f "${CADDY_UPSTREAM_FILE}" ]]; then
    echo "==> seeding CADDY_UPSTREAM_FILE=${CADDY_UPSTREAM_FILE} (ensure Caddyfile imports it)"
    cp -f "${APP_DIR}/deploy/caddy/upstream.caddy.example" "${CADDY_UPSTREAM_FILE}"
  fi
  bluegreen_cutover
else
  pkill -f "uvicorn app.main:app.*--port ${PORT}" || true
  sleep 3
  set -a
  # shellcheck disable=SC1090
  source "${ENV}"
  set +a
  export MA3_GIT_COMMIT="${DEPLOY_GIT_COMMIT}"
  unset MA3_DISABLE_EMBEDDINGS || true
  nohup .venv/bin/python -m uvicorn app.main:app \
    --host "${UVICORN_HOST}" --port "${PORT}" --app-dir . \
    >/tmp/ma3-v1-uvicorn.log 2>&1 &
  echo $! >"${REMOTE_DIR}/ma3.pid"

  ready=0
  deadline=$((SECONDS + HEALTHZ_TIMEOUT))
  while ((SECONDS < deadline)); do
    if curl -sf "http://127.0.0.1:${PORT}/healthz" >/tmp/ma3-healthz.json 2>/dev/null; then
      if [[ "${REQUIRE_VECTOR}" != "1" ]]; then ready=1; break; fi
      feats="$(python3 -c "import json;print(','.join(json.load(open('/tmp/ma3-healthz.json')).get('features',[])))")"
      [[ "${feats}" == *vector* ]] && { ready=1; break; }
    fi
    sleep 2
  done
  [[ "${ready}" -eq 1 ]] || {
    echo "healthz not ready after ${HEALTHZ_TIMEOUT}s" >&2
    tail -40 /tmp/ma3-v1-uvicorn.log >&2
    exit 1
  }
  python3 -m json.tool /tmp/ma3-healthz.json
fi

persist_deploy_commit
activate_git_release
