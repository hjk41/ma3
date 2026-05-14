#!/usr/bin/env bash
# Create a ma3 PostgreSQL backup plus a manifest that can be consumed by
# deploy/ltp/bootstrap_ma3_ltp.sh.
#
# Required env:
#   MA3_BACKUP_DIR       Directory on CephFS/3FS, e.g. /mnt/3fs/data/ma3/backups
#   PGDATABASE           Database name, e.g. ma3db
#   PGUSER               Database user, e.g. ma3user
#   PGPASSWORD           Database password
#
# Optional env:
#   PGHOST               default: localhost
#   PGPORT               default: 5432
#   MA3_RETAIN_BACKUPS   default: 30
#   MA3_GIT_COMMIT       included in manifest when set
#   MA3_PUBLIC_BASE_URL  included in manifest when set

set -euo pipefail
umask 077

BACKUP_DIR="${MA3_BACKUP_DIR:?MA3_BACKUP_DIR is required}"
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGDATABASE="${PGDATABASE:?PGDATABASE is required}"
PGUSER="${PGUSER:?PGUSER is required}"
PGPASSWORD="${PGPASSWORD:?PGPASSWORD is required}"
RETAIN="${MA3_RETAIN_BACKUPS:-30}"

mkdir -p "$BACKUP_DIR"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
BASE="ma3db_${TS}"
DUMP_PATH="${BACKUP_DIR}/${BASE}.sql.gz"
MANIFEST_PATH="${BACKUP_DIR}/${BASE}.manifest.json"
LATEST_MANIFEST="${BACKUP_DIR}/latest.manifest.json"

echo "[backup] writing ${DUMP_PATH}"
export PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD
pg_dump --no-owner --no-privileges --format=plain "$PGDATABASE" | gzip -9 > "$DUMP_PATH"

SHA256="$(sha256sum "$DUMP_PATH" | awk '{print $1}')"
BYTES="$(stat -c '%s' "$DUMP_PATH")"

python3 - "$MANIFEST_PATH" "$DUMP_PATH" "$SHA256" "$BYTES" <<'PY'
import json
import os
import pathlib
import subprocess
import sys

manifest_path = pathlib.Path(sys.argv[1])
dump_path = pathlib.Path(sys.argv[2])
sha256 = sys.argv[3]
bytes_ = int(sys.argv[4])

def psql_scalar(sql: str) -> str | None:
    try:
        out = subprocess.check_output(
            ["psql", "-Atqc", sql],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return out or None
    except Exception:
        return None

record_count = psql_scalar("SELECT COUNT(*) FROM records") or "0"
latest_record_updated_at = psql_scalar(
    "SELECT MAX(COALESCE(payload_json->>'updated_at', payload_json->>'created_at')) FROM records"
)
wal_lsn = psql_scalar("SELECT pg_current_wal_lsn()")
schema_tables = psql_scalar("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'") or "0"

manifest = {
    "format": "ma3-postgres-backup-v1",
    "created_at": os.environ.get("TS_OVERRIDE") or psql_scalar("SELECT now() AT TIME ZONE 'UTC'") or "",
    "dump_path": str(dump_path),
    "dump_file": dump_path.name,
    "sha256": sha256,
    "bytes": bytes_,
    "database": os.environ.get("PGDATABASE"),
    "pg_host": os.environ.get("PGHOST"),
    "pg_port": os.environ.get("PGPORT"),
    "git_commit": os.environ.get("MA3_GIT_COMMIT"),
    "public_base_url": os.environ.get("MA3_PUBLIC_BASE_URL"),
    "record_count": int(record_count),
    "latest_record_updated_at": latest_record_updated_at,
    "wal_lsn": wal_lsn,
    "schema_tables": int(schema_tables),
    "delta_cursor": {
        "latest_record_updated_at": latest_record_updated_at,
        "wal_lsn": wal_lsn,
    },
}
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
PY

ln -sfn "$(basename "$MANIFEST_PATH")" "$LATEST_MANIFEST"

echo "[backup] manifest ${MANIFEST_PATH}"
echo "[backup] latest -> ${LATEST_MANIFEST}"

if [[ "$RETAIN" =~ ^[0-9]+$ ]] && [[ "$RETAIN" -gt 0 ]]; then
  ls -1t "${BACKUP_DIR}"/ma3db_*.sql.gz 2>/dev/null | tail -n +"$((RETAIN + 1))" | while read -r old_dump; do
    old_base="${old_dump%.sql.gz}"
    rm -f "$old_dump" "${old_base}.manifest.json"
  done
fi

