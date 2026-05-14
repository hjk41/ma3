# ma3 on LTP

This directory contains the first-pass deployment path for starting a prod-like
ma3 instance from a single LTP/OpenPAI job.

The target behavior is:

1. Submit one LTP job.
2. The job pulls ma3 code from Codeup/Git.
3. The job checks out the requested branch/commit.
4. The job restores PostgreSQL from a CephFS/3FS backup manifest.
5. The job runs the v1-to-v2 Case/Thread migration by default.
6. The job injects secrets from LTP secrets.
7. The job starts ma3 and writes an instance manifest.

HTTPS certificates are intentionally out of scope for this job-level bootstrap.

## Files

| File | Purpose |
|------|---------|
| `backup_postgres.sh` | Production backup script. Writes `*.sql.gz` plus `*.manifest.json` and `latest.manifest.json`. |
| `restore_postgres.sh` | Restores a backup described by a manifest. Verifies SHA256 before import. |
| `bootstrap_ma3_ltp.sh` | Runs inside the LTP container and starts a ma3 instance. |
| `ma3_ltp_job.yaml.template` | LTP job template showing required env and secrets. |
| `archive_logs.sh` | Compresses completed local operation logs and copies them to CephFS/3FS. |

## Required secrets

Pass these through LTP `secrets`:

- `MA3_ADMIN_KEY`
- `MA3_POSTGRES_PASSWORD`
- `MA3_GIT_TOKEN` or `MA3_GIT_SSH_KEY`

Do not echo these values in commands. Do not enable `set -x`.

## Required job parameters

Render the template with:

- `MA3_INSTANCE_NAME`
- `MA3_DOCKER_IMAGE`
- `MA3_GIT_REPO`
- `MA3_GIT_REF`
- `MA3_GIT_COMMIT` — recommended; pin for reproducibility
- `MA3_PUBLIC_BASE_URL`
- `MA3_INSTANCE_ID`
- `MA3_BACKUP_DIR`
- `MA3_BACKUP_MANIFEST` — usually `latest`
- `MA3_ENABLE_DELTA` — start with `0`
- `MA3_DELTA_URL` — only when delta import is implemented
- `MA3_RUN_V1_TO_V2_MIGRATION` — default `1`; set `0` only for debugging a pure v1 restore
- `MA3_PORT` — default `8000`; on LTP shared-node jobs prefer a high unused port
  such as `18080` to avoid collisions with services already listening on the
  host network namespace
- `MA3_CEPHFS_ENABLE` — set `1` when `MA3_BACKUP_DIR` is on CephFS
- `MA3_CEPHFS_USER` — CephFS user, for example `chuntao.hong`
- `MA3_CEPHFS_MOUNT` — default `/mnt/cephfs`
- `MA3_CEPHFS_FS_NAME` — default `mycephfs`
- `MA3_CEPHFS_MON` — default `10.100.65.50,10.100.65.51,10.100.160.70`
- `LTP_VIRTUAL_CLUSTER`
- `LTP_SKU_TYPE`

The Docker image should include Git, curl, Python venv support, PostgreSQL
server/client, and any storage mount tooling required by the cluster.
`bootstrap_ma3_ltp.sh` makes a best-effort `apt-get` install of missing
Git/curl/Python/PostgreSQL packages on Debian/Ubuntu images, but a prebuilt
internal image is preferred for reproducibility.

The default LTP dependency file is `server/requirements-ltp.txt` via
`MA3_REQUIREMENTS_FILE`. It excludes `sentence-transformers`/torch and sets
`MA3_DISABLE_EMBEDDINGS=1` so startup stays lightweight; semantic embeddings can
be enabled later with a prebuilt image and `server/requirements.txt`.

`restore_postgres.sh` accepts manifests whose `dump_path` is from another host by
falling back to a same-basename dump in the manifest directory. The bootstrap also
auto-detects the running PostgreSQL cluster port when the default `PGPORT` is not
ready. Ensure `MA3_BACKUP_DIR` points to a path actually mounted inside the LTP
container; a host-only CephFS path will otherwise be created as an empty local
directory.

For CephFS backups, do **not** rely on `enableLocalStorage.hostpath=/mnt/cephfs`.
The LTP worker may mount an empty worker-local filesystem there. Instead, enable
the bootstrap CephFS path and pass the keyring via LTP secrets:

```yaml
commands:
  - |
    export MA3_CEPHFS_ENABLE='1'
    export MA3_CEPHFS_USER='chuntao.hong'
    export MA3_CEPHFS_MOUNT='/mnt/cephfs'
    export MA3_CEPHFS_FS_NAME='mycephfs'
    export MA3_CEPHFS_MON='10.100.65.50,10.100.65.51,10.100.160.70'
    export MA3_CEPHFS_KEYRING='<% $secrets.MA3_CEPHFS_KEYRING %>'
```

