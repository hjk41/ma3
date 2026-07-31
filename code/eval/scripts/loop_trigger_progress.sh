#!/usr/bin/env bash
# Minute tick for trigger matrix progress reporting (session loop).
set -eu
while true; do
  sleep 60
  printf '%s\n' 'AGENT_LOOP_TICK_trigger_progress {"prompt":"Check trigger matrix progress and report briefly in Chinese: done/216, by arm/runtime, active cells, recent DONE/FAIL, ETA"}'
done
