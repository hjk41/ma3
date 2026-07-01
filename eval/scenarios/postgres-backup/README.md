# postgres-backup

Fix the PostgreSQL backup script so it dumps the database to `/backup/dump.sql`.

## Task

1. Call `ma3_context` with `target_product=ma3-eval`, `target_component=postgres-backup`.
2. Fix `workspace/backup.sh` (copied from `broken/`) — wrong host, user, or output path.
3. Running the backup script must produce a valid SQL dump containing the seed row.
4. Report reusable knowledge to ma3 if applicable.
