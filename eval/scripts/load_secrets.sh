#!/usr/bin/env bash
# Source eval secrets for orchestrator and scenario scripts.
# Usage: source eval/scripts/load_secrets.sh
set -euo pipefail

_EVAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_SECRETS_DIR="${EVAL_SECRETS_DIR:-$_EVAL_ROOT/secrets}"

if [[ -f "$_SECRETS_DIR/secrets.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$_SECRETS_DIR/secrets.env"
  set +a
elif [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then
  : # already exported in shell
elif [[ -f "${HOME}/.bashrc" ]] && grep -q DEEPSEEK_API_KEY "${HOME}/.bashrc" 2>/dev/null; then
  # Fallback for dev hosts — prefer explicit secrets.env
  eval "$(grep '^export DEEPSEEK_API_KEY=' "${HOME}/.bashrc" || true)"
fi

if [[ -f "$_SECRETS_DIR/agent-keys.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$_SECRETS_DIR/agent-keys.env"
  set +a
fi

export EVAL_ROOT="$_EVAL_ROOT"
export EVAL_SECRETS_DIR="$_SECRETS_DIR"
export MA3_BASE_URL="${MA3_BASE_URL:-http://127.0.0.1:8000}"

if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  echo "warn: DEEPSEEK_API_KEY not set — copy eval/secrets/secrets.env.example to secrets.env" >&2
fi
