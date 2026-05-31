#!/usr/bin/env bash
# Bootstrap a prod-like ma3 instance inside one LTP/OpenPAI container.
#
# This script is intentionally self-contained so an LTP job can pull code and
# start a full ma3 instance without manual file upload after the container starts.

set -euo pipefail
umask 077

log() { printf '[ma3-ltp] %s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

doctor_matches_instance() {
  curl -fsS "http://127.0.0.1:${MA3_PORT}/v2/doctor" >/tmp/ma3-doctor.json 2>/dev/null || return 1
  MA3_EXPECTED_INSTANCE_ID="$MA3_INSTANCE_ID" \
  MA3_EXPECTED_GIT_COMMIT="${MA3_GIT_COMMIT:-}" \
  python3 - <<'PY'
import json
import os
import sys

doctor = json.load(open("/tmp/ma3-doctor.json", "r", encoding="utf-8"))
expected_instance_id = os.environ["MA3_EXPECTED_INSTANCE_ID"]
expected_git_commit = os.environ.get("MA3_EXPECTED_GIT_COMMIT") or ""

if doctor.get("status") != "ok":
    sys.exit(1)
if doctor.get("instance_id") != expected_instance_id:
    sys.exit(1)
if expected_git_commit and doctor.get("git_commit") != expected_git_commit:
    sys.exit(1)
PY
}

: "${MA3_GIT_REPO:?MA3_GIT_REPO is required}"
: "${MA3_GIT_REF:?MA3_GIT_REF is required}"
: "${MA3_ADMIN_KEY:?MA3_ADMIN_KEY is required}"
: "${MA3_BACKUP_DIR:?MA3_BACKUP_DIR is required}"

MA3_INSTANCE_ID="${MA3_INSTANCE_ID:-ma3-${PAI_JOB_NAME:-ltp}-$(date -u +%Y%m%dT%H%M%SZ)}"
MA3_WORKDIR="${MA3_WORKDIR:-/root/ma3-instance}"
MA3_REPO_DIR="${MA3_REPO_DIR:-${MA3_WORKDIR}/repo}"
MA3_VENV="${MA3_VENV:-${MA3_WORKDIR}/.venv}"
MA3_PORT="${MA3_PORT:-8000}"
MA3_PUBLIC_BASE_URL="${MA3_PUBLIC_BASE_URL:-http://127.0.0.1:${MA3_PORT}}"
MA3_BACKUP_MANIFEST="${MA3_BACKUP_MANIFEST:-latest}"
MA3_ENABLE_DELTA="${MA3_ENABLE_DELTA:-0}"
MA3_DELTA_URL="${MA3_DELTA_URL:-}"
MA3_RUN_V1_TO_V2_MIGRATION="${MA3_RUN_V1_TO_V2_MIGRATION:-1}"
MA3_RUN_V2_TO_V3_MIGRATION="${MA3_RUN_V2_TO_V3_MIGRATION:-1}"
MA3_MANIFEST_DIR="${MA3_MANIFEST_DIR:-${MA3_BACKUP_DIR}/instances}"

# v3 PITR realtime backup
MA3_PG_ARCHIVE_ENABLE="${MA3_PG_ARCHIVE_ENABLE:-1}"
MA3_PG_ARCHIVE_DIR="${MA3_PG_ARCHIVE_DIR:-${MA3_BACKUP_DIR}/wal/${MA3_INSTANCE_ID}}"
MA3_PG_ARCHIVE_TIMEOUT_SECONDS="${MA3_PG_ARCHIVE_TIMEOUT_SECONDS:-60}"
MA3_PG_BASEBACKUP_INTERVAL_MIN="${MA3_PG_BASEBACKUP_INTERVAL_MIN:-30}"
MA3_PG_BASEBACKUP_RETENTION="${MA3_PG_BASEBACKUP_RETENTION:-4}"
MA3_PG_OLD_INSTANCE_RETENTION_DAYS="${MA3_PG_OLD_INSTANCE_RETENTION_DAYS:-7}"
MA3_OP_LOG_REALTIME_CEPHFS="${MA3_OP_LOG_REALTIME_CEPHFS:-1}"
if [[ "$MA3_OP_LOG_REALTIME_CEPHFS" == "1" && -n "${MA3_BACKUP_DIR:-}" ]]; then
  MA3_OP_LOG_DIR="${MA3_OP_LOG_DIR:-${MA3_BACKUP_DIR}/op_logs/${MA3_INSTANCE_ID}}"
else
  MA3_OP_LOG_DIR="${MA3_OP_LOG_DIR:-/var/log/ma3/ops}"
fi
MA3_LOG_ARCHIVE_DIR="${MA3_LOG_ARCHIVE_DIR:-${MA3_BACKUP_DIR}/logs}"
MA3_LOG_LOCAL_RETENTION_DAYS="${MA3_LOG_LOCAL_RETENTION_DAYS:-2}"
MA3_V1_TO_V2_REPORT="${MA3_V1_TO_V2_REPORT:-${MA3_WORKDIR}/v1_to_v2_migration_report.json}"
MA3_REQUIREMENTS_FILE="${MA3_REQUIREMENTS_FILE:-server/requirements-ltp.txt}"
MA3_DISABLE_EMBEDDINGS="${MA3_DISABLE_EMBEDDINGS:-1}"
MA3_DB_POOL_ENABLED="${MA3_DB_POOL_ENABLED:-1}"
MA3_DB_POOL_MIN_SIZE="${MA3_DB_POOL_MIN_SIZE:-1}"
MA3_DB_POOL_MAX_SIZE="${MA3_DB_POOL_MAX_SIZE:-8}"
MA3_DB_POOL_TIMEOUT_SECONDS="${MA3_DB_POOL_TIMEOUT_SECONDS:-5}"
MA3_SEARCH_BATCH_GRAPH_ENABLED="${MA3_SEARCH_BATCH_GRAPH_ENABLED:-1}"
MA3_SEARCH_INDEX_MODE="${MA3_SEARCH_INDEX_MODE:-jsonb_runtime}"
MA3_CEPHFS_ENABLE="${MA3_CEPHFS_ENABLE:-0}"
MA3_CEPHFS_USER="${MA3_CEPHFS_USER:-}"
MA3_CEPHFS_KEYRING="${MA3_CEPHFS_KEYRING:-}"
MA3_CEPHFS_MOUNT="${MA3_CEPHFS_MOUNT:-/mnt/cephfs}"
MA3_CEPHFS_FS_NAME="${MA3_CEPHFS_FS_NAME:-mycephfs}"
MA3_CEPHFS_MON="${MA3_CEPHFS_MON:-10.100.65.50,10.100.65.51,10.100.160.70}"

PGHOST="${PGHOST:-localhost}"
PGPORT_EXPLICIT="${PGPORT+x}"
PGPORT="${PGPORT:-5432}"
PGDATABASE="${PGDATABASE:-ma3db}"
PGUSER="${PGUSER:-ma3user}"
PGPASSWORD="${PGPASSWORD:?PGPASSWORD is required}"

export MA3_INSTANCE_ID MA3_PUBLIC_BASE_URL PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD
export MA3_OP_LOG_DIR MA3_LOG_ARCHIVE_DIR MA3_LOG_LOCAL_RETENTION_DAYS
export MA3_DB_POOL_ENABLED MA3_DB_POOL_MIN_SIZE MA3_DB_POOL_MAX_SIZE MA3_DB_POOL_TIMEOUT_SECONDS
export MA3_SEARCH_BATCH_GRAPH_ENABLED MA3_SEARCH_INDEX_MODE

make_postgres_url() {
  python3 - <<'PY'
import os
from urllib.parse import quote

user = os.environ["PGUSER"]
password = os.environ["PGPASSWORD"]
host = os.environ["PGHOST"]
port = os.environ["PGPORT"]
database = os.environ["PGDATABASE"]
print(
    "postgresql://"
    f"{quote(user, safe='')}:{quote(password, safe='')}"
    f"@{host}:{port}/{quote(database, safe='')}"
)
PY
}

mount_cephfs_if_enabled() {
  if [[ "$MA3_CEPHFS_ENABLE" != "1" ]]; then
    return 0
  fi
  [[ -n "$MA3_CEPHFS_USER" ]] || die "MA3_CEPHFS_ENABLE=1 but MA3_CEPHFS_USER is empty"
  [[ -n "$MA3_CEPHFS_KEYRING" ]] || die "MA3_CEPHFS_ENABLE=1 but MA3_CEPHFS_KEYRING is empty"

  log "mounting CephFS at ${MA3_CEPHFS_MOUNT} as ${MA3_CEPHFS_USER}"
  if ! command -v ceph-fuse >/dev/null 2>&1; then
    if ! command -v apt-get >/dev/null 2>&1; then
      die "ceph-fuse missing and apt-get is unavailable"
    fi
    export DEBIAN_FRONTEND=noninteractive
    if command -v curl >/dev/null 2>&1; then
      curl -fsSL http://10.100.197.13/user_config/bootstrap.sh | bash -s -- --ceph || true
    fi
    apt-get update
    apt-get install -y --no-install-recommends ceph-common ceph-fuse
  fi

  mkdir -p /etc/ceph "$MA3_CEPHFS_MOUNT"
  local keyring_path="/etc/ceph/${MA3_CEPHFS_USER}.keyring"
  printf '%s\n' "$MA3_CEPHFS_KEYRING" > "$keyring_path"
  chmod 600 "$keyring_path"
  local keyring_user
  keyring_user="$(awk '/^\[client\.[^]]+\]$/ {gsub(/^\[client\./, ""); gsub(/\]$/, ""); print; exit}' "$keyring_path")"
  [[ -n "$keyring_user" ]] || die "CephFS keyring is missing a [client.<user>] header"
  [[ "$keyring_user" == "$MA3_CEPHFS_USER" ]] || die "CephFS keyring identity client.${keyring_user} does not match MA3_CEPHFS_USER=${MA3_CEPHFS_USER}"
  awk '/^[[:space:]]*key[[:space:]]*=/ {found=1} END {exit found ? 0 : 1}' "$keyring_path" \
    || die "CephFS keyring for ${MA3_CEPHFS_USER} is missing a key entry"
  cat > /etc/ceph/ceph.conf <<EOF
[global]
mon_host = ${MA3_CEPHFS_MON}
EOF

  if mountpoint -q "$MA3_CEPHFS_MOUNT"; then
    log "CephFS mountpoint already mounted: ${MA3_CEPHFS_MOUNT}"
  else
    ceph-fuse "$MA3_CEPHFS_MOUNT" \
      --client_fs="$MA3_CEPHFS_FS_NAME" \
      --id "$MA3_CEPHFS_USER" \
      --keyring "$keyring_path" \
      --client_reconnect_stale=1
  fi

  if ! timeout 30 bash -c 'until mountpoint -q "$1"; do sleep 1; done' _ "$MA3_CEPHFS_MOUNT"; then
    findmnt "$MA3_CEPHFS_MOUNT" -o TARGET,FSTYPE,OPTIONS -n >&2 || true
    die "CephFS mountpoint did not become mounted: ${MA3_CEPHFS_MOUNT}"
  fi
  log "CephFS mounted; backup dir check: ${MA3_BACKUP_DIR}"
  if [[ ! -d "$MA3_BACKUP_DIR" ]]; then
    die "MA3_BACKUP_DIR does not exist after CephFS mount: ${MA3_BACKUP_DIR}"
  fi
  ls -ld "$MA3_BACKUP_DIR" >&2 || true
}

log "instance_id=${MA3_INSTANCE_ID}"
log "workdir=${MA3_WORKDIR}"
mkdir -p "$MA3_WORKDIR" /var/log/ma3

if ! command -v pg_isready >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1 || ! python3 -m venv --help >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    log "installing missing runtime packages with apt-get"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends git curl ca-certificates sudo python3 python3-venv python3-pip postgresql postgresql-client cron nodejs npm
  else
    die "missing runtime packages and apt-get is unavailable; use an image with git/curl/python3-venv/PostgreSQL"
  fi
fi

mount_cephfs_if_enabled
mkdir -p "$MA3_MANIFEST_DIR"

if command -v pg_ctlcluster >/dev/null 2>&1; then
  log "starting local PostgreSQL cluster"
  pg_ctlcluster 16 main start 2>/dev/null || pg_ctlcluster 15 main start 2>/dev/null || true
fi

if [[ -z "$PGPORT_EXPLICIT" ]] && command -v pg_lsclusters >/dev/null 2>&1; then
  DETECTED_PGPORT=""
  for _ in $(seq 1 30); do
    DETECTED_PGPORT="$(pg_lsclusters --no-header 2>/dev/null | awk '$4 == "online" {print $3; exit}')"
    if [[ -n "$DETECTED_PGPORT" ]]; then
      break
    fi
    sleep 1
  done
  if [[ -n "$DETECTED_PGPORT" ]]; then
    log "detected PostgreSQL cluster port=${DETECTED_PGPORT}"
    PGPORT="$DETECTED_PGPORT"
    export PGPORT
  else
    die "could not detect an online job-local PostgreSQL cluster port with pg_lsclusters"
  fi
fi

if ! pg_isready -h "$PGHOST" -p "$PGPORT" >/dev/null 2>&1; then
  die "PostgreSQL is not ready at ${PGHOST}:${PGPORT}; use an image with PostgreSQL or pre-start it"
fi

log "ensuring database/user exist"
[[ "$PGUSER" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || die "PGUSER must be a simple PostgreSQL identifier"
[[ "$PGDATABASE" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || die "PGDATABASE must be a simple PostgreSQL identifier"
if command -v runuser >/dev/null 2>&1 && id postgres >/dev/null 2>&1; then
  postgres_psql() {
    runuser -u postgres -- env -u PGUSER -u PGHOST -u PGPASSWORD -u PGDATABASE \
      psql -h /var/run/postgresql -U postgres -p "$PGPORT" "$@"
  }
  postgres_createdb() {
    runuser -u postgres -- env -u PGUSER -u PGHOST -u PGPASSWORD -u PGDATABASE \
      createdb -h /var/run/postgresql -U postgres -p "$PGPORT" "$@"
  }
  if ! postgres_psql -Atc "SELECT 1 FROM pg_roles WHERE rolname='${PGUSER}'" | grep -q 1; then
    postgres_psql -v ON_ERROR_STOP=1 -c "CREATE USER ${PGUSER};"
  fi
  postgres_psql -v ON_ERROR_STOP=1 --set=ma3_password="$PGPASSWORD" <<SQL
ALTER USER ${PGUSER} WITH PASSWORD :'ma3_password';
SQL
  if ! postgres_psql -Atc "SELECT 1 FROM pg_database WHERE datname='${PGDATABASE}'" | grep -q 1; then
    postgres_createdb -O "$PGUSER" "$PGDATABASE"
  fi
  postgres_psql -v ON_ERROR_STOP=1 -d "$PGDATABASE" <<SQL
ALTER DATABASE ${PGDATABASE} OWNER TO ${PGUSER};
GRANT ALL ON SCHEMA public TO ${PGUSER};
SQL
else
  die "runuser/postgres unavailable; cannot initialize PostgreSQL role/database safely"
fi

log "cloning code"
rm -rf "$MA3_REPO_DIR"
if [[ -n "${MA3_GIT_SSH_KEY:-}" ]]; then
  mkdir -p /root/.ssh
  printf '%s\n' "$MA3_GIT_SSH_KEY" > /root/.ssh/id_ma3_codeup
  chmod 600 /root/.ssh/id_ma3_codeup
  export GIT_SSH_COMMAND="ssh -i /root/.ssh/id_ma3_codeup -o StrictHostKeyChecking=no"
fi
if [[ -n "${MA3_GIT_TOKEN:-}" && "$MA3_GIT_REPO" =~ ^https:// ]]; then
  AUTH_REPO="${MA3_GIT_REPO/https:\/\//https:\/\/${MA3_GIT_TOKEN}@}"
else
  AUTH_REPO="$MA3_GIT_REPO"
fi
git clone --depth 1 --branch "$MA3_GIT_REF" "$AUTH_REPO" "$MA3_REPO_DIR"
cd "$MA3_REPO_DIR"
if [[ -n "${MA3_GIT_COMMIT:-}" ]]; then
  git fetch --depth 1 origin "$MA3_GIT_COMMIT" || true
  git checkout "$MA3_GIT_COMMIT"
fi
RESOLVED_COMMIT="$(git rev-parse HEAD)"
export MA3_GIT_COMMIT="$RESOLVED_COMMIT"
log "code commit=${RESOLVED_COMMIT}"

log "creating virtualenv"
python3 -m venv "$MA3_VENV"
"$MA3_VENV/bin/pip" install --upgrade pip
"$MA3_VENV/bin/pip" install -r "$MA3_REPO_DIR/$MA3_REQUIREMENTS_FILE"

log "restoring database backup"
if [[ "$MA3_BACKUP_MANIFEST" == "latest_pitr" ]]; then
  if [[ -f "${MA3_BACKUP_DIR}/pitr_manifest.json" ]]; then
    log "PITR restore via pitr_manifest.json"
    # SHOW data_directory needs superuser; ma3user can't run it. Try
    # sudo -u postgres first, then fall back to pg_lsclusters, then to
    # the standard Debian/Ubuntu path.
    DETECTED_PGDATA="$(sudo -u postgres psql -tAc 'SHOW data_directory;' 2>/dev/null || true)"
    if [[ -z "$DETECTED_PGDATA" ]] && command -v pg_lsclusters >/dev/null 2>&1; then
      DETECTED_PGDATA="$(pg_lsclusters -h 2>/dev/null | awk '$4=="online"{print $6;exit}' || true)"
    fi
    DETECTED_PGDATA="${DETECTED_PGDATA:-/var/lib/postgresql/16/main}"
    log "PGDATA resolved to ${DETECTED_PGDATA}"
    MA3_BACKUP_DIR="$MA3_BACKUP_DIR" \
    MA3_INSTANCE_ID="$MA3_INSTANCE_ID" \
    PGDATA="$DETECTED_PGDATA" \
    PGHOST="$PGHOST" PGPORT="$PGPORT" PGUSER="$PGUSER" PGPASSWORD="$PGPASSWORD" \
      bash "$MA3_REPO_DIR/deploy/ltp/restore_pitr.sh" || {
        rc=$?
        log "PITR restore exited rc=$rc; falling back to legacy pg_dump restore"
        MA3_BACKUP_MANIFEST=latest \
        MA3_BACKUP_DIR="$MA3_BACKUP_DIR" \
        PGHOST="$PGHOST" PGPORT="$PGPORT" PGDATABASE="$PGDATABASE" PGUSER="$PGUSER" PGPASSWORD="$PGPASSWORD" \
          bash "$MA3_REPO_DIR/deploy/ltp/restore_postgres.sh"
      }
  else
    log "MA3_BACKUP_MANIFEST=latest_pitr but no pitr_manifest.json yet — falling back to legacy restore"
    MA3_BACKUP_MANIFEST=latest \
    MA3_BACKUP_DIR="$MA3_BACKUP_DIR" \
    PGHOST="$PGHOST" PGPORT="$PGPORT" PGDATABASE="$PGDATABASE" PGUSER="$PGUSER" PGPASSWORD="$PGPASSWORD" \
      bash "$MA3_REPO_DIR/deploy/ltp/restore_postgres.sh"
  fi
else
  MA3_BACKUP_MANIFEST="$MA3_BACKUP_MANIFEST" \
  MA3_BACKUP_DIR="$MA3_BACKUP_DIR" \
  PGHOST="$PGHOST" PGPORT="$PGPORT" PGDATABASE="$PGDATABASE" PGUSER="$PGUSER" PGPASSWORD="$PGPASSWORD" \
    bash "$MA3_REPO_DIR/deploy/ltp/restore_postgres.sh"
fi

# Configure WAL archiving (idempotent — only restarts PG on first enable)
if [[ "$MA3_PG_ARCHIVE_ENABLE" == "1" ]]; then
  log "configuring Postgres WAL archiving"
  mkdir -p /opt/ma3
  install -m 0755 "$MA3_REPO_DIR/deploy/ltp/pg_archive.sh"      /opt/ma3/pg_archive.sh
  install -m 0755 "$MA3_REPO_DIR/deploy/ltp/pg_restore_walk.sh" /opt/ma3/pg_restore_walk.sh
  mkdir -p "$MA3_PG_ARCHIVE_DIR" "${MA3_BACKUP_DIR}/basebackups/${MA3_INSTANCE_ID}" "${MA3_BACKUP_DIR}/op_logs/${MA3_INSTANCE_ID}"
  mkdir -p /var/log/ma3 /tmp/ma3-archive
  chmod 0777 /var/log/ma3 /tmp/ma3-archive 2>/dev/null || true
  # CephFS rejects chmod/chown across the FUSE boundary; only Linux uid=0
  # gets cephfs caps. Workarounds:
  #   (a) postgres-side archive_command runs via sudo so the WAL copy is
  #       performed as root (which CAN write CephFS).
  #   (b) pg_basebackup runs as root locally, connecting over TCP with
  #       ma3user (granted REPLICATION) for the protocol auth.
  log "installing sudoers entry for postgres -> /opt/ma3/pg_archive_wrapper.sh"
  mkdir -p /etc/sudoers.d
  cat > /etc/sudoers.d/ma3-pg-archive <<SUDO
Defaults env_keep += "MA3_PG_ARCHIVE_DIR"
postgres ALL=(root) NOPASSWD: /opt/ma3/pg_archive_wrapper.sh
SUDO
  chmod 0440 /etc/sudoers.d/ma3-pg-archive
  cat > /opt/ma3/pg_archive_wrapper.sh <<EOF
#!/usr/bin/env bash
# Generated by bootstrap_ma3_ltp.sh — bakes MA3_PG_ARCHIVE_DIR for the
# postgres-invoked archive_command to avoid sudo env wrangling.
export MA3_PG_ARCHIVE_DIR='${MA3_PG_ARCHIVE_DIR}'
exec /opt/ma3/pg_archive.sh "\$@"
EOF
  chmod 0755 /opt/ma3/pg_archive_wrapper.sh

  # Grant REPLICATION to ma3user so pg_basebackup can authenticate over
  # TCP. ALTER SYSTEM/ALTER ROLE require superuser → use postgres OS user.
  sudo -u postgres psql -d "$PGDATABASE" <<SQL
ALTER ROLE "$PGUSER" WITH REPLICATION;
ALTER SYSTEM SET archive_mode      = 'on';
ALTER SYSTEM SET archive_command   = 'sudo /opt/ma3/pg_archive_wrapper.sh %p %f';
ALTER SYSTEM SET archive_timeout   = '${MA3_PG_ARCHIVE_TIMEOUT_SECONDS}s';
ALTER SYSTEM SET max_wal_senders   = 3;
ALTER SYSTEM SET wal_keep_size     = '512MB';
SQL
  # Allow ma3user replication connections from localhost. pg_hba.conf is
  # in $PGDATA but we'll go through ALTER SYSTEM-style dynamic include
  # instead — append a single replication line if not already present.
  HBA="$(sudo -u postgres psql -tAc 'SHOW hba_file;')"
  if [[ -n "$HBA" ]] && ! grep -qE "^host\s+replication\s+$PGUSER\s+127\.0\.0\.1/32" "$HBA"; then
    log "adding pg_hba replication line for $PGUSER"
    echo "host    replication    $PGUSER    127.0.0.1/32    md5" | sudo tee -a "$HBA" >/dev/null
  fi
  sudo -u postgres psql -d "$PGDATABASE" -tAc 'SELECT pg_reload_conf();' >/dev/null
  if ! sudo -u postgres psql -d "$PGDATABASE" -tAc 'SHOW archive_mode;' | grep -qi '^on$'; then
    log "archive_mode is off; restarting Postgres once to enable"
    pg_ctlcluster 16 main restart 2>/dev/null || pg_ctlcluster 15 main restart 2>/dev/null || true
    for _ in $(seq 1 30); do
      pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" >/dev/null 2>&1 && break
      sleep 1
    done
  fi
fi

if [[ "$MA3_ENABLE_DELTA" == "1" ]]; then
  if [[ -z "$MA3_DELTA_URL" ]]; then
    die "MA3_ENABLE_DELTA=1 but MA3_DELTA_URL is empty"
  fi
  log "delta sync requested; placeholder fetch from ${MA3_DELTA_URL}"
  # Intentionally conservative: delta import must be schema/version aware.
  # A future implementation should call an authenticated prod export endpoint
  # and apply an idempotent JSONL delta.
  curl -fsS "$MA3_DELTA_URL" -o "${MA3_WORKDIR}/delta.jsonl"
fi

MA3_DATABASE_URL_VALUE="$(make_postgres_url)"
export MA3_DATABASE_URL_VALUE

if [[ "$MA3_RUN_V1_TO_V2_MIGRATION" == "1" ]]; then
  log "running v1-to-v2 case migration"
  cd "$MA3_REPO_DIR/server"
  MA3_DATABASE_URL="$MA3_DATABASE_URL_VALUE" \
    "$MA3_VENV/bin/python3" scripts/migrate_v1_to_v2_cases.py \
      --apply \
      --report "$MA3_V1_TO_V2_REPORT"
else
  log "skipping v1-to-v2 case migration (MA3_RUN_V1_TO_V2_MIGRATION=${MA3_RUN_V1_TO_V2_MIGRATION})"
fi

if [[ "$MA3_RUN_V2_TO_V3_MIGRATION" == "1" ]]; then
  if [[ -f "$MA3_REPO_DIR/server/scripts/migrate_v2_tokens_to_v3.py" ]]; then
    log "running v2-to-v3 token migration (idempotent)"
    cd "$MA3_REPO_DIR/server"
    MA3_DATABASE_URL="$MA3_DATABASE_URL_VALUE" \
      "$MA3_VENV/bin/python3" scripts/migrate_v2_tokens_to_v3.py --apply
  else
    log "skipping v2-to-v3 token migration (script not present in this commit)"
  fi
else
  log "skipping v2-to-v3 token migration (MA3_RUN_V2_TO_V3_MIGRATION=${MA3_RUN_V2_TO_V3_MIGRATION})"
fi

if [[ -f "$MA3_REPO_DIR/server/scripts/migrate_v3_to_v3_1_rbac.py" ]]; then
  log "running v3-to-v3.1 RBAC migration (idempotent)"
  cd "$MA3_REPO_DIR/server"
  MA3_DATABASE_URL="$MA3_DATABASE_URL_VALUE" \
    "$MA3_VENV/bin/python3" scripts/migrate_v3_to_v3_1_rbac.py --apply
fi

if ! command -v node >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    log "installing nodejs/npm for web SPA build"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends nodejs npm
  else
    die "nodejs/npm missing and apt-get is unavailable"
  fi
fi

if [[ -d "$MA3_REPO_DIR/server/app/web" ]]; then
  cd "$MA3_REPO_DIR/server/app/web"
  if [[ ! -f dist/index.html ]] || [[ "$(find src index.html package.json -newer dist/index.html -print -quit 2>/dev/null)" ]]; then
    log "building web SPA"
    npm ci --silent
    npm run build
  else
    log "web SPA dist is fresh; skipping build"
  fi
fi

log "writing root-only env file"
cat > "${MA3_WORKDIR}/ma3.env" <<EOF
MA3_DATABASE_URL=${MA3_DATABASE_URL_VALUE}
MA3_API_KEY=${MA3_ADMIN_KEY}
MA3_PUBLIC_BASE_URL=${MA3_PUBLIC_BASE_URL}
MA3_INSTANCE_ID=${MA3_INSTANCE_ID}
MA3_GIT_COMMIT=${RESOLVED_COMMIT}
MA3_OP_LOG_DIR=${MA3_OP_LOG_DIR}
MA3_LOG_ARCHIVE_DIR=${MA3_LOG_ARCHIVE_DIR}
MA3_LOG_LOCAL_RETENTION_DAYS=${MA3_LOG_LOCAL_RETENTION_DAYS}
MA3_LOG_REDACT_RAW=1
MA3_DISABLE_EMBEDDINGS=${MA3_DISABLE_EMBEDDINGS}
MA3_REQUIREMENTS_FILE=${MA3_REQUIREMENTS_FILE}
MA3_RUN_V1_TO_V2_MIGRATION=${MA3_RUN_V1_TO_V2_MIGRATION}
MA3_RUN_V2_TO_V3_MIGRATION=${MA3_RUN_V2_TO_V3_MIGRATION}
MA3_V1_TO_V2_REPORT=${MA3_V1_TO_V2_REPORT}
MA3_DB_POOL_ENABLED=${MA3_DB_POOL_ENABLED}
MA3_DB_POOL_MIN_SIZE=${MA3_DB_POOL_MIN_SIZE}
MA3_DB_POOL_MAX_SIZE=${MA3_DB_POOL_MAX_SIZE}
MA3_DB_POOL_TIMEOUT_SECONDS=${MA3_DB_POOL_TIMEOUT_SECONDS}
MA3_SEARCH_BATCH_GRAPH_ENABLED=${MA3_SEARCH_BATCH_GRAPH_ENABLED}
MA3_SEARCH_INDEX_MODE=${MA3_SEARCH_INDEX_MODE}
MA3_AUTH_VERIFY_URL=${MA3_AUTH_VERIFY_URL:-}
MA3_AUTH_LOGIN_URL=${MA3_AUTH_LOGIN_URL:-}
MA3_AUTH_ADMIN_USERS=${MA3_AUTH_ADMIN_USERS:-}
MA3_XYZ_LIBRARY_ID=${MA3_XYZ_LIBRARY_ID:-}
MA3_PG_ARCHIVE_ENABLE=${MA3_PG_ARCHIVE_ENABLE}
MA3_PG_ARCHIVE_DIR=${MA3_PG_ARCHIVE_DIR}
MA3_PG_ARCHIVE_TIMEOUT_SECONDS=${MA3_PG_ARCHIVE_TIMEOUT_SECONDS}
MA3_PG_BASEBACKUP_INTERVAL_MIN=${MA3_PG_BASEBACKUP_INTERVAL_MIN}
MA3_PG_BASEBACKUP_RETENTION=${MA3_PG_BASEBACKUP_RETENTION}
MA3_PG_OLD_INSTANCE_RETENTION_DAYS=${MA3_PG_OLD_INSTANCE_RETENTION_DAYS}
MA3_OP_LOG_REALTIME_CEPHFS=${MA3_OP_LOG_REALTIME_CEPHFS}
MA3_BACKUP_DIR=${MA3_BACKUP_DIR}
PGUSER=${PGUSER}
PGHOST=${PGHOST}
PGPORT=${PGPORT}
PGPASSWORD=${PGPASSWORD}
MA3_REPO_DIR=${MA3_REPO_DIR}
HF_HUB_OFFLINE=${HF_HUB_OFFLINE:-1}
EOF
chmod 600 "${MA3_WORKDIR}/ma3.env"

log "starting ma3"
set -a
# shellcheck disable=SC1090
. "${MA3_WORKDIR}/ma3.env"
set +a
cd "$MA3_REPO_DIR/server"
nohup "$MA3_VENV/bin/python3" -m uvicorn app.main:app --host 0.0.0.0 --port "$MA3_PORT" \
  > /var/log/ma3/ma3.log 2>&1 &
MA3_PID="$!"
echo "$MA3_PID" > "${MA3_WORKDIR}/ma3.pid"

log "waiting for healthcheck"
MA3_READY=0
for _ in $(seq 1 60); do
  if ! kill -0 "$MA3_PID" 2>/dev/null; then
    tail -80 /var/log/ma3/ma3.log >&2 || true
    die "ma3 uvicorn process exited before becoming ready"
  fi
  if curl -fsS "http://127.0.0.1:${MA3_PORT}/healthz" >/tmp/ma3-health.json 2>/dev/null && doctor_matches_instance; then
    MA3_READY=1
    break
  fi
  sleep 2
done
if [[ "$MA3_READY" != "1" ]]; then
  tail -80 /var/log/ma3/ma3.log >&2 || true
  die "ma3 did not become ready on port ${MA3_PORT} with matching /v2/doctor identity"
fi
curl -fsS "http://127.0.0.1:${MA3_PORT}/healthz" | python3 -m json.tool
curl -fsS "http://127.0.0.1:${MA3_PORT}/v2/doctor" | python3 -m json.tool

log "installing daily log archive cron entry"
if command -v cron >/dev/null 2>&1; then
  (crontab -l 2>/dev/null | grep -v 'archive_logs.sh' || true; echo "7 3 * * * cd '$MA3_REPO_DIR/server' && set -a && . '$MA3_WORKDIR/ma3.env' && set +a && bash '$MA3_REPO_DIR/deploy/ltp/archive_logs.sh' >> /var/log/ma3/archive.log 2>&1") | crontab -
  cron || true
fi

if [[ "$MA3_PG_ARCHIVE_ENABLE" == "1" ]]; then
  log "installing pg_basebackup cron (every ${MA3_PG_BASEBACKUP_INTERVAL_MIN}m)"
  if command -v cron >/dev/null 2>&1; then
    (crontab -l 2>/dev/null | grep -v 'pg_basebackup_cron.sh' || true; \
     echo "*/${MA3_PG_BASEBACKUP_INTERVAL_MIN} * * * * set -a && . '$MA3_WORKDIR/ma3.env' && set +a && bash '$MA3_REPO_DIR/deploy/ltp/pg_basebackup_cron.sh' >> /var/log/ma3/basebackup.log 2>&1") | crontab -
    cron || true
  fi
  log "seeding initial basebackup for $MA3_INSTANCE_ID"
  set -a; . "$MA3_WORKDIR/ma3.env"; set +a
  if ! bash "$MA3_REPO_DIR/deploy/ltp/pg_basebackup_cron.sh"; then
    log "WARNING: initial basebackup failed; cron will retry. ma3 startup is NOT blocked."
  fi
fi

INSTANCE_MANIFEST="${MA3_MANIFEST_DIR}/${MA3_INSTANCE_ID}.json"
python3 - "$INSTANCE_MANIFEST" <<'PY'
import json
import os
import pathlib
import time

path = pathlib.Path(__import__("sys").argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
manifest = {
    "format": "ma3-ltp-instance-v1",
    "instance_id": os.environ["MA3_INSTANCE_ID"],
    "job_name": os.environ.get("PAI_JOB_NAME"),
    "task_index": os.environ.get("PAI_CURRENT_TASK_ROLE_CURRENT_TASK_INDEX"),
    "public_base_url": os.environ.get("MA3_PUBLIC_BASE_URL"),
    "git_repo": os.environ.get("MA3_GIT_REPO"),
    "git_ref": os.environ.get("MA3_GIT_REF"),
    "git_commit": os.environ.get("MA3_GIT_COMMIT"),
    "backup_manifest": os.environ.get("MA3_BACKUP_MANIFEST"),
    "v1_to_v2_migration": os.environ.get("MA3_RUN_V1_TO_V2_MIGRATION"),
    "v1_to_v2_report": os.environ.get("MA3_V1_TO_V2_REPORT"),
    "performance_mode": {
        "db_pool_enabled": os.environ.get("MA3_DB_POOL_ENABLED"),
        "db_pool_min_size": os.environ.get("MA3_DB_POOL_MIN_SIZE"),
        "db_pool_max_size": os.environ.get("MA3_DB_POOL_MAX_SIZE"),
        "search_batch_graph_enabled": os.environ.get("MA3_SEARCH_BATCH_GRAPH_ENABLED"),
        "search_index_mode": os.environ.get("MA3_SEARCH_INDEX_MODE"),
    },
    "database": os.environ.get("PGDATABASE"),
    "started_at_epoch": int(time.time()),
    "healthz": f"http://127.0.0.1:{os.environ.get('MA3_PORT', '8000')}/healthz",
    "agents_md": f"{os.environ.get('MA3_PUBLIC_BASE_URL', '').rstrip('/')}/agents.md",
}
path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
PY
ln -sfn "$(basename "$INSTANCE_MANIFEST")" "${MA3_MANIFEST_DIR}/latest-instance.json"
log "instance manifest: ${INSTANCE_MANIFEST}"

log "ready: ${MA3_PUBLIC_BASE_URL}"
tail -F /var/log/ma3/ma3.log
