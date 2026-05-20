#!/usr/bin/env bash
# pg_restore_walk.sh — Postgres restore_command for ma3 PITR.
#
# PG calls this with %f (wanted WAL filename) %p (target path inside PGDATA).
# Walks every directory in $MA3_PG_WAL_DIRS (colon-separated) and copies
# the first match. Exit 0 on hit, non-zero on miss (PG treats consecutive
# misses as end-of-recovery, which is the desired behavior).
#
# Env consumed:
#   MA3_PG_WAL_DIRS   colon-separated list of CephFS WAL directories,
#                     in priority order. Required.

set -euo pipefail
IFS=$'\n\t'

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <%f wal-name> <%p target-path>" >&2
  exit 64
fi

NAME="$1"
TARGET="$2"

log() { printf '[%s] pg_restore_walk: %s\n' "$(date -u +%FT%TZ)" "$*" >&2; }

DIRS="${MA3_PG_WAL_DIRS:-}"
if [[ -z "$DIRS" ]]; then
  log "MA3_PG_WAL_DIRS not set"
  exit 65
fi

IFS=':' read -r -a dirs <<<"$DIRS"
for d in "${dirs[@]}"; do
  [[ -z "$d" ]] && continue
  src="$d/$NAME"
  if [[ -f "$src" ]]; then
    cp -- "$src" "$TARGET"
    log "restored $NAME from $d"
    exit 0
  fi
done

# Miss is normal at end-of-recovery; do NOT log loudly here, PG will
# treat exit non-zero as "no more WAL" and finish recovery.
exit 1
