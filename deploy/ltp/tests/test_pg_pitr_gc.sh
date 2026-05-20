#!/usr/bin/env bash
# Hermetic test for pg_pitr_gc.sh — verifies retention rules without PG.

set -euo pipefail
IFS=$'\n\t'

THIS_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$THIS_DIR/../pg_pitr_gc.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

INST="ma3-test-cur"
OTHER_NEW="ma3-test-newer-other"
OTHER_OLD="ma3-test-older-other"

export MA3_BACKUP_DIR="$TMP"
export MA3_INSTANCE_ID="$INST"
export MA3_PG_ARCHIVE_DIR="$TMP/wal/$INST"
export MA3_PG_BASEBACKUP_RETENTION=2
export MA3_PG_OLD_INSTANCE_RETENTION_DAYS=1

# --- Layout: 5 basebackups for current instance with monotonic mtimes ---
mkdir -p "$TMP/basebackups/$INST" "$MA3_PG_ARCHIVE_DIR"
for i in 1 2 3 4 5; do
  d="$TMP/basebackups/$INST/snap$i"
  mkdir -p "$d"
  touch -d "$(date -u -d "$((i*60)) seconds ago" +%FT%TZ)" "$d"
done

# WAL files: half pre-floor (older than oldest surviving snap), half post
mkdir -p "$MA3_PG_ARCHIVE_DIR"
old_t=$(date -u -d "1 hour ago" +%FT%TZ)
new_t=$(date -u -d "10 seconds ago" +%FT%TZ)
touch -d "$old_t" "$MA3_PG_ARCHIVE_DIR/000000010000000000000001"
touch -d "$old_t" "$MA3_PG_ARCHIVE_DIR/000000010000000000000002"
touch -d "$new_t" "$MA3_PG_ARCHIVE_DIR/000000010000000000000003"
touch -d "$new_t" "$MA3_PG_ARCHIVE_DIR/000000010000000000000004"

# Cross-instance dirs: one fresh (kept), one old (pruned)
mkdir -p "$TMP/wal/$OTHER_NEW" "$TMP/wal/$OTHER_OLD"
touch -d "$new_t" "$TMP/wal/$OTHER_NEW/000000010000000000000099"
touch -d "$(date -u -d "3 days ago" +%FT%TZ)" "$TMP/wal/$OTHER_OLD/000000010000000000000088"

# pitr_manifest.json claims OTHER_NEW as basebackup_instance_id (kept)
cat > "$TMP/pitr_manifest.json" <<JSON
{"schema_version":1,"basebackup_instance_id":"$OTHER_NEW","wal_dirs":["wal/$INST","wal/$OTHER_NEW","wal/$OTHER_OLD"]}
JSON

# --- Run GC ---
bash "$SCRIPT"

# --- Assertions ---
remaining_bbs=$(find "$TMP/basebackups/$INST" -mindepth 1 -maxdepth 1 -type d | wc -l)
if [[ "$remaining_bbs" -ne 2 ]]; then
  echo "FAIL: expected 2 basebackups remaining, got $remaining_bbs"
  ls -la "$TMP/basebackups/$INST"
  exit 1
fi
echo "ok: basebackup retention enforced ($remaining_bbs of 5)"

remaining_wal=$(find "$MA3_PG_ARCHIVE_DIR" -maxdepth 1 -type f | wc -l)
if [[ "$remaining_wal" -gt 2 ]]; then
  echo "FAIL: expected ≤2 WAL files (pre-floor pruned), got $remaining_wal"
  ls -la "$MA3_PG_ARCHIVE_DIR"
  exit 1
fi
echo "ok: pre-floor WAL pruned ($remaining_wal remain)"

[[ -d "$TMP/wal/$OTHER_NEW" ]] || { echo "FAIL: kept-by-manifest dir was pruned"; exit 1; }
echo "ok: basebackup_instance_id wal dir preserved"

[[ -d "$TMP/wal/$OTHER_OLD" ]] && { echo "FAIL: stale cross-instance dir not pruned"; exit 1; } || true
echo "ok: stale cross-instance dir pruned"

# pitr_manifest.json should drop the pruned wal_dir
new_manifest_dirs=$(python3 -c "import json; print(','.join(json.load(open('$TMP/pitr_manifest.json'))['wal_dirs']))")
if [[ "$new_manifest_dirs" == *"$OTHER_OLD"* ]]; then
  echo "FAIL: pitr_manifest.json still references pruned dir"
  echo "  wal_dirs=$new_manifest_dirs"
  exit 1
fi
echo "ok: pitr_manifest.json wal_dirs pruned ($new_manifest_dirs)"

echo "PASS: pg_pitr_gc.sh standalone tests"
