#!/usr/bin/env bash
# Hermetic test for pg_restore_walk.sh — exercises hit/miss across
# multiple wal_dirs.

set -euo pipefail
IFS=$'\n\t'

THIS_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$THIS_DIR/../pg_restore_walk.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/wal_a" "$TMP/wal_b" "$TMP/target"
printf 'segA' > "$TMP/wal_a/00000001000000000000000A"
printf 'segB' > "$TMP/wal_b/00000001000000000000000B"

export MA3_PG_WAL_DIRS="$TMP/wal_a:$TMP/wal_b"

# 1) Hit in first dir
"$SCRIPT" "00000001000000000000000A" "$TMP/target/x"
diff <(printf 'segA') "$TMP/target/x"
echo "ok: first-dir hit"

# 2) Hit in second dir (fall-through)
"$SCRIPT" "00000001000000000000000B" "$TMP/target/y"
diff <(printf 'segB') "$TMP/target/y"
echo "ok: second-dir hit (priority walk)"

# 3) Miss → exit 1
if "$SCRIPT" "DOES_NOT_EXIST" "$TMP/target/z" 2>/dev/null; then
  echo "FAIL: expected miss to exit non-zero"; exit 1
fi
echo "ok: miss returns non-zero"

# 4) Empty MA3_PG_WAL_DIRS → exit non-zero
unset MA3_PG_WAL_DIRS
if "$SCRIPT" "00000001000000000000000A" "$TMP/target/q" 2>/dev/null; then
  echo "FAIL: expected non-zero when MA3_PG_WAL_DIRS unset"; exit 1
fi
echo "ok: missing env rejected"

echo "PASS: pg_restore_walk.sh standalone tests"
