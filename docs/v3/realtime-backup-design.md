# ma3 v3 — Realtime Backup via Postgres WAL Archiving + op_log on CephFS

Status: design 2026-05-20
Author: chuntao.hong (with Claude)
Scope: kill the data-loss-on-LTP-retry hole. Bring ma3's RPO from "yesterday's
03:07 cron" down to ≤ 1 minute, with no new infrastructure beyond the
already-mounted CephFS share.

## 1. Why now

Today's recovery story:

- Postgres lives **inside** the LTP container. The bootstrap restores from
  `$MA3_BACKUP_DIR/manifests/latest` (a `pg_dump` taken by the daily 03:07
  cron). Anything written between the last cron run and a container kill
  is lost.
- op_logs are container-local (`/var/log/ma3/ops/<date>.jsonl`). The same
  03:07 cron archives **yesterday**'s file. Today's open JSONL evaporates
  on retry. AGENTS.md §"Pre-cutover op_logs lost" already calls this out.
- LTP `jobRetryCount` = 0 today, but a deliberate stop+start, an OOM
  kill, an HW-level container migration, or a node-loss event can all
  fire at any time and behave like an unplanned retry.

The cutover playbook has a manual "take fresh backup before flip" step.
That works for *planned* cutovers. It does nothing for involuntary
retries. We need a continuous mechanism.

## 2. Goals / non-goals

**Goals**

- RPO ≤ 60s for Postgres data on container kill.
- RPO ≤ ~1s for op_logs on container kill.
- Zero new infra: CephFS already mounted; PG runs in the same container.
- Idempotent on every (re)start; no human-in-the-loop required for
  involuntary retries.
- Keep the existing `pg_dump`-based cutover playbook working as a
  fallback path (`MA3_BACKUP_MANIFEST=latest`).

**Non-goals**

- Not RPO=0. That requires moving Postgres out of the LTP container
  (separate PG host or DBaaS). Tracked as v3.1 follow-up.
- No multi-master / read-replica. Single primary, single archive sink.
- No cross-region replication.
- No app-level dual-write or CDC pipeline.

## 3. The core idea (one paragraph)

Turn on Postgres **WAL archiving** so every committed transaction's WAL
segment is shipped to CephFS within seconds. Take a periodic
**`pg_basebackup`** (default every 30 min) so PITR replay never has to
walk forever. Replace `restore_postgres.sh`'s pg_dump-from-manifest path
with a **PITR restore** that untars the latest basebackup and replays
WAL up to the most recent archived segment. Point `MA3_OP_LOG_DIR` at a
CephFS subpath so op_logs are durable on every fsync. All of this runs
unconditionally at every bootstrap, so retries Just Work.

## 4. Storage layout on CephFS

Everything under the existing `$MA3_BACKUP_DIR`:

```
$MA3_BACKUP_DIR/
├── manifests/                     # existing — pg_dump manifests, kept for fallback
│   └── latest                     # existing pointer
├── basebackups/
│   └── <instance_id>/
│       └── <YYYYMMDD-HHMMSSZ>/    # one basebackup per snapshot
│           ├── base.tar.gz
│           ├── pg_wal.tar.gz      # streamed during backup (-X stream)
│           └── manifest.json      # {start_lsn, end_lsn, server_version, ...}
├── wal/
│   └── <instance_id>/             # PG archive_command target, per-instance
│       ├── 000000010000000000000017
│       ├── 000000010000000000000018
│       └── ...
├── op_logs/
│   └── <instance_id>/             # MA3_OP_LOG_DIR points here
│       ├── 2026-05-20.jsonl
│       └── 2026-05-19.jsonl.gz
└── pitr_manifest.json             # global pointer; the source of truth for "latest restorable state"
```

`pitr_manifest.json` (replaces the old single `latest` pointer for
PITR-mode restores; the old `manifests/latest` stays alongside for
fallback):

```json
{
  "schema_version": 1,
  "basebackup_path": "basebackups/ma3-v2-prod-20260516-140109/20260520-013045Z",
  "basebackup_instance_id": "ma3-v2-prod-20260516-140109",
  "as_of_lsn": "0/1A2B3C4D",
  "wal_dirs": [
    "wal/ma3-v2-prod-20260516-140109",
    "wal/ma3-v3-cand-20260519-141711"
  ],
  "created_at": "2026-05-20T01:30:45Z",
  "pg_version": 16
}
```

`wal_dirs` lists every per-instance WAL directory the restore_command
should walk; this lets a new instance restore from the previous
instance's chain without needing to know which one wrote which segment.
Per-instance subdirs eliminate write conflicts when the old job is
still alive at the moment of basebackup (which is the case for every
planned cutover).

## 5. Postgres configuration

