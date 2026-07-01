#!/usr/bin/env bash
# Agent install/upgrade test in Docker; ma3 runs on HOST (202), not in compose.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${SCRIPT_DIR}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found" >&2
  exit 1
fi

COMPOSE=(docker compose)
if ! docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
fi

MA3_RESTORE_VERSION="${MA3_RESTORE_VERSION:-1.0.0}"
MA3_HOST_MA3_URL="${MA3_HOST_MA3_URL:-http://host.docker.internal:8000}"

cleanup() {
  echo "==> cleanup: restore host ma3 skill_version=${MA3_RESTORE_VERSION}"
  bash "${SCRIPT_DIR}/scripts/restart_host_ma3.sh" "${MA3_RESTORE_VERSION}" || true
  "${COMPOSE[@]}" down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

chmod +x scripts/*.sh

build_runner() {
  mkdir -p binaries
  if command -v droid >/dev/null 2>&1; then
    cp "$(command -v droid)" binaries/droid
    echo "bundled host droid: $(command -v droid)"
  fi
  HTTP_PROXY="${HTTP_PROXY:-}" HTTPS_PROXY="${HTTPS_PROXY:-}" \
    "${COMPOSE[@]}" build runner
}

run_phase() {
  local phase="$1"
  local skill="$2"
  export MA3_SKILL_VERSION="${skill}"
  export MA3_EXPECT_SKILL_VERSION="${skill}"
  export VERIFY_PHASE="${phase}"
  export MA3_HOST_MA3_URL
  "${COMPOSE[@]}" run --rm runner || {
    echo "ERROR: runner phase ${phase} failed" >&2
    exit 1
  }
}

echo "==> Phase 1: install against host ma3 (skill ${MA3_RESTORE_VERSION})"
"${COMPOSE[@]}" down --remove-orphans >/dev/null 2>&1 || true
build_runner
bash "${SCRIPT_DIR}/scripts/restart_host_ma3.sh" "${MA3_RESTORE_VERSION}"
run_phase install "${MA3_RESTORE_VERSION}"

echo "==> Phase 2: upgrade after host ma3 bump (skill 2.0.0)"
bash "${SCRIPT_DIR}/scripts/restart_host_ma3.sh" "2.0.0"
run_phase upgrade "2.0.0"

echo "==> agent-client-sync docker test passed (host ma3 + 4 real agent CLIs)"
