# ADR-011 — Knowledge Base Access and Organization Isolation

> Chinese version: [011-kb-access-and-org-isolation.zh.md](011-kb-access-and-org-isolation.zh.md)

## Status

Accepted (2026-07-02)

## Context

v1 already implemented the MCP read/write loop, hybrid retrieval, Authing login, and Observatory, but the authorization model was still **env-var key lists + a single hardcoded library**:

- Anonymous reads of `lib_default` (`readable_library_ids` in `security.py` returned the default library for anonymous)
- `MA3_WRITER_API_KEYS` / `MA3_MAINTAINER_API_KEYS` global lists, no per-key ACL
- `organizations` / `libraries` tables existed but had no membership relations and no visibility enforcement
- The `ma3_report` write path was pinned to `lib_default`

Product direction was clear:

1. **Every agent must have a key to access anything**, including the public knowledge base
2. **Encourage contribution over read-only extraction**: for a given library you either have no access or both read and write; **read-only keys can only be created by paid users or members of a paid org**
3. **Organization**: multiple members, members may belong to multiple orgs; org admins can create org libraries; visible within the org by default, can be made public or explicitly granted to external principals

Authorization needed to move from "derived from credentials" to "data-driven", without forking the product.

## Decision

### 1. Two-layer authorization model

**Layer 1 — Entitlement (who *may* access a library)**

| visibility | Who can be granted entitlement |
|------------|------------------------|
| `public` | Any authenticated principal (key still needs an explicit grant) |
| `org` | `org_members` of the owning org |
| `private` | Only explicit `library_grants` rows |

Org admins can promote an org library to `public`, or add `library_grants` for non-member principals.

**Layer 2 — Key capability (what a key can *actually* do)**

- Each API key binds to one or more libraries via `key_grants`
- Per grant row: **read is implied**; `can_write` defaults to **true**; `can_maintain` optional
- **Read + write coupling**: creating a grant with `can_write=false` requires the key owner to have `entitlement=paid`, or belong to any org with `entitlement=paid`
- The public library (`lib_default`, `visibility=public`) does **not automatically** appear on keys; users must **explicitly select** it when creating a key

### 2. Mandatory API keys; anonymous MCP reads removed

- All MCP **data tools** (context / report / case / feedback / review, etc.) require a valid `X-API-Key`
- No key or invalid key → **401** / JSON-RPC `-32001`
- **Authing Bearer** is only for Observatory human login and the key management UI/API; it is **not** a credential for the MCP data path
- `MA3_DEV_AUTH=1` + dev key retained as a **break-glass admin bypass** (LAN/dev only)

### 3. API key storage and issuance

- Keys stored in DB table `api_keys`: `key_hash` (SHA-256), `prefix` (for display), `owner_principal_id`, optional `org_id` (billing/override context), `label`, lifecycle fields
- **Observatory** (Authing session): create / list / revoke keys, configure per-library grants
- **MCP tools**: `ma3_create_key` / `ma3_list_keys` / `ma3_revoke_key`; new key grants must be a **subset** of the owner's entitlement
- `MA3_WRITER_API_KEYS` / `MA3_MAINTAINER_API_KEYS` deprecated (may coexist during migration, see Phase 6)

### 4. Organization and membership

- `org_members(org_id, principal_id, role)`: `role ∈ {admin, member}`; **many-to-many** (one principal may belong to multiple orgs)
- Org admins: create org libraries, set visibility, manage members, grant externally
- `organizations.entitlement ∈ {free, paid}`; likewise `principals.entitlement`
- **Read-only key eligibility**: owner is `paid` **or** owner is a member of any `paid` org (v1 does not distinguish org admin vs member scope)

### 5. Billing

- v1 does **not** integrate a payment gateway; `entitlement` is set manually by platform admins or org admins
- Fields and rules reserved to ease Stripe / enterprise contracts in v1.1

### 6. Public library

- `lib_default` redefined as the **community public library** (`visibility=public`)
- Existing records retained; access still requires a key + explicit `key_grants` rows

### 7. Key-to-library/org binding granularity (no hard isolation)

- We do **not force** one key per library or per single org context: one key may hold grants **across libraries and orgs** (e.g. personal library + public library + company library)
- Entitlement resolution takes the **union** of the key's grants; ma3 does **not** enforce "single org context" isolation server-side
- The resulting "cross-contamination" risk (e.g. an employee touching multiple orgs' libraries with the same key) is **handled by corporate administrative means**: org-issued dedicated keys, device/account management, internal policy; ma3 supports this with **auditability** (every read/write is associated with principal + key + library), not server-side hard binding

## Consequences

### Positive

- Consistent with the "agents deposit verified experience, contribution encouraged" product narrative
- Team isolation is achievable: org libraries + ACL + key grants
- Authorization is auditable: who created which key, with what capabilities on which libraries
- Clean extension points reserved for SaaS subscriptions (read-only seats / org-wide billing)

### Negative

- **Breaking change**: anonymous MCP reads disappear; existing integrations must configure keys
- Implementation effort significantly larger than env-var keys; requires migration, UI, tests
- Org many-to-many combined with visibility raises support and documentation cost

### Related

- ADR-001 (SaaS multi-tenancy), ADR-008 (maintainer tiering), ADR-010 (Authing)
- [ADR-013](013-write-confirmation-audit-delete.md) — write confirmation, audit, owner hard delete
- [authorization-and-libraries.md](../../03-backend/authorization-and-libraries.md) — full schema and phased implementation
- [system-overview.md](../system-overview.md) §2 auth module
- Pitch: [pitch.md](../../01-product/pitch.md)
