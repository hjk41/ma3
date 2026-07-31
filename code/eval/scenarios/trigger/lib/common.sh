#!/usr/bin/env bash
# Shared helpers for trigger-p* scenarios.
set -euo pipefail

trigger_scenario_root() {
  cd "$(dirname "${BASH_SOURCE[1]}")/.." && pwd
}

trigger_eval_root() {
  cd "$(dirname "${BASH_SOURCE[1]}")/../../.." && pwd
}

trigger_wrapped_scenario_dir() {
  local wrap="$1"
  trigger_eval_root
  echo "$(trigger_eval_root)/scenarios/$wrap"
}

trigger_print_prompt() {
  local dir="$1"
  echo "--- user prompt (neutral; do not add ma3 hints) ---"
  cat "$dir/prompt.txt"
  echo "--- end prompt ---"
}

trigger_compose_up() {
  local dir="$1"
  if [[ ! -f "$dir/docker-compose.yml" ]]; then
    return 0
  fi
  (
    cd "$dir"
    docker compose down -v --remove-orphans >/dev/null 2>&1 || true
    docker compose up -d --build
  )
  sleep 2
}

trigger_compose_down() {
  local dir="$1"
  if [[ -f "$dir/docker-compose.yml" ]]; then
    (cd "$dir" && docker compose down -v --remove-orphans) >/dev/null 2>&1 || true
  fi
}