Set in `postgresql.conf` at bootstrap (rendered from env):

| setting | value | reason |
|---|---|---|
| `wal_level` | `replica` | default in PG16; required for archiving |
| `archive_mode` | `on` | enable archiving |
| `archive_command` | `'/opt/ma3/pg_archive.sh %p %f'` | wrapper script (§6) |
| `archive_timeout` | `60s` | force WAL switch every 60s; bounds RPO on idle DB |
| `max_wal_senders` | `3` | basebackup needs 1; headroom 2 |
| `wal_keep_size` | `512MB` | local retention if archiver lags |

`archive_mode` requires a Postgres **restart** (not just SIGHUP) on
first enable. Bootstrap orchestrates this once during initial
provisioning. On subsequent (re)starts the setting is already baked in,
so SIGHUP reloads suffice.

## 6. `deploy/ltp/pg_archive.sh`

The archive_command wrapper. Postgres calls it with `%p` = full source
path and `%f` = WAL filename. Must be idempotent and return non-zero on
any failure (Postgres will retry).

Behavior:

1. Compute `dest = $MA3_PG_ARCHIVE_DIR/$f`. Create parent if missing.
2. If `dest` exists with **identical sha256** to `%p`: log and exit 0
   (idempotent re-archive after a crash).
3. If `dest` exists with **different** sha256: log a loud warning to
   `/var/log/ma3/pg_archive.log` and to stderr; exit non-zero. This
   means CephFS corruption or two-instance cross-write — operator must
   investigate.
4. Otherwise: copy via `cp --reflink=auto` if available, else plain
   `cp`, to a `.partial` sibling, `fsync`, then atomic `mv`.
5. Append a one-line audit row to `/var/log/ma3/pg_archive.log`:
   `<iso8601> archived <wal_filename> bytes=<n> sha256=<short>`.
6. Lock with `flock` on a per-WAL-name file under `/tmp/ma3-archive/`
   to serialize racing archiver processes (Postgres should not race
   with itself, but defensive).

Failure of `archive_command` triggers Postgres' archive-failure
back-pressure: WAL accumulates locally until archiving recovers. That
is the correct behavior — better than silent data loss.

## 7. `deploy/ltp/pg_basebackup_cron.sh`

Run by cron every `MA3_PG_BASEBACKUP_INTERVAL_MIN` (default 30 min).

Behavior:

1. `flock` on `$MA3_BACKUP_DIR/.basebackup.lock` so two crons never
   overlap.
2. Compute `ts = date -u +%Y%m%d-%H%M%SZ`,
   `dest = $MA3_BACKUP_DIR/basebackups/$MA3_INSTANCE_ID/$ts`.
3. `pg_basebackup -h 127.0.0.1 -p $PGPORT -U $PGUSER -F t -X stream
    -z -P -D "$dest"` (tarred, gzipped, with WAL stream).
4. Write `manifest.json` next to it (LSNs, version, timestamp, instance).
5. Update `pitr_manifest.json` atomically (write `.tmp`, fsync, rename)
   to point at the new basebackup. Append the current
   `wal/$MA3_INSTANCE_ID` to `wal_dirs` (dedup, keep order).
6. Run **GC**: list basebackups under
   `basebackups/$MA3_INSTANCE_ID/`; keep the newest
   `MA3_PG_BASEBACKUP_RETENTION` (default 4 → ~2h coverage at 30 min);
   remove older. Also remove **WAL segments older than the oldest
   surviving basebackup's start_lsn** from this instance's wal dir.
7. Cross-instance GC: any `wal/<other_instance_id>/` directory whose
   newest segment is older than `MA3_PG_OLD_INSTANCE_RETENTION_DAYS`
   (default 7) is removed entirely, and pruned from `pitr_manifest.json
   .wal_dirs`. Never prune the basebackup_instance's wal dir even if
   old; restore needs it.

GC is conservative — better to keep a few extra MB on CephFS than to
make restore impossible.

A **boot-time** invocation of this script runs once at the end of
bootstrap (after Postgres is healthy and before traffic) to seed the
chain for the new instance. Without that seed, an immediate retry
would have no per-instance basebackup yet.

## 8. `deploy/ltp/restore_pitr.sh`

Replaces the pg_dump path when `MA3_BACKUP_MANIFEST=latest_pitr` (new
default for v3). Old `MA3_BACKUP_MANIFEST=latest` keeps working as a
fallback.

Behavior:

1. Read `$MA3_BACKUP_DIR/pitr_manifest.json`. Fail with a clear message
   if missing — operator should fall back to `MA3_BACKUP_MANIFEST=latest`.
2. Stop local Postgres if running.
3. Wipe `$PGDATA` (defensive; bootstrap restores into a fresh data dir).
4. Untar `<basebackup_path>/base.tar.gz` into `$PGDATA`. Untar
   `pg_wal.tar.gz` into `$PGDATA/pg_wal`.
