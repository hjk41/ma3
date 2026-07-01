#!/usr/bin/env bash
# Bootstrap PostgreSQL for ma3 on a single local host (e.g. 192.168.31.202).
set -euo pipefail

PGUSER="${PGUSER:-ma3user}"
PGDATABASE="${PGDATABASE:-ma3db}"
PGPORT="${PGPORT:-5432}"
PGHOST="${PGHOST:-127.0.0.1}"
PGPASSWORD="${PGPASSWORD:-${MA3_PG_PASSWORD:-ma3local}}"

if ! command -v psql >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends postgresql postgresql-client
fi

if ! sudo systemctl is-active --quiet postgresql; then
  sudo systemctl enable --now postgresql
fi

sudo -u postgres psql -v ON_ERROR_STOP=1 -p "$PGPORT" <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${PGUSER}') THEN
    CREATE ROLE ${PGUSER} LOGIN PASSWORD '${PGPASSWORD}';
  ELSE
    ALTER ROLE ${PGUSER} WITH LOGIN PASSWORD '${PGPASSWORD}';
  END IF;
END
\$\$;
SQL

if ! sudo -u postgres psql -p "$PGPORT" -Atc "SELECT 1 FROM pg_database WHERE datname='${PGDATABASE}'" | grep -q 1; then
  sudo -u postgres createdb -p "$PGPORT" -O "$PGUSER" "$PGDATABASE"
fi

sudo -u postgres psql -p "$PGPORT" -d "$PGDATABASE" -v ON_ERROR_STOP=1 <<SQL
GRANT ALL PRIVILEGES ON DATABASE ${PGDATABASE} TO ${PGUSER};
GRANT ALL ON SCHEMA public TO ${PGUSER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO ${PGUSER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO ${PGUSER};
SQL

ENC_PASS=$(python3 - <<PY
import urllib.parse
print(urllib.parse.quote("${PGPASSWORD}", safe=""))
PY
)
echo "postgresql://${PGUSER}:${ENC_PASS}@${PGHOST}:${PGPORT}/${PGDATABASE}"
