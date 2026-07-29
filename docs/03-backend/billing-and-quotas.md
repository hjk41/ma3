# Billing & Quotas

> Chinese version: [billing-and-quotas.zh.md](billing-and-quotas.zh.md)

> **ADR**: [ADR-012](../02-architecture/decisions/012-billing-and-quotas.md)
> **Prerequisite**: [authorization-and-libraries.md](authorization-and-libraries.md)
> **Status**: Design finalized; **v1 transitional implementation** — paid status = `principals.plan_code=pro` **or** the `MA3_PAID_PRINCIPAL_IDS` env allowlist. Operators can set a user to Pro directly in Observatory (`/ui/observatory/users/`) with no restart required. The full `billing_accounts` / Stripe implementation still lands per Phase B1–B4.
> **Ops UI**: Product admin → Observatory → Billing overview / User billing / Organizations
> **Commercial narrative**: [pricing-and-plans.md](../07-commercial/pricing-and-plans.md), [pitch.md](../01-product/pitch.md)

---

## 1. Goals

| Goal | Description |
|------|------|
| Three-tier plans | Free / Pro / Team, five-dimensional quotas mapped to the `plans` table |
| billing_account | A first-class billing entity for usage and resources |
| Implicit personal org | Every user automatically gets a personal org + free billing account |
| Contribution safety | Public library write-back and `ma3_report` incur no billing penalty |
| No Stripe in v1 | `plan_code` set manually; the schema reserves provider fields |

---

## 2. Conceptual model

```text
Principal (user)
    │
    ├── org_personal_{sub}  ── billing_account(plan=free|pro)
    │         └── libraries (personal, max N)
    │
    └── org_members ── org_company_x ── billing_account(plan=team)
              └── libraries (org visibility)

api_key.billing_account_id  →  read usage is attributed here
library.org_id              →  storage / library count is attributed to the owner org's billing_account
```

### 2.1 Read unit metering

| Tool | Billable | Rule |
|------|----------|------|
| `ma3_context` | Yes | 1 + max(0, ceil(records_returned/10) - 1) |
| `ma3_case` | Yes | Same as above |
| `ma3_report` | **No** | Contribution path |
| `ma3_feedback` | **No** | |
| `ma3_validate` | **No** | |
| `ma3_list_drafts` / `ma3_review_record` | **No** | Maintainer |
| Key management etc. | **No** | |

Only **2xx success** responses count as billable; 4xx are recorded for observability and do not count against quota.

### 2.2 Storage metering

- Count: **active + buffered + draft** records (`invalid` does not count)
- Attribution: library → owner org → org's `billing_account`
- **Public library (`lib_default`)**: owner is treated as the platform; writes **do not consume** any writer's quota
- Field: `libraries.active_record_count` (maintained); optional `storage_bytes` aggregate

---

## 3. Data model

### 3.1 `plans`

```sql
CREATE TABLE plans (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  scope TEXT NOT NULL CHECK (scope IN ('personal', 'org')),
  allow_readonly_grants INTEGER NOT NULL DEFAULT 0,
  deletion_protection INTEGER NOT NULL DEFAULT 0,   -- Team=1, see design/10 §6b
  max_libraries INTEGER NOT NULL,
  max_records_per_library INTEGER NOT NULL,
  max_records_total INTEGER NOT NULL,
  monthly_read_units INTEGER NOT NULL,
  daily_read_units INTEGER,
  rate_limit_per_min INTEGER NOT NULL DEFAULT 60,
  included_seats INTEGER NOT NULL DEFAULT 1,
  max_external_grants_per_library INTEGER NOT NULL DEFAULT 2,
  max_keys INTEGER NOT NULL DEFAULT 10,
  overage_mode TEXT NOT NULL DEFAULT 'block' CHECK (overage_mode IN ('block', 'allow')),
  created_at TEXT NOT NULL
);
```

**Seed (v1 starting point)**:

