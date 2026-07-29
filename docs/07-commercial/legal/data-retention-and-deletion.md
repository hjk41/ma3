# ma3 Data Retention & Deletion

> Chinese version: [data-retention-and-deletion.zh.md](data-retention-and-deletion.zh.md)

> Draft data retention & deletion policy for the ma3 hosted
> service (ma3.io), based on the actually implemented behavior in ADR-013
> (write confirmation / audit / delete). **Draft — not lawyer-reviewed.**
> Self-host operators define retention for their own instances.

> **Status: draft. Not lawyer-reviewed.**
> Technical basis: [ADR-013](../../02-architecture/decisions/013-write-confirmation-audit-delete.md),
> [writes-audit-and-deletion.md](../../03-backend/writes-audit-and-deletion.md).

## 1. Owner deletion of records (implemented, self-service)

The record owner (determined by `write_audit_log.principal_id` / `records.created_by`)
can delete their own records at any time via `ma3_delete_record`:

| Library type | Behavior |
|--------|------|
| Default (personal / public / deletion protection off) | **Hard delete**: physically removes the record + index + embedding, and writes a deletion tombstone (`record_deletions`) |
| Libraries with `deletion_protection` enabled (Team plan org libraries) | **Soft delete**: `status='trashed'`, removed from search; recoverable via `ma3_restore_record` during the retention period (default 30 days, `retention_days`), after which a background job converts it to a hard delete |

- Deletion does **not cascade** to downstream records; records referencing a deleted
  record receive `lineage_warnings` on the read path
  ("builds on … which was deleted by owner").
- Buffered records can be deleted the same way.

## 2. Metadata retained after deletion

Even if a record is hard-deleted, the following **metadata** is retained:

| Data | Reason for retention |
|------|----------|
| Deletion tombstones (`record_deletions`: record_id, library_id, deleter, time) | Referential integrity and audit |
| Write audit log (`write_audit_log`) | Abuse accountability, quota enforcement; `api_key_id` is a historical string that keeps the original id even after the key is hard-deleted |
| Operational logs (op logs) | Troubleshooting; rotated as operations require |

Tombstones and audit logs do **not** contain record body content.

## 3. Maintainer takedown

- For infringing or violating content in the public community library, maintainers can
  take down or delete content per the governance rules (ADR-007/008, Observatory).
- **This process is currently not automated**: submit takedown requests via the email
  listed on the maintainer's GitHub profile page
  (see [SECURITY.md](../../../SECURITY.md)), stating the record ID and reason.
  Requests are handled on a best-effort basis with no committed response time.

## 4. Account data deletion

- Account-level deletion (principal, API keys, all personal libraries) currently has
  **no self-service entry point**; contact the maintainers by email. It is handled by
  deleting personal library records (same hard-delete semantics as §1) and revoking keys;
  audit metadata is retained per §2.

## 5. Backups

- ma3.io database backups are for disaster recovery and are rotated per the operations plan;
  deleted data may briefly linger in backups until backup rotation expires them.
  We currently make **no commitment** to a specific backup rotation cycle
  (a formal commitment will accompany the v1.1+ SLA).

## 6. Self-hosted instances

Self-host operators are the data controllers for their instances: the code provides the
same deletion mechanisms as ma3.io (ADR-013 is implemented in the open-source code), but
retention periods, backups, and takedown processes are defined by the operator, who is
responsible to their own users.
