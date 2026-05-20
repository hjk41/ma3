#!/usr/bin/env bash
# pg_archive.sh — Postgres archive_command wrapper for ma3 PITR.
#
# Postgres calls this with %p (full source path) and %f (WAL filename).
# Ships the WAL segment to $MA3_PG_ARCHIVE_DIR on CephFS via an atomic
# .partial->mv, with sha256 idempotency so a repeated archive of the same
# segment is a no-op. Returns non-zero on any failure so PG retries.
#
# Env consumed:
#   MA3_PG_ARCHIVE_DIR   target directory on CephFS (per-instance).
#                        Required.
# Logs append to /var/log/ma3/pg_archive.log (one line per call) plus
# stderr.

set -euo pipefail
IFS=$'\n\t'

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <%p source-path> <%f wal-filename>" >&2
  exit 64
fi

SRC="$1"
NAME="$2"

log() { printf '[%s] pg_archive: %s\n' "$(date -u +%FT%TZ)" "$*" >&2; }
audit() {
  mkdir -p /var/log/ma3 2>/dev/null || true
  printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*" >> /var/log/ma3/pg_archive.log 2>/dev/null || true
}

DEST_DIR="${MA3_PG_ARCHIVE_DIR:-}"
if [[ -z "$DEST_DIR" ]]; then
  log "MA3_PG_ARCHIVE_DIR not set"
  exit 65
fi

mkdir -p "$DEST_DIR"
DEST="$DEST_DIR/$NAME"
PARTIAL="$DEST.partial.$$"

LOCK_DIR="/tmp/ma3-archive"
mkdir -p "$LOCK_DIR"
LOCK_FILE="$LOCK_DIR/$NAME.lock"

# Per-WAL flock: defensive against any same-name race
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log "another archiver holds the lock for $NAME; postgres will retry"
  exit 75
fi

if [[ -f "$DEST" ]]; then
  src_sha=$(sha256sum "$SRC" | awk '{print $1}')
  dst_sha=$(sha256sum "$DEST" | awk '{print $1}')
  if [[ "$src_sha" == "$dst_sha" ]]; then
    audit "noop $NAME bytes=$(stat -c %s "$DEST") sha256=${src_sha:0:12}"
    exit 0
  fi
  log "DIVERGENT archive collision: $NAME already exists with sha256=${dst_sha:0:12} but source is sha256=${src_sha:0:12}; refusing to overwrite"
  audit "collision $NAME src_sha256=${src_sha:0:12} dst_sha256=${dst_sha:0:12}"
  exit 73
fi

# Atomic copy: cp to .partial, fsync, rename
cp -- "$SRC" "$PARTIAL"
# fsync the .partial; portable across busybox/coreutils
python3 - <<PY 2>/dev/null || sync
import os, sys
fd = os.open("$PARTIAL", os.O_RDONLY)
try:
    os.fsync(fd)
finally:
    os.close(fd)
PY
mv -- "$PARTIAL" "$DEST"

bytes=$(stat -c %s "$DEST")
sha=$(sha256sum "$DEST" | awk '{print $1}')
audit "archived $NAME bytes=$bytes sha256=${sha:0:12}"
log "archived $NAME bytes=$bytes"
exit 0
