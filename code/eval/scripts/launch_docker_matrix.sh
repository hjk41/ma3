#!/usr/bin/env bash
set -euo pipefail
cd /home/hct/ma3-trigger-wt
# shellcheck disable=SC1091
source /home/hct/ma3/.venv/bin/activate
set -a
# shellcheck disable=SC1091
source code/eval/secrets/secrets.env
set +a
eval "$(grep -E '^export DUCKCODING_CODEX_TOKEN=' ~/.bashrc | head -1)" || true
# DeepSeek / Anthropic may already be in the parent env; pull from bashrc if present
eval "$(grep -E '^export DEEPSEEK_API_KEY=' ~/.bashrc | head -1)" || true
export PATH="${HOME}/.local/bin:${HOME}/.npm-global/bin:${PATH}"
export MA3_BASE_URL=http://127.0.0.1:8010
export MA3_API_KEY="${MA3_KEY_LOCAL}"
export DUCKCODING_HTTPS_PROXY=http://192.168.31.200:1080
export TRIGGER_SKIP_LOCAL_RESTART=1
export TRIGGER_ROUNDS=3
export TRIGGER_PARALLEL_WORKERS=4
export TRIGGER_SKIP_DONE=1
export TRIGGER_CSV=/home/hct/ma3-trigger-wt/code/eval/results/trigger/runs-local-4arm-3rt.csv
export TRIGGER_MATRIX_LOG=/home/hct/ma3-trigger-wt/code/eval/results/trigger/experiment-matrix-local-4arm-3rt.log
export TRIGGER_ARMS="A0-baseline A1-gate C0-skill C1-gate-skill"
export TRIGGER_RUNTIMES="cursor-agent claude codex"
export TRIGGER_DOCKER_IMAGE=ma3-trigger-worker:latest
export TRIGGER_CELL_RUNNER=/home/hct/ma3-trigger-wt/code/eval/scripts/run_trigger_cell_docker.sh
export NO_PROXY="127.0.0.1,localhost,::1,192.168.0.0/16,10.0.0.0/8"
export no_proxy="$NO_PROXY"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] launch_docker_matrix start pid=$$" | tee -a "$TRIGGER_MATRIX_LOG"
exec bash code/eval/scripts/run_full_trigger_matrix.sh
