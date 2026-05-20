#!/usr/bin/env bash
# pg_basebackup_cron.sh — periodic pg_basebackup + pitr_manifest update
# + GC. Designed to be invoked from cron with the standard
# `set -a; . /root/ma3-instance/ma3.env; set +a` preamble.
#
# Behavior:
#   1. flock $MA3_BACKUP_DIR/.basebackup.lock so concurrent crons don't
#      overlap.
#   2. Run pg_basebackup -F t -X stream -z to per-instance dir/<ts>/.
#   3. Write per-backup manifest.json next to it.
#   4. Atomically update $MA3_BACKUP_DIR/pitr_manifest.json (.tmp -> fsync
#      -> rename) so it points at this new basebackup.
#   5. Call pg_pitr_gc.sh to enforce retention.
#
# Env consumed:
#   MA3_BACKUP_DIR                 required
#   MA3_INSTANCE_ID                required
#   MA3_PG_ARCHIVE_DIR             default $MA3_BACKUP_DIR/wal/<inst>
#   PGUSER, PGHOST, PGPORT, PGPASSWORD  Postgres connection (PGPASSWORD
#                                  pulled from ma3.env)
#   MA3_REPO_DIR                   used to find pg_pitr_gc.sh

set -euo pipefail
IFS=$'\n\t'

log() { printf '[%s] pg_basebackup_cron: %s\n' "$(date -u +%FT%TZ)" "$*" >&2; }

: "${MA3_BACKUP_DIR:?MA3_BACKUP_DIR required}"
: "${MA3_INSTANCE_ID:?MA3_INSTANCE_ID required}"
: "${PGUSER:?PGUSER required}"
: "${PGHOST:=127.0.0.1}"
: "${PGPORT:=5433}"
: "${MA3_PG_ARCHIVE_DIR:=$MA3_BACKUP_DIR/wal/$MA3_INSTANCE_ID}"
: "${MA3_REPO_DIR:=/root/ma3-instance/repo}"

LOCK="$MA3_BACKUP_DIR/.basebackup.lock"
mkdir -p "$MA3_BACKUP_DIR"
exec 9>"$LOCK"
if ! flock -n 9; then
  log "another basebackup is running; skipping"
  exit 0
fi

ts=$(date -u +%Y%m%d-%H%M%SZ)
dest="$MA3_BACKUP_DIR/basebackups/$MA3_INSTANCE_ID/$ts"
mkdir -p "$dest"

log "pg_basebackup -> $dest"
if ! pg_basebackup -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" \
      -F t -X stream -z -P -D "$dest" >&2; then
  log "pg_basebackup FAILED; cleaning up partial dir"
  rm -rf -- "$dest"
  exit 1
fi

# Best-effort start_lsn from backup_label inside base.tar.gz; fall back
# to gross timestamp.
start_lsn=""
if [[ -f "$dest/backup_manifest" ]]; then
  start_lsn=$(python3 -c "
import json
try:
    d=json.load(open('$dest/backup_manifest'))
    print(d.get('Start-LSN') or d.get('Start-Lsn') or '')
except Exception:
    print('')
" 2>/dev/null || true)
fi

cat > "$dest/manifest.json.tmp" <<JSON
{
  "schema_version": 1,
  "instance_id": "$MA3_INSTANCE_ID",
  "created_at": "$(date -u +%FT%TZ)",
  "start_lsn": "$start_lsn",
  "pg_version": $(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -tAc 'SHOW server_version_num;' 2>/dev/null || echo 0)
}
JSON
mv -- "$dest/manifest.json.tmp" "$dest/manifest.json"

# Update global pitr_manifest.json atomically
manifest="$MA3_BACKUP_DIR/pitr_manifest.json"
python3 - "$manifest" "$MA3_BACKUP_DIR" "$dest" "$MA3_INSTANCE_ID" "$MA3_PG_ARCHIVE_DIR" "$start_lsn" <<'PY'
import json, os, sys
mpath, root, dest, instance, archive_dir, start_lsn = sys.argv[1:]
existing = {}
if os.path.exists(mpath):
    try:
        with open(mpath) as f:
            existing = json.load(f)
    except Exception:
        existing = {}
wal_dirs = list(existing.get("wal_dirs") or [])
def _rel(p):
    if p.startswith(root + os.sep) or p == root:
        return os.path.relpath(p, root)
    return p
new_wal = _rel(archive_dir)
if new_wal not in wal_dirs:
    wal_dirs.append(new_wal)
payload = {
    "schema_version": 1,
    "basebackup_path": _rel(dest),
    "basebackup_instance_id": instance,
    "as_of_lsn": start_lsn or existing.get("as_of_lsn", ""),
    "wal_dirs": wal_dirs,
    "created_at": __import__("datetime").datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "pg_version": existing.get("pg_version") or None,
}
tmp = mpath + ".tmp"
with open(tmp, "w") as f:
    json.dump(payload, f, indent=2)
    f.flush()
    os.fsync(f.fileno())
os.replace(tmp, mpath)
print(f"updated pitr_manifest.json -> {_rel(dest)}", file=sys.stderr)
PY

# Run GC
gc_script="$MA3_REPO_DIR/deploy/ltp/pg_pitr_gc.sh"
if [[ -x "$gc_script" ]]; then
  bash "$gc_script" || log "GC returned non-zero (non-fatal)"
else
  log "GC script not found at $gc_script; skipping"
fi

log "basebackup complete: $dest"