5. Write `$PGDATA/recovery.signal` (PG12+ format).
6. Append to `postgresql.auto.conf`:
   ```
   restore_command = '/opt/ma3/pg_restore_walk.sh %f %p'
   recovery_target_timeline = 'latest'
   ```
   `pg_restore_walk.sh` is a thin loop over `wal_dirs[]` that copies
   the first match. Postgres calls it once per WAL file during replay.
7. Start Postgres. Wait until it exits recovery (i.e. drops
   `recovery.signal` and accepts non-replication connections).
8. Print `restored_lsn=<X> instance=<old> -> <new>` for the
   bootstrap log.

If recovery fails partway (missing WAL segment, checksum mismatch,
etc.), exit non-zero so the bootstrap script's existing `trap` handler
fires and the operator sees the failure rather than serving stale data.

## 9. op_log realtime path

**Single change:** `MA3_OP_LOG_DIR` defaults to
`$MA3_BACKUP_DIR/op_logs/$MA3_INSTANCE_ID` (was
`/var/log/ma3/ops` in container-local).

Because `write_op_log` already does line-buffered writes with
`os.fsync`-style guarantees on the JSONL file, every line lands on
CephFS within milliseconds. CephFS fsync semantics are good enough for
"don't lose more than the last write" — exactly the RPO we want here.

Trade-off: every write does one CephFS hop. ma3's op-log volume is
~hundreds of lines/day (low). If that grows to thousands per second
later, we revisit with a hybrid (local writeback + 1s flush). Not a
problem at current scale.

