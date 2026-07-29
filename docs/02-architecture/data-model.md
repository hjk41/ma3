# Data Model Overview

> Chinese version: [data-model.zh.md](data-model.zh.md)

> Field-level details per module live in the corresponding backend docs; this document provides the **entity relationships and state machine** big picture.

## Core ER (logical)

```text
Organization ──< org_members >── Principal (user:xxx)
      │
      └──< libraries (visibility, write_buffer_hours, kind, owner)
                │
                └──< cases ──< records (status, publish_at)
                              └── relations

Principal ──< api_keys ──< api_key_grants >── Library
                │
                └── billing_account_id → billing_accounts → plans

write_audit_log ──> record_id, principal_id, api_key_id (no FK to api_keys)
record_deletions (tombstone)
record_feedback → correctness_tier / Wilson inputs
```

## Record State Machine

```text
ma3_report (new/supplement)
    └──► buffered ──publish_at expiry / ma3_publish_record──► active
              │ PATCH resets publish_at
              └── ma3_delete_record ──► hard delete + tombstone

ma3_report (verify/refute) ──► active (no buffer)

visibility=draft ──► draft ── maintainer review ──► active | invalid

active ── maintainer/user ──► invalid
active ── library with deletion_protection ──► trashed ── retention job ──► hard delete
```

## Key Enums

| Entity | Field | Values |
|------|------|------|
| `libraries.visibility` | | `public` \| `org` \| `private` |
| `libraries.kind` | | `personal` \| … |
| `records.status` | | `active` \| `buffered` \| `draft` \| `invalid` \| `trashed` |
| `api_key_grants.role` | | `reader` \| `writer` |
| `library_grants.role` | | `contributor` \| `maintainer` \| `admin` |
| `plans.code` | | `free` \| `pro` \| `team` |

## Index and Constraint Highlights

- `principals`: `idx_principals_user_display_name` UNIQUE `lower(display_name) WHERE kind='user'`
- `api_keys`: `key_hash` UNIQUE; listings filter `revoked_at IS NULL`
- Personal library idempotency: `(kind='personal', owner_principal_id)`

## Spec Sub-documents

| Topic | Document |
|------|------|
| ACL / grants | [authorization-and-libraries.md](../03-backend/authorization-and-libraries.md) |
| Billing tables | [billing-and-quotas.md](../03-backend/billing-and-quotas.md) |
| Write audit / deletion | [writes-audit-and-deletion.md](../03-backend/writes-audit-and-deletion.md) |
| Buffer | [write-buffer.md](../03-backend/write-buffer.md) |

## To Be Added

- [ ] Full DDL single-page export (kept in sync with `db.py initialize_database`)
- [ ] Migration version history