| code | scope | RO | lib | rec/lib | rec total | read/mo | seats | keys |
|------|-------|----|-----|---------|-----------|---------|-------|------|
| free | personal | 0 | 1 | 1000 | 3000 | 10000 | 1 | 10 |
| pro | personal | 1 | 5 | 10000 | 50000 | 100000 | 1 | 50 |
| team | org | 1 | 10 | 100000 | 100000 | 500000 | 5 | 200 |

For Team, `max_records_per_library` / `max_records_total` are both **org-pooled**.

**Library count quota (design/24, ratified 2026-07-06)** — two tiers:

| Tier | personal org | team org |
|------|--------------|----------|
| Plan (user-visible) | Free **1** / Pro **5** | Team **10** |
| Platform hard cap | **100** | **1000** |

Environment variables: `MA3_PLAN_MAX_LIBRARIES_*`, `MA3_PLATFORM_MAX_LIBRARIES_PERSONAL_ORG` (100), `MA3_PLATFORM_MAX_LIBRARIES_TEAM_ORG` (1000). `lib_default` does not count against any org's library count. Team org ownership has a hard cap of **100** (`MA3_PLATFORM_MAX_TEAM_ORGS_OWNED`); the soft cap on the number of orgs joined is **999**.

### 3.2 `billing_accounts`

```sql
CREATE TABLE billing_accounts (
  id TEXT PRIMARY KEY,
  owner_type TEXT NOT NULL CHECK (owner_type IN ('principal', 'org')),
  owner_id TEXT NOT NULL,
  plan_code TEXT NOT NULL REFERENCES plans(code),
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'past_due', 'cancelled')),
  current_period_start TEXT NOT NULL,
  current_period_end TEXT NOT NULL,
  provider TEXT,
  provider_customer_id TEXT,
  created_at TEXT NOT NULL,
  UNIQUE (owner_type, owner_id)
);
```

### 3.3 `quota_overrides`

```sql
CREATE TABLE quota_overrides (
  billing_account_id TEXT NOT NULL,
  quota_key TEXT NOT NULL,
  value INTEGER NOT NULL,
  reason TEXT,
  expires_at TEXT,
  PRIMARY KEY (billing_account_id, quota_key)
);
```

### 3.4 `usage_events` (append-only) + `usage_daily` / `usage_monthly`

```sql
CREATE TABLE usage_events (
  id TEXT PRIMARY KEY,
  occurred_at TEXT NOT NULL,
  billing_account_id TEXT NOT NULL,
  principal_id TEXT, api_key_id TEXT, org_id TEXT, library_id TEXT,
  tool_name TEXT NOT NULL,
  operation TEXT NOT NULL CHECK (operation IN ('read', 'write', 'admin')),
  units INTEGER NOT NULL DEFAULT 0,
  records_returned INTEGER,
  status_code INTEGER,
  created_at TEXT NOT NULL
);

CREATE TABLE usage_daily (
  billing_account_id TEXT NOT NULL, date TEXT NOT NULL,
  metric TEXT NOT NULL, value INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (billing_account_id, date, metric)
);

CREATE TABLE usage_monthly (
  billing_account_id TEXT NOT NULL, period_start TEXT NOT NULL,
  metric TEXT NOT NULL, value INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (billing_account_id, period_start, metric)
);
```

`metric`: `read_units`, `reports` (for observability, not billable).

### 3.5 Extensions to the tables from 08

| Table | New columns |
|----|------|
| `organizations` | `kind (personal|team)`, `billing_account_id` |
| `api_keys` | `billing_account_id` (read usage attribution) |
| `libraries` | `active_record_count`, optional `storage_bytes` |
| `org_members` | `seat_status (active|pending|removed)`, `joined_at` |

---

## 4. Bootstrap flow

On a user's first Authing login (after `ensure_user_principal`):

```text
1. IF NOT EXISTS org WHERE kind='personal' AND owner=principal:
     CREATE org_personal_{sub}, kind=personal
     CREATE billing_account(owner=org, plan=free)
     INSERT org_members(org, principal, role=admin, seat_status=active)
2. Return principal + personal_org_id + billing_account_id
```