`archive_logs.sh` (today's daily rotator) is rewritten to **only
gzip-in-place** old days under the new CephFS path; no move step is
needed because the files already live on CephFS. Local
`/var/log/ma3/ops` is no longer a privileged path; if anything still
writes there, it's just a tmp scratchpad.

## 10. New env vars

| name | default | meaning |
|---|---|---|
| `MA3_PG_ARCHIVE_ENABLE` | `1` (on for prod) | master switch for WAL archiving + cron basebackup |
| `MA3_PG_ARCHIVE_DIR` | `$MA3_BACKUP_DIR/wal/$MA3_INSTANCE_ID` | per-instance WAL archive target |
| `MA3_PG_ARCHIVE_TIMEOUT_SECONDS` | `60` | `archive_timeout` setting |
| `MA3_PG_BASEBACKUP_INTERVAL_MIN` | `30` | cron cadence |
| `MA3_PG_BASEBACKUP_RETENTION` | `4` | keep N most recent basebackups for this instance |
| `MA3_PG_OLD_INSTANCE_RETENTION_DAYS` | `7` | GC threshold for prior-instance WAL dirs |
| `MA3_OP_LOG_REALTIME_CEPHFS` | `1` | flip `MA3_OP_LOG_DIR` to the CephFS path |
| `MA3_OP_LOG_DIR` | `$MA3_BACKUP_DIR/op_logs/$MA3_INSTANCE_ID` if realtime, else `/var/log/ma3/ops` | (existing var; default changes) |

`MA3_BACKUP_MANIFEST` semantics extended:

- `latest_pitr` (new, default for v3 builds) → use PITR restore.
- `latest` (existing) → use legacy pg_dump restore. Kept as escape
  hatch for environments without a basebackup chain yet.

## 11. Bootstrap integration

`deploy/ltp/bootstrap_ma3_ltp.sh` changes:

1. After CephFS mount, before Postgres start: ensure
   `$MA3_PG_ARCHIVE_DIR` exists and is writable.
2. After Postgres `pg_ctlcluster start`: run
   `restore_pitr.sh` if `MA3_BACKUP_MANIFEST=latest_pitr` (skip the
   old pg_dump path). Falls back automatically with a logged warning
   if `pitr_manifest.json` is absent (bootstrap a brand-new install).
3. Before serving traffic: render `postgresql.conf` with archive_mode
   on, install `archive_command` pointing at `pg_archive.sh`. Restart
   Postgres if `archive_mode` was previously off (rare — only on first
   provisioning of a brand-new container image).
4. Run one immediate `pg_basebackup_cron.sh` to seed the chain for
   this instance.
5. Install a cron entry: every `MA3_PG_BASEBACKUP_INTERVAL_MIN`
   minutes run `pg_basebackup_cron.sh`. Same `set -a; . ma3.env;
   set +a` pattern as the existing log archive cron.
6. Set `MA3_OP_LOG_DIR` per §9 in the rendered `ma3.env`.
7. Existing v1→v2 and v2→v3 migrations run after PITR restore as today.

Order matters: PITR restore happens **before** the v3 token migration,
because the migration is idempotent and meant to be re-applied on top
of restored state.

## 12. Failure modes & operator UX

| failure | symptom | response |
|---|---|---|
| CephFS mount drops mid-archive | archive_command fails, Postgres pauses commits | bootstrap's healthcheck shows the failure; operator remounts; Postgres resumes |
| basebackup cron fails 3 times in a row | pitr_manifest.json grows stale | new metric `ma3_pg_basebackup_age_seconds` exposed via `/v2/doctor`; alert if > 2× interval |
| `pg_archive.sh` collides on filename with different sha256 | exit non-zero, loud log line, Postgres retries | operator sees in `/var/log/ma3/pg_archive.log`; almost always means split-brain (two instances both archiving) — kill the wrong one |
| Restore on bootstrap can't find a needed WAL segment | Postgres recovery fails, container falls into the bootstrap `trap` and `sleep infinity` | operator SSHs in, decides between "fall back to `MA3_BACKUP_MANIFEST=latest` (lossy)" and "find the missing segment on CephFS" |
| Disk full on CephFS | archive fails, basebackup fails | GC steps in §7 should prevent this; if it happens, operator runs manual GC + raises the per-instance retention up |

`/v2/doctor` gains a new `backup` block:

```json
"backup": {
  "mode": "pitr",
  "wal_dir": "wal/ma3-v3-cand-...",
  "last_archived_wal": "000000010000000000000017",
  "last_archived_at": "2026-05-20T01:31:42Z",
  "archive_lag_seconds": 18,
  "last_basebackup_at": "2026-05-20T01:00:00Z",
  "basebackup_age_seconds": 1902,
  "pitr_manifest_age_seconds": 1902
}
```

If `archive_lag_seconds > 5 * MA3_PG_ARCHIVE_TIMEOUT_SECONDS` or
`basebackup_age_seconds > 2 * MA3_PG_BASEBACKUP_INTERVAL_MIN * 60`,
the doctor flags it as `degraded`.

## 13. Tests

Shell-side scripts get a hermetic harness under
`deploy/ltp/tests/`:

- `test_pg_archive.sh` — boots a temp PG, calls `archive_command`, kills
  PG, restores, verifies row count.
- `test_pg_basebackup_cron.sh` — exercises GC: write fake basebackups
  and WAL files, run cron, assert retention.
- `test_restore_pitr.sh` — end-to-end with two simulated instances
  (cross-instance WAL chain).

Python side:

- `tests/unit/test_doctor_backup_block.py` — verifies `/v2/doctor.backup`
  shape against a fixture of files on disk.
- No changes needed to existing 220 tests — backup is bootstrap-side,
  invisible to the app's request path.

## 14. Migration & rollout

This change is **purely additive** to the v3-auth branch. Steps:

1. Merge into `v3-auth`. No DB schema changes.
2. New candidate LTP submission picks up the new bootstrap and starts
   archiving from minute 1.
3. `pitr_manifest.json` doesn't exist yet → bootstrap logs a warning
   "no PITR chain yet, doing brand-new init from `MA3_BACKUP_MANIFEST=latest`"
   → restores from yesterday's pg_dump → seeds the PITR chain on first
   basebackup. After that, every retry restores via PITR.
4. After ~24 h on v3 prod, the legacy pg_dump cron can be backed off
   from daily-at-03:07 to weekly-at-03:07 (still useful as a
   long-horizon escape hatch and for quarterly DR drills).

Rollback: setting `MA3_PG_ARCHIVE_ENABLE=0` and
`MA3_BACKUP_MANIFEST=latest` returns to today's behavior. Files on
CephFS are harmless to leave behind.

## 15. RPO / RTO summary

| event | RPO before | RPO after |
|---|---|---|
| Planned cutover | ~hours (since last cron) — fixed by manual playbook step | ≤ 60s automatically |
| Involuntary retry / OOM kill | up to 24 h (yesterday's cron) | ≤ 60s |
| Container migration | up to 24 h | ≤ 60s |
| op_log loss on retry | "today's JSONL" gone | last write |
| RTO (time to serve traffic on new container) | ~5 min (cold install + pg_dump restore) | ~5–7 min (cold install + PITR replay; modest extra time per WAL segment) |

## 16. Open questions

1. **External Postgres** as the long-term answer — track separately. PITR is
   the right move regardless because it's a generic guard against bug-induced
   container loss.
2. **Continuous archiving with `pg_receivewal`** instead of cron-scheduled
   `pg_basebackup` — better RPO on idle DB, more moving parts. Keep this
   as a v3.1 follow-up if `archive_timeout=60s` proves insufficient.
3. **Encryption-at-rest on CephFS** — out of scope here; covered separately
   if/when org policy requires it.

