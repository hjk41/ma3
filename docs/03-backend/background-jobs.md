# Background Jobs

> Chinese version: [background-jobs.zh.md](background-jobs.zh.md)

> **Status**: TODO — the following is a summary of already-decided behavior

## Established jobs

| Job | Trigger | Behavior | Spec |
|------|------|------|------|
| `publish_due_buffered_records` | Startup + every **60s** | `status=buffered` with `publish_at <= now` → `active` + build index | [write-buffer.md](write-buffer.md) |
| Trashed record purge | Not implemented / v1.1 | `trashed_at + retention_days` → hard delete | [writes-audit-and-deletion.md](writes-audit-and-deletion.md) |
| Usage rollup | Billing Phase B2 | `usage_events` → `usage_daily` / `usage_monthly` | [billing-and-quotas.md](billing-and-quotas.md) |

## Implementation conventions (buffer publish)

- Integrated with FastAPI lifespan / background tasks
- On failure: log + retry on the next tick; does not block the request path
- The author's `ma3_publish_record` **races** with the job: DB row-level status is authoritative

## TODO

- [ ] Job registry (module, function, interval)
- [ ] Single-instance vs. multi-instance leader election (if horizontally scaled)
- [ ] Monitoring: last successful publish job run time
- [ ] Asynchronous embedding index rebuild (if applicable)
