# ADR-007 — v1 milestones: Observatory governance, first deploy, data migration

> Chinese version: [007-v1-milestones-and-observatory-governance.zh.md](007-v1-milestones-and-observatory-governance.zh.md)

## Status

Accepted (2026-07-01)

## Context

Q1–Q12 and ADR 001–006 have already settled the core architecture. Before starting work on `code/`, three execution-layer decisions still needed to be made: Observatory write-permission boundaries, the first runnable environment, and the strategy for legacy library data.

## Decision

### 1. Observatory governance (Option B)

Observatory is primarily **read-only browsing**, for use by **human maintainers**; **agent maintainers** perform equivalent actions via MCP (ADR-008).

Humans can perform **a single write action (v1)** in the UI:

- **Mark a record `invalid`** (with a brief reason)

**Not included in v1**:

- The full review queue UI
- Draft approve/reject forms (still go through MCP `ma3_review_record`)
- Org/seat/billing management

Relationship to ADR-005: adds a **minimal governance write path** on top of the "read-only Observatory," supporting search-pollution mitigation under ADR-002's active-by-default policy.

### 2. First deploy target (Option A)

v1 will **first be validated in parallel on LAN dev (an internal staging host)**:

- A new port (e.g. `:8001`)
- **The same binary** as SaaS, `profile-lan` + `MA3_DEV_AUTH=1`
- Public SaaS staging (full OIDC) proceeds once validation passes on 202

### 3. Data migration (Option C)

**Deploy in parallel, migrate data after cutover**:

- v1 starts with a **new PG database / new schema** (no in-place changes to the production database on `:8000` on 202)
- The old instance on `:8000` keeps serving until v1 validation completes
- At cutover, run a **v2→v1 migration script** (including `org_default` backfill)
- Rollback: point DNS/port back to the old instance

## Consequences

### Positive

- Risk on 202 is controlled and does not affect current `:8000` users
- Observatory gives humans a "correction" button instead of relying entirely on MCP
- A clear migration window that can be dry-run repeatedly

### Negative

- Before cutover, the v1 database is empty or holds only test data, requiring acceptance of a dual-instance period
- The invalid write path requires UI + API + ACL design aligned with MCP semantics

### Related

- ADR-002, ADR-005, ADR-001
- [pitch.md](../../01-product/pitch.md)
- [system-overview.md](../../02-architecture/system-overview.md) — v1 architecture and deploy profiles
- [deployment.md](../../06-operations/deployment.md) — LAN / SaaS deployment
