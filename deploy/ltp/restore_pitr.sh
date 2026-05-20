#!/usr/bin/env bash
# restore_pitr.sh — Postgres point-in-time recovery from CephFS.
#
# Replaces the pg_dump-restore path when MA3_BACKUP_MANIFEST=latest_pitr.
# Reads $MA3_BACKUP_DIR/pitr_manifest.json, untars the basebackup into
# the freshly-initialized PGDATA, configures restore_command to walk
# every wal_dir listed in the manifest, then starts Postgres and waits
# until recovery is complete.
#
# Failure modes:
#   - pitr_manifest.json missing  -> exit 70 with a clear message; the
#     caller (bootstrap) is expected to fall back to legacy pg_dump
#     restore.
#   - basebackup_path missing on disk -> exit 71.
#   - Postgres recovery fails -> exit 72.
#
# Env consumed:
#   MA3_BACKUP_DIR                 required
#   MA3_INSTANCE_ID                required
#   PGDATA, PGUSER, PGHOST, PGPORT
#   MA3_REPO_DIR                   for pg_restore_walk.sh path

set -euo pipefail
IFS=$'\n\t'

log() { printf '[%s] restore_pitr: %s\n' "$(date -u +%FT%TZ)" "$*" >&2; }

: "${MA3_BACKUP_DIR:?MA3_BACKUP_DIR required}"
: "${MA3_INSTANCE_ID:?MA3_INSTANCE_ID required}"
: "${PGDATA:?PGDATA required}"
: "${PGUSER:?PGUSER required}"
: "${PGHOST:=127.0.0.1}"
: "${PGPORT:=5433}"
: "${MA3_REPO_DIR:=/root/ma3-instance/repo}"

manifest="$MA3_BACKUP_DIR/pitr_manifest.json"
if [[ ! -f "$manifest" ]]; then
  log "no pitr_manifest.json at $manifest — caller should fall back to legacy restore"
  exit 70
fi

# Parse manifest with python for robustness
read -r BB_PATH WAL_DIRS_COLON < <(python3 - "$manifest" "$MA3_BACKUP_DIR" <<'PY'
import json, os, sys
mpath, root = sys.argv[1], sys.argv[2]
with open(mpath) as f:
    d = json.load(f)
bb = d.get("basebackup_path") or ""
if bb and not os.path.isabs(bb):
    bb = os.path.join(root, bb)
wals = []
for w in d.get("wal_dirs") or []:
    p = w if os.path.isabs(w) else os.path.join(root, w)
    wals.append(p)
print(bb, ":".join(wals))
PY
)

if [[ -z "$BB_PATH" || ! -d "$BB_PATH" ]]; then
  log "basebackup_path '$BB_PATH' missing on disk"
  exit 71
fi
if [[ ! -f "$BB_PATH/base.tar.gz" ]]; then
  log "basebackup tarball missing: $BB_PATH/base.tar.gz"
  exit 71
fi
log "restoring from basebackup $BB_PATH; wal_dirs=$WAL_DIRS_COLON"

# Stop PG if running locally
if command -v pg_ctlcluster >/dev/null 2>&1; then
  pg_ctlcluster 16 main stop 2>/dev/null || pg_ctlcluster 15 main stop 2>/dev/null || true
fi

# Wipe PGDATA
if [[ -d "$PGDATA" ]]; then
  rm -rf -- "${PGDATA:?}"/*
  rm -rf -- "${PGDATA:?}"/.??*
fi
mkdir -p "$PGDATA"
chown -R postgres:postgres "$PGDATA" 2>/dev/null || true
chmod 700 "$PGDATA"

# Untar
log "untar base.tar.gz -> $PGDATA"
tar -xzf "$BB_PATH/base.tar.gz" -C "$PGDATA"
mkdir -p "$PGDATA/pg_wal"
log "untar pg_wal.tar.gz -> $PGDATA/pg_wal"
tar -xzf "$BB_PATH/pg_wal.tar.gz" -C "$PGDATA/pg_wal"

chown -R postgres:postgres "$PGDATA" 2>/dev/null || true

# Recovery signal + restore_command
touch "$PGDATA/recovery.signal"
chown postgres:postgres "$PGDATA/recovery.signal" 2>/dev/null || true

restore_walk="${MA3_REPO_DIR}/deploy/ltp/pg_restore_walk.sh"
if [[ ! -x /opt/ma3/pg_restore_walk.sh ]]; then
  install -m 0755 -o postgres -g postgres "$restore_walk" /opt/ma3/pg_restore_walk.sh 2>/dev/null \
    || install -m 0755 "$restore_walk" /opt/ma3/pg_restore_walk.sh
fi

cat >> "$PGDATA/postgresql.auto.conf" <<EOF
# ma3 PITR restore
restore_command = 'MA3_PG_WAL_DIRS=$WAL_DIRS_COLON /opt/ma3/pg_restore_walk.sh %f %p'
recovery_target_timeline = 'latest'
EOF
chown postgres:postgres "$PGDATA/postgresql.auto.conf" 2>/dev/null || true

# Start PG and wait for recovery
log "starting Postgres for recovery"
if command -v pg_ctlcluster >/dev/null 2>&1; then
  pg_ctlcluster 16 main start 2>/dev/null || pg_ctlcluster 15 main start
fi

deadline=$(( $(date -u +%s) + 600 ))
while true; do
  if [[ ! -f "$PGDATA/recovery.signal" ]] && \
     pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" >/dev/null 2>&1; then
    break
  fi
  if (( $(date -u +%s) > deadline )); then
    log "recovery timed out after 10 minutes"
    exit 72
  fi
  sleep 2
done

log "recovery complete; instance=$MA3_INSTANCE_ID restored from ${BB_PATH##*/}"
exit 0
