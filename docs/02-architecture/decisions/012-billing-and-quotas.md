# ADR-012 — Paid Plans and Quotas (Billing & Quotas)

> Chinese version: [012-billing-and-quotas.zh.md](012-billing-and-quotas.zh.md)

## Status

Accepted (2026-07-02)

## Context

[ADR-011](011-kb-access-and-org-isolation.md) settled: mandatory API keys, read+write by default, read-only keys as a paid privilege, Organization and library isolation. Product proposed five paid triggers:

1. Read-only key privilege  
2. Knowledge base capacity over threshold  
3. Knowledge base count over threshold  
4. Per-account access volume over threshold  
5. Organization members > 1  

Joint review conclusion (Fable and GPT 5.5):

- The five dimensions cover the right ground, but **should not be five independently billed lines** — that risks double-charging and hurts the "contribution first" narrative  
- Converge to **three plans: Free / Pro / Team + quota caps**  
- Introduce **`billing_account` as a first-class entity**; every user gets an implicit **personal org**  
- **Write paths and public-library write-backs** must not punish contributors  

v1 does **not** integrate Stripe; `plan_code` is set manually by platform admins.

## Decision

### 1. Three plans (Free / Pro / Team)

| Dimension | Free | Pro | Team |
|------|------|-----|------|
| Read-only key | ❌ (public grant forced RW) | ✅ personal billing account | ✅ org-billed key |
| Library count | personal: **1**; public grants don't count | personal: **5** | org: **10** |
| Library capacity | **1,000** active records/library, personal total **3,000** | **10,000**/library, total **50,000** | org pooled **100,000** |
| Access volume (read units/month) | **10,000** | **100,000** | org pooled **500,000** |
| Org members | personal org **1 person** | same; can be invited into a Team | **includes 5 seats** |
| Deletion protection (recycle bin/restore) | ❌ | ❌ | ✅ can be enabled on org-owned libraries (see [ADR-013](013-write-confirmation-audit-delete.md)) |
| Rate limit | 60 req/min/key | 120 | 300 |

Concrete numbers live in the `plans` table and can be tuned operationally.

**Read unit**: each successful `ma3_context` / `ma3_case` response counts 1 unit; responses returning >10 records count `ceil(n/10)`. (`ma3_search_explain` has been retired to an internal interface — not via MCP, not billed.) `ma3_report`, `ma3_feedback`, `ma3_validate`, and maintainer tools do **not** count billable units.

### 2. Billing account (first-class entity)

- Table `billing_accounts`: `owner_type` (principal | org), `owner_id`, `plan_code`, `status`, billing-cycle fields  
- First Authing login → create an **implicit personal org** (`org_personal_{sub}`) + personal `billing_account(plan=free)`  
- Explicitly created Team org → its own `billing_account(plan=team)`  
- **`api_keys.billing_account_id` is required**; when creating a key, choose Personal or a Team org (must be a member)  
- Access volume is billed to the **key's billing_account**; storage/library count is billed to the **library owner org's billing_account**

### 3. Contribution-first invariant (must not be violated)

1. Writes to the **public library** (`lib_default`) → storage belongs to the platform, **not counted** against the writer's storage quota  
2. **Write paths such as `ma3_report`** → do not count as read usage  
3. Free users granting the public library → **`can_write` forced true** (ADR-011)  
4. Read-only grants → only when `billing_account.allow_readonly_grants == true` (Pro personal or Team org-billed key)

### 4. Read-only and billing context (narrowing ADR-011)

- ADR-011's "paid-org members may create RO keys" is **narrowed** to: only **org-billed keys** (`billing_account` pointing at a Team org) or an org context explicitly authorized by an org admin  
- Prevents a Team subscription from leaking into members' personal free billing accounts  

### 5. Five-dimension enforcement

| Dimension | When | Over limit |
|------|------|------|
| RO grant | key/grant creation | 403; Free FORCE RW |
| Library count | create_library | 403 + upgrade |
| Storage | ma3_report writing to an **owned** library | Soft warning at 80%; **over cap (≥100%) library becomes read-only**: writes blocked, reads unaffected |
| Read usage | Successful MCP read | Monthly overage 429; Team may opt into overage (v1.1) |
| Org members | Invite accept | 2nd person on free personal 403; Team over seats 403 |

**Downgrade/non-payment**: reads always available; writes/library creation/invites restricted; existing RO keys get a 30-day grace period then become RW or are revoked; **the system never auto-deletes records** (users may hard-delete their own records per [ADR-013](013-write-confirmation-audit-delete.md)).

### 6. Quota and rate limits are separate

- **Rate limit** (req/min): abuse prevention, differs per plan  
- **Monthly read units**: commercial quota, metered independently  

### 7. External collaborators

- `library_grants` do **not** count as org seats  
- Free: cap of **2** external grants per library (configurable in v1.1, design reserved)

### 8. `entitlement` field migration

- `principals.entitlement` / `organizations.entitlement` (ADR-011) remain as **derived compatibility projections**  
- Source of truth: `billing_account.plan_code` + `plans` quota columns + `quota_overrides`

## Consequences

### Positive

- Clear plans: Free for contribution, Pro for personal flexibility, Team for organizational assets  
- The five dimensions map to cost without double-charging  
- billing_account decouples key usage from org resources  
- Schema reserved for Stripe in v1.1  

### Negative

- Implementation complexity higher than a binary `paid` flag  
- The implicit personal org adds onboarding and UI explanation cost  
- Requires usage rollup and enforcement to be integrated together  

### Related

- [ADR-011](011-kb-access-and-org-isolation.md) — ACL prerequisite  
- [ADR-013](013-write-confirmation-audit-delete.md) — owner hard delete and tombstone (amends "records are not deleted")  
- [billing-and-quotas.md](../../03-backend/billing-and-quotas.md) — schema and phased implementation  
- [pricing-and-plans.md](../../07-commercial/pricing-and-plans.md) — commercial narrative  

## Implementation order

1. ADR-011 Phase 1–3 (schema + key auth + entitlement coupling)  
2. ADR-012 Phase B1–B3 (billing schema → metering → enforcement)  
3. ADR-012 Phase B4 (Observatory billing UI + Stripe stub; payment integration in v1.1)  
