# 16 — Library Write Buffer

> Chinese version: [write-buffer.zh.md](write-buffer.zh.md)

> **Status**: Finalized (2026-07-04, product decision ratified)
> **Acceptance**: [acceptance-criteria.md](../08-quality/acceptance-criteria.md) (`v1-library-write-buffer` pending migration)

---

## 0. TL;DR

Add a configurable **`write_buffer_hours`** (schema default 24) for every **library**. New/supplement records written by a user via an agent are **invisible to others and not searchable/citable** until the buffer period ends; **the writer themself can always see it**. During the buffer period, **only the writer** can **PATCH-edit**, **hard-delete**, or **immediately confirm publish**. When the buffer period elapses, it auto-publishes (`active`).

**Personal libraries**: since the sole owner can already read their own content during the buffer period, the buffer has **no practical effect** for them; the owner can set `write_buffer_hours` to **0** to disable the buffer.

This is a third axis distinct from **`visibility=draft`** (maintainer review queue) and pre-write **`confirmation`** (agent↔user dialogue): **a revocable window after write, before publish**.

---

## 1. Ratified decisions

| # | Topic | **Decision** |
|---|------|----------|
| B1 | Default buffer | **24** (schema default); personal owner **can set 0** |
| B2 | Timer after PATCH | **Resets** `publish_at = now + hours` |
| B3 | Edit semantics | **Overwrite the same record_id** |
| B4 | Writer authority | `write_audit_log.principal_id` |
| B5 | UI | Shipped in v1: `/ui/me/writes/` + action area on `/ui/records/{id}/` |
| B6 | Stats | Buffered records **do not count** toward public active count; author-side "pending publish" count |
| B7 | User disclosure | Writing to the **Community** public library (`lib_default`) knowledge entries |

---

## 2. Scope

| `report_kind` / path | Enters buffer |
|----------------------|---------------|
| **new** / **supplement** | **Yes** (if the library's `write_buffer_hours > 0`) |
| **verify** / **refute** | **No** — locks the target library, should not be hidden |
| Explicit `visibility=draft` | **Not stacked** — goes through the maintainer draft queue |
| Maintainer / admin ghost-writing | **No** (v1 maintainer exemption) |

### Library-level configuration

| Field | Default | Who can change |
|------|------|--------|
| `write_buffer_hours` | **24** | Library owner / library admin; personal owner can set **0** |
| `0` | — | Disables the buffer, writes go straight to `active` (ADR-002 behavior) |

---

## 3. State model

### 3.1 New status: `buffered`

```
ma3_report (supplement/new)
    → status = buffered
    → publish_at = now + write_buffer_hours
    → created_by = principal_id
    → persisted in owner-scoped FTS/embedding indexes; excluded from search / ma3_context for others
    → visible to the writer via deep link + ma3_list_my_writes + their own ma3_context

At end of buffer period (background job, every 60s)
    → status = active

Writer operations:
    publish_now  → active (immediately)
    PATCH        → overwrites the same record_id; publish_at reset
    delete       → ma3_delete_record (hard delete + tombstone)
```

**Not adopted**: a single-state design of "status=active + a hidden field" — Observatory stats, search, and the portal already broadly assume `active` = visible.

### 3.2 Visibility matrix

| Observer | buffered record |
|--------|-----------------|
| **Writer** | Read, PATCH, delete, publish; visible via search/deep link |
| Other readers/agents in the same library | **404**; **not visible** in search / ma3_context |
| Library maintainer | **Not visible in v1** (optionally "visible but not editable" in v1.1) |
| Product admin (Observatory) | Visible, enumerable |
| Library Stats (portal) | **Not counted** toward active; "N pending publish" on the author's side |

---

## 4. Portal UI

```text
/ui/me/writes/          filter "pending publish" / badge / stat link ?status=buffered
/ui/records/{id}/       buffered + owner → [Publish Now] [Edit] [Delete]
/ui/libraries/{id}/settings/  owner/admin → write_buffer_hours form (0–168)
```

Bulk list operations (buffered only): bulk publish · bulk delete → `POST /ui/me/writes/batch` ([22](../04-frontend/information-architecture.md) §3.4).

---

## 5. MCP / Agent contract

| Tool | Change |
|------|------|
| `ma3_report` | Response adds `status: "buffered"`, `publish_at`, `buffer_hours_remaining` |
| `ma3_publish_record(record_id)` | Writer publishes early → active |
| `ma3_patch_record` / recall | Only buffered + owner; PATCH **resets `publish_at`** |
| `ma3_delete_record` | Buffered records can also be deleted |
| `ma3_context` | Never returns others' buffered records; **includes the author's own buffered records** |
| `ma3_list_my_writes` | Adds `status`, `publish_at` |

Agent policy: when receiving `status=buffered`, inform the user of the buffer deadline; suggest `/ui/me/writes/` or `ma3_publish_record` to publish early.

Author recall shares the active-record relevance floor, context boost, GTN ranking, and final limit/case truncation. Every index query must enforce
`status='active' OR (status='buffered' AND created_by=caller)`; buffered rows must never be fetched first and filtered for authorization afterward.
PATCH rebuilds the private index, publish/auto-publish changes its status to active, and deletion removes both FTS and embedding entries.

---

## 6. Relationship to draft / confirmation

| Mechanism | Timing | Visibility | Approver |
|------|------|--------|--------|
| **confirmation** (ADR-013) | **Before** write | Not yet persisted | Agent↔user (not a gate) |
| **buffer** (this design) | **After** write | Author only | Author publishes or timeout |
| **draft** (ADR-002) | **After** write | Maintainer queue | Maintainer approval |

**Mutually exclusive**: `visibility=draft` → **never** also `buffered`; `verify_direct` → goes straight to active, no buffer.

---

## 7. Schema

```sql
ALTER TABLE libraries ADD COLUMN write_buffer_hours INTEGER NOT NULL DEFAULT 24;
ALTER TABLE records ADD COLUMN publish_at TEXT NULL;   -- ISO8601; only for status=buffered
-- records.status allows 'buffered'
```

---

## 8. Scheduled job

`publish_due_buffered_records()`: runs at startup + every 60s as a background task; `publish_at <= now` → `status=active` + build index.

---

## 9. Related documents

- [10-write-audit-and-delete.md](writes-audit-and-deletion.md) — writer determination, deletion
- [15-user-portal.md](../04-frontend/portal-permissions.md) — Stats≠Enumerate
- [22-user-portal-ui-layout.md](../04-frontend/information-architecture.md) — list/filter/batch