Use a **current** full keyring copied from `https://ceph-user.zhilicon.com` when
rendering the LTP secret. A stale local keyring cache can have the right
`[client.<user>]` header but still fail Ceph authentication after the portal key
has been reset.

`bootstrap_ma3_ltp.sh` installs `ceph-common`/`ceph-fuse`, writes the keyring to
`/etc/ceph/$MA3_CEPHFS_USER.keyring`, writes `/etc/ceph/ceph.conf` with the MON
hosts, validates that the keyring identity matches `MA3_CEPHFS_USER`, mounts
CephFS with `ceph-fuse`, waits for `/mnt/cephfs` to become a real mountpoint,
and only then reads `$MA3_BACKUP_DIR/latest.manifest.json`.

The job template still keeps `enableLocalStorage` parameterized with
`LTP_STORAGE_HOSTPATH` and `LTP_STORAGE_MNTPATH` for non-Ceph local scratch.
Those fields are not the CephFS data mount.

When running on LTP, do not rely on `/healthz` alone to prove this instance is
serving traffic: another node-local service may already own the requested port.
`bootstrap_ma3_ltp.sh` verifies the uvicorn child process and `/v2/doctor`
identity before writing the instance manifest.

## Backup format

Run on the production instance or backup host:

```bash
export MA3_BACKUP_DIR=/mnt/3fs/data/ma3/backups
export PGHOST=localhost
export PGPORT=5432
export PGDATABASE=ma3db
export PGUSER=ma3user
export PGPASSWORD=...
export MA3_GIT_COMMIT=$(git -C /root/ma3 rev-parse HEAD)
export MA3_PUBLIC_BASE_URL=https://ma3.zhilicon.com

bash deploy/ltp/backup_postgres.sh
```

The script writes:

```text
ma3db_YYYYMMDDTHHMMSSZ.sql.gz
ma3db_YYYYMMDDTHHMMSSZ.manifest.json
latest.manifest.json -> ma3db_YYYYMMDDTHHMMSSZ.manifest.json
```

The manifest includes:

- dump path and checksum
- git commit
- public base URL
- record count
- latest record timestamp
- PostgreSQL WAL LSN
- a `delta_cursor` object

## Delta policy

Initial LTP bootstrap should use full dump restore only:

```bash
MA3_ENABLE_DELTA=0
```

Delta import is intentionally a placeholder in `bootstrap_ma3_ltp.sh`. Before
turning it on, add a versioned, idempotent export/import protocol that covers:

- records
- feedback
- relations
- libraries
- case assignments
- deletes/rejects/status updates

## v1-to-v2 migration

After the full dump restore, `bootstrap_ma3_ltp.sh` runs:

```bash
server/scripts/migrate_v1_to_v2_cases.py --apply --report "$MA3_WORKDIR/v1_to_v2_migration_report.json"
```

The migration is idempotent and deterministic:

- existing v1 records are grouped into v2 Cases using explicit relations first;
- unconnected records are grouped by library, product, component, problem family, and tags;
- `case_id` values are stable hashes of each group’s record IDs;
- the migration writes each record’s `case_id` and upserts matching rows in `cases`;
- rerunning the migration should produce the same case IDs and record assignments.

For a preflight report without writes, run the script manually with `--dry-run`.
The instance manifest includes `v1_to_v2_migration` and `v1_to_v2_report`, but
must not include any secret values.

## Runtime identity

Set `MA3_PUBLIC_BASE_URL`, `MA3_INSTANCE_ID`, and `MA3_GIT_COMMIT`. The server
exposes them through:

- `GET /healthz`
- `GET /v2/doctor`
- rendered `GET /agents.md`

This replaces the old deployment-time `sed -i` rewrite of `agents.md`.

## Instance manifest

`bootstrap_ma3_ltp.sh` writes:

```text
$MA3_BACKUP_DIR/instances/$MA3_INSTANCE_ID.json
$MA3_BACKUP_DIR/instances/latest-instance.json -> $MA3_INSTANCE_ID.json
```

The manifest contains the job name, public URL, git commit, backup manifest, and
health URLs. It must not contain secrets.

## Operation logs

The bootstrap script sets:

```bash
MA3_OP_LOG_DIR=/var/log/ma3/ops
MA3_LOG_ARCHIVE_DIR=$MA3_BACKUP_DIR/logs
MA3_LOG_LOCAL_RETENTION_DAYS=2
MA3_LOG_REDACT_RAW=1
```

ma3 writes JSONL operation logs locally. The bootstrap installs a daily cron job
that runs `deploy/ltp/archive_logs.sh`, compresses completed logs, copies them to
CephFS/3FS under `$MA3_LOG_ARCHIVE_DIR/$MA3_INSTANCE_ID/`, updates a manifest, and
removes old local compressed logs after the configured retention window.
