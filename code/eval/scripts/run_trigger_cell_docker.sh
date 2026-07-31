#!/usr/bin/env bash
# Run one trigger matrix cell inside Docker (agent CLIs + isolated HOME volume).
# Replaces host-side HOME isolation: binaries come from agent-client-sync-runner image;
# scenario compose uses host Docker via mounted socket (--network host for verify ports).
set -euo pipefail

WORKER_ID="${1:?worker id}"
ARM="${2:?arm}"
RUNTIME="${3:?runtime}"
SCENARIO="${4:?scenario}"
ROUND="${5:?round}"

EVAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$EVAL_ROOT/../.." && pwd)"
HOST_HOME="${TRIGGER_HOST_HOME:-/home/hct}"
IMAGE="${TRIGGER_DOCKER_IMAGE:-ma3-trigger-worker:latest}"
PROXY="${DUCKCODING_HTTPS_PROXY:-${HTTPS_PROXY:-http://192.168.31.200:1080}}"
HOST_UID="${TRIGGER_DOCKER_UID:-$(id -u)}"
HOST_GID="${TRIGGER_DOCKER_GID:-$(id -g)}"
DOCKER_GID="${TRIGGER_DOCKER_SOCK_GID:-$(getent group docker | cut -d: -f3)}"

# shellcheck disable=SC1091
source "$EVAL_ROOT/scripts/load_secrets.sh"

if [[ -z "${DUCKCODING_CODEX_TOKEN:-}" && -f "${HOST_HOME}/.bashrc" ]]; then
  eval "$(grep -E '^export DUCKCODING_CODEX_TOKEN=' "${HOST_HOME}/.bashrc" | head -1)" || true
fi

WORKER_ROOT="${TRIGGER_WORKER_ROOT:-$EVAL_ROOT/results/trigger/workers}/w${WORKER_ID}"
mkdir -p "$WORKER_ROOT/home" "$WORKER_ROOT/logs"
CELL_LOG="${WORKER_ROOT}/cell.log"

# Mount repo at the SAME host absolute path so docker.sock compose bind-mounts resolve
# (daemon sees host paths; /repo aliases would break P2/P3 volume mounts).
CONT_CSV="${TRIGGER_CSV:-$EVAL_ROOT/results/trigger/runs.csv}"
CONT_LOG="${TRIGGER_MATRIX_LOG:-$EVAL_ROOT/results/trigger/experiment-matrix.log}"
CONT_WORKER_ROOT="${TRIGGER_WORKER_ROOT:-$EVAL_ROOT/results/trigger/workers}"

NAME="trigger-cell-w${WORKER_ID}-${SCENARIO}-r${ROUND}-$$"
NAME="${NAME:0:63}"

{
  echo "===== docker cell ${ARM}-${RUNTIME}-${SCENARIO}-r${ROUND} $(date -u +%Y-%m-%dT%H:%M:%SZ) image=$IMAGE ====="
} >>"$CELL_LOG"

docker run --rm --name "$NAME" \
  --network host \
  --user "${HOST_UID}:${HOST_GID}" \
  --group-add "${DOCKER_GID}" \
  --add-host=host.docker.internal:host-gateway \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /usr/bin/docker:/usr/bin/docker:ro \
  -v /usr/libexec/docker/cli-plugins:/usr/libexec/docker/cli-plugins:ro \
  -v "${REPO_ROOT}:${REPO_ROOT}" \
  -v "${HOST_HOME}:/host-home:ro" \
  -e TRIGGER_HOST_HOME=/host-home \
  -e TRIGGER_WORKER_ROOT="$CONT_WORKER_ROOT" \
  -e TRIGGER_WORKER_MODE=1 \
  -e TRIGGER_DOCKER_CELL=1 \
  -e TRIGGER_CSV="$CONT_CSV" \
  -e TRIGGER_MATRIX_LOG="$CONT_LOG" \
  -e TRIGGER_SKIP_LOCAL_RESTART=1 \
  -e MA3_BASE_URL="${MA3_BASE_URL:-http://127.0.0.1:8010}" \
  -e MA3_KEY_LOCAL="${MA3_KEY_LOCAL:-}" \
  -e MA3_API_KEY="${MA3_KEY_LOCAL:-${MA3_API_KEY:-}}" \
  -e MA3_KEY_REMOTE="${MA3_KEY_REMOTE:-}" \
  -e MA3_KEY_CURSOR_CLI="${MA3_KEY_CURSOR_CLI:-}" \
  -e DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}" \
  -e CURSOR_API_KEY="${CURSOR_API_KEY:-}" \
  -e FACTORY_API_KEY="${FACTORY_API_KEY:-}" \
  -e DUCKCODING_CODEX_TOKEN="${DUCKCODING_CODEX_TOKEN:-}" \
  -e DUCKCODING_HTTPS_PROXY="$PROXY" \
  -e HTTPS_PROXY="$PROXY" \
  -e HTTP_PROXY="$PROXY" \
  -e https_proxy="$PROXY" \
  -e http_proxy="$PROXY" \
  -e ALL_PROXY="$PROXY" \
  -e NO_PROXY="127.0.0.1,localhost,::1,192.168.0.0/16,10.0.0.0/8" \
  -e no_proxy="127.0.0.1,localhost,::1,192.168.0.0/16,10.0.0.0/8" \
  -e PATH="/opt/npm-global/bin:/usr/local/bin:/usr/bin:/bin" \
  -w "$EVAL_ROOT" \
  --entrypoint bash \
  "$IMAGE" \
  "${EVAL_ROOT}/scripts/run_trigger_cell.sh" "$WORKER_ID" "$ARM" "$RUNTIME" "$SCENARIO" "$ROUND" \
  >>"$CELL_LOG" 2>&1
