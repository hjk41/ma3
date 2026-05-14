#!/usr/bin/env bash
# Restore ma3 PostgreSQL from a backup manifest produced by backup_postgres.sh.
#
# Required env:
#   MA3_BACKUP_MANIFEST  Path to manifest, or "latest" to use $MA3_BACKUP_DIR/latest.manifest.json
#   MA3_BACKUP_DIR       Required when MA3_BACKUP_MANIFEST=latest
#   PGDATABASE
#   PGUSER
#   PGPASSWORD
#
# Optional env:
#   PGHOST               default: localhost
#   PGPORT               default: 5432
#   MA3_DROP_EXISTING_DB default: 1

set -euo pipefail
umask 077

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGDATABASE="${PGDATABASE:?PGDATABASE is required}"
PGUSER="${PGUSER:?PGUSER is required}"
PGPASSWORD="${PGPASSWORD:?PGPASSWORD is required}"
DROP_EXISTING="${MA3_DROP_EXISTING_DB:-1}"

MANIFEST="${MA3_BACKUP_MANIFEST:-latest}"
if [[ "$MANIFEST" == "latest" ]]; then
  BACKUP_DIR="${MA3_BACKUP_DIR:?MA3_BACKUP_DIR is required when MA3_BACKUP_MANIFEST=latest}"
  MANIFEST="${BACKUP_DIR}/latest.manifest.json"
fi

if [[ ! -f "$MANIFEST" ]]; then
  echo "ERROR: backup manifest not found: $MANIFEST" >&2
  exit 1
fi

DUMP_PATH="$(python3 - "$MANIFEST" <<'PY'
import json, pathlib, sys
manifest = pathlib.Path(sys.argv[1])
m = json.loads(manifest.read_text(encoding='utf-8'))
base = manifest.parent
candidates = []
if m.get('dump_path'):
    raw = pathlib.Path(m['dump_path'])
    candidates.append(raw)
    candidates.append(base / raw.name)
if m.get('dump_file'):
    candidates.append(base / m['dump_file'])
for candidate in candidates:
    if candidate.is_file():
        print(candidate)
        break
else:
    print(candidates[0] if candidates else base / 'missing.sql.gz')
PY
)"

if [[ ! -f "$DUMP_PATH" ]]; then
  echo "ERROR: dump file not found: $DUMP_PATH" >&2
  exit 1
fi

EXPECTED_SHA="$(python3 - "$MANIFEST" <<'PY'
import json, pathlib, sys
print(json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8')).get('sha256') or '')
PY
)"
if [[ -n "$EXPECTED_SHA" ]]; then
  ACTUAL_SHA="$(sha256sum "$DUMP_PATH" | awk '{print $1}')"
  if [[ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]]; then
    echo "ERROR: checksum mismatch for $DUMP_PATH" >&2
    echo "expected: $EXPECTED_SHA" >&2
    echo "actual:   $ACTUAL_SHA" >&2
    exit 1
  fi
fi

export PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD

if [[ "$DROP_EXISTING" == "1" ]]; then
  echo "[restore] dropping and recreating public schema in ${PGDATABASE}"
  psql -v ON_ERROR_STOP=1 -d "$PGDATABASE" <<'SQL'
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
SQL
fi

echo "[restore] restoring ${DUMP_PATH}"
gzip -dc "$DUMP_PATH" | psql -v ON_ERROR_STOP=1 -d "$PGDATABASE"
echo "[restore] done"

