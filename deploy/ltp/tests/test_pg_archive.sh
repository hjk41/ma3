#!/usr/bin/env bash
# Hermetic test for pg_archive.sh — exercises the no-PG paths:
# fresh archive, idempotent re-archive, divergent collision detection.
# Skips if `sha256sum` or `flock` is missing.

set -euo pipefail
IFS=$'\n\t'

THIS_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$THIS_DIR/../pg_archive.sh"

if ! command -v sha256sum >/dev/null 2>&1 || ! command -v flock >/dev/null 2>&1; then
  echo "skip: sha256sum/flock missing" >&2
  exit 0
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

src="$TMP/src/00000001000000000000000A"
mkdir -p "$(dirname "$src")"
printf 'wal-content-v1' > "$src"

export MA3_PG_ARCHIVE_DIR="$TMP/dest"

# 1) Fresh archive
"$SCRIPT" "$src" "$(basename "$src")"
[[ -f "$MA3_PG_ARCHIVE_DIR/$(basename "$src")" ]] || { echo "FAIL: dest missing"; exit 1; }
echo "ok: fresh archive"

# 2) Idempotent re-archive (same sha256 -> noop, exit 0)
"$SCRIPT" "$src" "$(basename "$src")"
echo "ok: idempotent re-archive"

# 3) Divergent collision: change source, expect non-zero
printf 'wal-content-v2-different' > "$src"
if "$SCRIPT" "$src" "$(basename "$src")" 2>/tmp/pg_archive_test.err; then
  echo "FAIL: expected non-zero on divergent content"; cat /tmp/pg_archive_test.err; exit 1
fi
echo "ok: divergent collision rejected"

# 4) Missing env
unset MA3_PG_ARCHIVE_DIR
if "$SCRIPT" "$src" "$(basename "$src")" 2>/dev/null; then
  echo "FAIL: expected non-zero when MA3_PG_ARCHIVE_DIR unset"; exit 1
fi
echo "ok: missing env rejected"

echo "PASS: pg_archive.sh standalone tests"
