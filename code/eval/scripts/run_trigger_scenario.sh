#!/usr/bin/env bash
# Prepare a trigger eval scenario: setup, optional KB seed, print prompt, optional verify.
set -euo pipefail

EVAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$EVAL_ROOT/scripts/load_secrets.sh"

SCENARIO="${1:?scenario id required, e.g. trigger-p2}"
shift || true

SCENARIO_DIR="$EVAL_ROOT/scenarios/$SCENARIO"
[[ -d "$SCENARIO_DIR" ]] || { echo "missing scenario: $SCENARIO" >&2; exit 1; }

DO_SEED=0
DO_VERIFY=0
DO_PROMPT=0
DO_SETUP=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed-kb) DO_SEED=1 ;;
    --verify-only) DO_VERIFY=1; DO_SETUP=1 ;;
    --print-prompt) DO_PROMPT=1 ;;
    --no-setup) DO_SETUP=0 ;;
    *) echo "unknown flag: $1" >&2; exit 1 ;;
  esac
  shift
done

if [[ "$DO_VERIFY" == "1" && "$DO_PROMPT" == "0" && "$DO_SEED" == "0" ]]; then
  :
elif [[ "$DO_PROMPT" == "0" && "$DO_SEED" == "0" && "$DO_VERIFY" == "0" ]]; then
  DO_PROMPT=1
fi

cleanup() {
  if [[ -f "$SCENARIO_DIR/docker-compose.yml" && "${KEEP_UP:-0}" != "1" && "$DO_VERIFY" == "1" ]]; then
    (cd "$SCENARIO_DIR" && docker compose down -v --remove-orphans) >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "======== trigger scenario: $SCENARIO ========"

if [[ "$DO_SETUP" == "1" && -x "$SCENARIO_DIR/setup.sh" ]]; then
  bash "$SCENARIO_DIR/setup.sh"
fi

if [[ "$DO_SEED" == "1" ]]; then
  bash "$EVAL_ROOT/scripts/seed_trigger_kb.sh" "$SCENARIO"
fi

if [[ "$DO_PROMPT" == "1" ]]; then
  echo ""
  echo "Working directory: $SCENARIO_DIR"
  if [[ -f "$SCENARIO_DIR/prompt.txt" ]]; then
    echo "--- user prompt ---"
    cat "$SCENARIO_DIR/prompt.txt"
    echo "--- end prompt ---"
  fi
  if [[ -f "$SCENARIO_DIR/workspace/seeded_record_ids.json" ]]; then
    echo "Seeded records: $(cat "$SCENARIO_DIR/workspace/seeded_record_ids.json")"
  fi
fi

if [[ "$DO_VERIFY" == "1" ]]; then
  if [[ -x "$SCENARIO_DIR/verify.sh" ]]; then
    bash "$SCENARIO_DIR/verify.sh"
  else
    echo "no verify.sh" >&2
    exit 1
  fi
fi

echo "done: $SCENARIO"