Explicitly creating a Team org (v1.1 UI / MCP): CREATE org(kind=team) + billing_account(plan=team) + creator as admin; when inviting the 2nd person, check `included_seats` (a personal org is always 1 seat → 403).

---

## 5. Enforcement pseudocode

### 5.1 Read-only grant (key creation)

```python
def validate_key_grants(billing_account_id: str, grants: list[KeyGrant]) -> None:
    plan = plan_for_billing_account(billing_account_id)
    for g in grants:
        if g.role == "reader" and not plan.allow_readonly_grants:
            reject_or_force_writer(g)   # v1 UI: free tier Community writer lock (design/14)
        assert_subset_of_entitlement(owner, g.library_id)
```

### 5.2 Storage (ma3_report)

```python
def check_storage_quota(library_id: str) -> QuotaCheck:
    if library_id == settings.public_library_id:
        return QuotaCheck(ok=True)  # platform bears cost
    ba = billing_account_for_library(library_id)
    usage, limit = count_records(ba), effective_quota(ba, "max_records_total")
    if usage >= limit:
        raise HTTPException(403, "library is read-only: storage quota exceeded")  # blocks writes, not reads
    if usage >= limit * 0.8:
        return QuotaCheck(ok=True, warn=True, pct=usage/limit)
    return QuotaCheck(ok=True)
```

### 5.3 Read usage (MCP read tools)

Exceeding the monthly cap → `429` + `Retry-After`.

### 5.4 Org seats

A personal org refuses to add members (403); a team org exceeding `included_seats` → 403 prompting an upgrade.

---

## 6. MCP `structuredContent.quota`

Every MCP response can optionally carry (alongside the `server` block):

```json
{
  "quota": {
    "billing_account_id": "ba_xxx",
    "plan": "free",
    "read_units": {"used": 8200, "limit": 10000, "period": "2026-07"},
    "storage": {"used": 2400, "limit": 3000, "scope": "personal"},
    "warnings": ["read_units at 82%"],
    "upgrade_url": "/ui/billing/"
  }
}
```

Agent policy may require: relay `warnings` to the user when present.

---

## 7. Integration points with 08

| Location in 08 | Hook in 09 |
|---------|---------|
| `validate_key_grants` | `billing_service.allow_readonly()` |
| `create_library` | `check_library_count()` |
| `invite_member` | `check_seats()` |
| MCP read tools | `record_read()` + quota warn |
| `ma3_report` | `check_storage()` |
| `ma3_whoami` | Returns plan + quota summary |
| `ma3_doctor` | `billing_schema_ok`, `usage_rollup_lag` |

---

## 8. Observatory / Admin (Phase B4)

| Page | Function |
|------|------|
| `/ui/billing/` | Current plan, quota usage, upgrade CTA |
| `/ui/billing/upgrade` | Shows Pro / Team; v1 manual contact or admin API |
| Admin API | `PATCH /admin/billing_accounts/{id}` sets `plan_code` (platform maintainer) |

Stripe webhook placeholder: `POST /webhooks/stripe` → v1.1.

---

## 9. Phased implementation

| Phase | Content | Acceptance |
|-------|------|------|
| B1 | Schema + seed plans + login bootstrap of personal org/ba; no enforcement | New user has a personal org + ba after login; migration is repeatable |
| B2 | Metering: `record_read_usage` hooked into read tools + rollup job + `active_record_count` | After 10 reads, `usage_monthly.read_units == 10` |
| B3 | Enforcement: RO grant, library count, storage, seats, read 429, quota warnings; past_due restricts writes not reads | `test_billing_enforcement.py` fully passes |
| B4 | Billing page + admin plan API + Stripe webhook stub | — |

---

## 10. Open questions for v1.1

| Item | Description |
|----|------|
| Team overage default on/off and pricing | Business strategy |
| Whether Pro includes "lite Team" | Product packaging |
| Contribution credit | Trading write-back for read quota |
| Vector search tier | Separate meter |
| Mapping Stripe Price ID to plans | Payment integration |
| Migrating the `max_keys_per_principal` heuristic | Fold into plan.max_keys |
