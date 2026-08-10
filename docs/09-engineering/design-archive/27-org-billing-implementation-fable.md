# 27 — Org Management + Billing/Payment: Implementation Design (Fable)

> Status: **design-complete; all owner decisions ratified 2026-08-10** (Fable; 5a+8 locked by owner).
> This is a shippable phase plan, not ADR prose. Formal ADRs (011/012/013) and code win on conflict;
> where this doc amends ADR-012 it says so explicitly and lists the doc-sync work.
> Scope: the next implementation epic on top of the shipped v1.1 org/library portal.
> SaaS-primary (ma3.io); self-host keeps admin-set plans with **no Stripe dependency**.

## 0. Ground truth (verified against code 2026-08-10)

**Shipped** (in `code/server/app`):

- Personal + team orgs (`organizations.kind/owner_principal_id/billing_account_id`), `org_members`
  (role admin|member, seat_status, alias), member add/remove/search, last-admin protection,
  token invite links (`org_invite_service` — note: design/24 had deferred invite links to v1.2; they shipped).
- Library grants portal (`/ui/orgs/*`, `/ui/libraries/{id}/{grants,records,storage}/`).
- Paid status = `principals.plan_code ∈ {free, pro}` **or** `MA3_PAID_PRINCIPAL_IDS` env allowlist
  (`onboarding_service.is_paid_principal`). Observatory ops can flip it (`billing_ops_service`).
- Partial quotas: library count (plan + platform caps, `library_quota_service`), personal library
  storage in **bytes** with tiers free/100mb/10gb/1tb (`storage_quota_service`, diverges from ADR-012's
  record counts), team-org creation gate Free 0 / Pro 1 (`org_quota_service`), RO keys for paid
  (free tier gets Community writer lock).
- `organizations.billing_account_id` exists **but holds a `plan:{code}` string label**, not a FK.
  Labels actually written by code: personal orgs get `plan:free|plan:pro` (`onboarding_service.set_user_paid`);
  team orgs get `plan:pro` (Pro creator) or `plan:admin` (product-admin creator) via `org_service.create_team_org`.
  **`plan:team` is never written today** — migration parsing (§3.3) must handle `free|pro|admin`, not `team`.
- `ma3_whoami` already returns a `storage_quota` block for the caller's single owned personal
  library (`mcp_tool_service`); it does **not** return plan/seats/library quotas yet.
- Per-principal storage override env `MA3_PRINCIPAL_STORAGE_TIERS` (`user:id=10gb,…`) exists
  (`storage_quota_service.parse_principal_storage_tier_env`) alongside the paid allowlist.
- Personal orgs: **invite creation is blocked** (400 `cannot invite into a personal organization`,
  `org_invite_service.create_org_invite`) but the **direct member-add path is not** — an org admin
  calling `POST /api/orgs/{org_id}/members` on a personal org succeeds today. P0 closes this.
- Schema migrations are **inline idempotent bootstrap** in `db.py::initialize_database`
  (`CREATE TABLE IF NOT EXISTS` + `_column_exists`-guarded `ALTER TABLE`), run at startup on both
  SQLite and Postgres. There is **no Alembic**; new billing tables follow the same pattern.

**Not shipped**: `plans` / `billing_accounts` / `quota_overrides` / `usage_*` tables, Stripe, read-unit
metering, seat caps (nothing on the invite/add path checks a seat limit today), `/ui/billing/`,
Team as a first-class subscription, **any rate limiter** (metrics count 429s but no middleware
produces them — "per-plan rate limits" in P1 is a build, not a rewire), SSO/SCIM (GitHub issue #3 — design-only).

---

## 0.1 Post-review amendments (2026-08-10, from GPT-5.6 + Grok reviews)

Accepted must-fixes; each amends the section it names. Where a phase table row conflicts with
this list, this list wins.

1. **No unpaid full Team.** §3.3 no longer maps every existing team org → full `team` plan.
   Pro-created (and migrated) team orgs land on **`team_stub`** (Decision 5a = **A**, locked).
   Full `team` requires an active Team subscription (or explicit admin set).
2. **Seat admission is one atomic DB primitive** (`admit_org_member`): single transaction that
   locks the org (Postgres `pg_advisory_xact_lock`; SQLite `BEGIN IMMEDIATE`), checks kind/status/
   seats, consumes the invite when applicable, and inserts/reactivates the member. Every admission
   path (invite create is advisory; invite redeem + direct add are authoritative) routes through it.
   **Invite reservation math**: `seats_used = active_members + sum(remaining_uses of non-expired
   invites)`; invite creation reserves capacity and `max_uses` is clamped to remaining seats.
3. **`api_keys.billing_account_id` moves to P0** (nullable column + deterministic backfill to the
   owner's personal BA + propagation through `ResolvedApiKey`). P1 keeps only the picker UI and
   the "required for new keys" rule. Metering must never start on keys without a verified BA.
4. **Read-quota admission is synchronous and durable**, separate from the buffered `usage_events`
   logger: a monthly per-BA counter is atomically incremented/reserved before returning a billable
   response; the async buffer remains detail/audit only. Observe-only mode reads the same counters
   that enforcement will use.
5. **No RO→RW escalation on private libraries at past_due.** Community `lib_default` may keep
   contribution-first FORCE_RW for free writers. Private/org libraries: **Decision 8 = A
   (revoke)** after **30-day grace**, with **banner + email** at T-7 / T-1 / T-0 (§9).
6. **Self-host defaults**: when `MA3_BILLING_PROVIDER=none`, read-quota enforcement and the rate
   limiter default **off** (`MA3_READ_QUOTA_ENFORCE=0`, `MA3_RATE_LIMIT_ENABLED=0`). SaaS compose
   turns them on explicitly. Private deployments never inherit SaaS caps by default.
7. **SaaS hard gates wait for Checkout** (now **locked Decision 7**, §9): read 429 / RPM 429 /
   past_due write-blocks stay observe-or-soft on ma3.io until Stripe Checkout is live. The
   personal-org direct-add fix still ships in P0 (security, not monetization). Mailto is never
   the SaaS upgrade funnel for a hard gate.
8. Doc drift: bootstrap module is `code/server/app/storage/db.py` (not `app/db.py`); all §0/§3.3
   references read accordingly.

---

## 1. Goals / non-goals

### Goals (this epic)

| # | Goal |
|---|------|
| G1 | `billing_accounts` + `plans` become the **source of truth** for plan/quota; `principals.plan_code` and `plan:` org labels become derived projections |
| G2 | **Seat caps enforced** on team orgs (invite create, invite redeem, direct add) |
| G3 | **Read-unit metering** on `ma3_context`/`ma3_case` with monthly caps and `structuredContent.quota` warnings |
| G4 | **`/ui/billing/`** self-serve surface: plan, usage meters, upgrade path |
| G5 | **Team is a purchasable subscription** (admin-set in P1, Stripe in P2) |
| G6 | **Stripe checkout + webhooks + past_due lifecycle** for Pro (personal) and Team (org) on ma3.io |
| G7 | Self-host parity: everything works with `MA3_BILLING_PROVIDER=none` (admin-set plans, no Stripe code paths) |

### Non-goals (explicitly waits)

| Deferred to | Item |
|---|------|
| v1.2+ | SSO/SCIM (GitHub #3 stays design-only; schema leaves no blockers), invoiced/enterprise contracts, seat self-serve quantity changes with proration, Team read-unit overage billing, contribution credit (write-backs earning read quota), vector-search metering tier, public pricing page CMS, per-record fine RBAC |
| Never (rejected) | Big-bang cutover deleting `principals.plan_code` in this epic; five independently billed quota lines (ADR-012); SPA rewrite of billing UI |

---

## 2. Phased plan

Ship order is strict; each phase is releasable on its own. Sizes: S ≈ ≤2 dev-days, M ≈ ≤1 week, L ≈ 2–3 weeks.

### P0 — Billing foundation + seat caps (M)

No user-visible pricing change. Everything behind the existing behavior.

| Deliverable | Depends on | Size |
|---|---|---|
| Migration: `plans` (seeded free/pro/team), `billing_accounts`, `quota_overrides`, `billing_events` tables | — | S |
| Login bootstrap + one-shot backfill: every user principal gets personal-org `billing_account`; parse `plan:{free\|pro\|admin}` labels + `principals.plan_code=pro` → `plan_code` (mapping in §3.3); repoint `organizations.billing_account_id` to real `ba_*` id | migration | M |
| `billing_service.py`: `effective_plan(billing_account_id)`, `effective_quota(ba, key)` (plan + `quota_overrides`), write-through projection to `principals.plan_code` | migration | S |
| Rewire `is_paid_principal` / `library_quota_service` / `org_quota_service` / `storage_quota_service` to resolve via `billing_service` (env allowlist stays as override) | billing_service | M |
| **Seat enforcement**: `check_seats(org_id)` on invite create, invite redeem, direct member add (this also closes today's gap where direct add to a **personal** org succeeds); personal org hard 1; team `included_seats` + `quota_overrides` | billing_service | S |
| Admin API `PATCH /api/admin/billing-accounts/{ba_id}` (plan_code, status, overrides; §8) + Observatory billing pages write to billing_accounts instead of `set_principal_plan_code` | billing_service | S |
| `ma3_whoami` returns `plan` + quota summary block | billing_service | S |

### P1 — Metering, enforcement, /ui/billing (read-only) (L)

| Deliverable | Depends on | Size |
|---|---|---|
| `usage_events` (append-only) + `usage_daily`/`usage_monthly` rollup job; `record_read_usage()` hooked into `ma3_context`/`ma3_case` success paths (unit formula per ADR-012: `max(1, ceil(records_returned/10))`; 2xx only; async buffer, see §14 risks) | P0 | M |
| `api_keys.billing_account_id`: nullable column, backfill to owner personal BA, key-creation UI/API gains Personal-vs-Team-org picker (member check), required for new keys | P0 | M |
| Monthly read cap → `429` + `Retry-After`; 80% warning via `structuredContent.quota` on every MCP data response | metering | S |
| Team pooled storage quota (bytes) enforced on org-library writes; `libraries.active_record_count` + `storage_bytes` maintained counters; org storage page loses its "preview only" caveat (closes design/24 D5) | P0 | M |
| `/ui/billing/` (personal) + `/ui/orgs/{org_id}/billing/` (org admin): plan card, usage meters (reads, storage, seats, libraries); per locked Decision 7 the SaaS upgrade CTA is hidden/disabled ("Checkout coming soon") until P2 — mailto/admin-contact copy only on self-host | metering | M |
| `past_due` semantics enforced from `billing_accounts.status` (admin-settable now, Stripe-driven later): writes/invites/library-creation blocked, reads fine; private/org RO keys/grants: 30-day grace then **revoke** (Decision 8-A); Community `lib_default` FORCE_RW unchanged; banner+email T-7/T-1/T-0 | P0 | S |
| Per-plan rate limits (60/120/300 rpm per key): **new** in-process sliding-window limiter keyed by `api_key_id` on `/mcp` (no limiter exists today; metrics already count 429s) → `429` + `Retry-After` seconds | P0 | M |

### P2 — Stripe (SaaS only) (L)

| Deliverable | Depends on | Size |
|---|---|---|
| `MA3_BILLING_PROVIDER=stripe|none` config; provider fields on `billing_accounts` already reserved | P1 | S |
| Stripe Checkout: `/ui/billing/upgrade` → hosted Checkout session (Pro personal; Team org with seat quantity), success/cancel return URLs | P1 | M |
| `POST /webhooks/stripe`: signature verification, idempotency via `billing_events`, handlers for `checkout.session.completed`, `customer.subscription.updated/deleted`, `invoice.payment_failed` (→ `past_due`), `invoice.paid` (→ `active`) | checkout | M |
| Stripe Customer Portal link for card/cancel management (no custom UI) | checkout | S |
| Downgrade/grace job: subscription deleted → plan reverts to free at period end; past_due RO grace (30d) then **revoke** private/org grants + T-7/T-1/T-0 email; never auto-delete records (ADR-012/013) | webhooks | M |
| Ops runbook + Observatory reconciliation view (Stripe subscription id ↔ billing_account) | webhooks | S |

### P3 — later (v1.2+ backlog, not scheduled here)

Seat quantity self-serve + proration, Team overage opt-in, SSO/SCIM (#3), contribution credit,
public pricing page, annual billing.

---

## 3. Target data model

New tables follow `docs/03-backend/billing-and-quotas.md` §3 with these **decisive amendments**:

### 3.1 Amendments to the spec

1. **Storage quota unit is bytes, not record counts** (matches shipped `storage_quota_service`).
   `plans` drops `max_records_per_library`/`max_records_total` from enforcement; adds
   `storage_bytes_per_library` and `storage_bytes_total` (team = pooled total). Record counts remain
   display-only metrics (`libraries.active_record_count`). This amends ADR-012 §1/§5 — doc-sync item in §14.
2. **`billing_events` table added** (webhook idempotency + admin audit):
   `id, provider, provider_event_id UNIQUE, type, billing_account_id, payload_json, processed_at, created_at`.
3. **Billing account owner is the org, uniformly.** Personal plans live on the personal org's BA
   (`owner_type='org'`, `owner_id=org_personal_*`). One code path; `owner_type='principal'` stays
   in the CHECK for future flexibility but is unused.
4. `plans` seed (quota values operational, changeable without migration):

| code | scope | RO keys | libs | storage/lib | storage total | read/mo | seats | keys | rpm |
|------|-------|---------|------|-------------|---------------|---------|-------|------|-----|
| free | personal | 0 | 1 | 10 MB (current `personal_library_quota_bytes_free`) | 10 MB | 10,000 | 1 | 10 | 60 |
| pro  | personal | 1 | 5 | 100 MB | 500 MB | 100,000 | 1 | 50 | 120 |
| team_stub | org | 1 | 3 | pooled | 1 GB pooled | 50,000 | 3 | 25 | 120 |
| team | org | 1 | 10 | pooled | 10 GB pooled | 500,000 | 5 | 200 | 300 |

`team_stub` is the ratified Decision **5a=A** package (§9.1). Full `team` is only ever set by an
active Team subscription or an explicit admin action (§3.3).

Also seeded but **not enforced in this epic** (columns exist so ops can tune ahead of enforcement):
`deletion_protection` (Team-only, enforcement rides ADR-013 recycle-bin work, out of scope here)
and `max_external_grants_per_library` (Free=2 per ADR-012 §7; enforcement deferred to P3 backlog).

5. **Env overrides keep working as break-glass, resolved before DB state**:
   `MA3_PAID_PRINCIPAL_IDS` (forces Pro) and `MA3_PRINCIPAL_STORAGE_TIERS` (forces a storage tier)
   stay supported for self-host; `quota_overrides` is the durable, auditable mechanism and wins
   over plan defaults but not over env (env is the operator's last word on their own box).

### 3.2 Column changes to existing tables

| Table | Change |
|---|---|
| `organizations.billing_account_id` | Repointed from `plan:{code}` label to real `billing_accounts.id` (backfill migration, §3.3) |
| `principals.plan_code` | **Kept as derived projection** (write-through on every plan change); consumers migrate to `billing_service`; column removal earmarked v1.3 |
| `api_keys` | `+ billing_account_id TEXT NULL` (**P0**: backfilled to owner personal BA; P1: picker + required for new keys) |
| `libraries` | `+ active_record_count INTEGER NOT NULL DEFAULT 0`, `+ storage_bytes INTEGER NOT NULL DEFAULT 0` (maintained counters; backfill from `sum_library_record_content_bytes`) |
| `org_members` | No change (seat_status/joined_at already shipped) |

### 3.3 Migration strategy from `plan:` string labels

Mechanics: same pattern as every shipped schema change — extend `db.py::initialize_database`
(inline `CREATE TABLE IF NOT EXISTS` + guarded `ALTER TABLE`, runs at startup, SQLite **and**
Postgres; there is no Alembic). The backfill is a separate idempotent pass invoked after
`initialize_database`, not a standalone ops script that can be forgotten.

Idempotent, zero-downtime, two writers tolerated during rollout:

1. Create tables + seed plans (pure additive).
2. Backfill pass (also runs lazily at login bootstrap for stragglers):
   - For each personal org: create `ba_*` with `plan_code = 'pro' if principals.plan_code=='pro' or env allowlist else 'free'`; period = current UTC calendar month.
   - For each team org: parse the existing label. Code today writes `plan:pro` (Pro creator) or
     `plan:admin` (product-admin creator) — never `plan:team`. Mapping (**amended post-review;
     supersedes the earlier "any team org → full `team`" rule**): team orgs map to the **stub
     plan `team_stub`** (Decision 5a=A), `status='active'`, with Decision-4-style grandfathering
     for anything already above the stub caps (existing members/libraries/bytes stay, net-new
     admission blocked or soft-warned per Decision 7). `plan:admin` orgs default to the same stub;
     product admins can raise individual orgs via `quota_overrides` or an explicit `team` set.
     **No org lands on full `team` without an active Team subscription or an explicit admin set.**
     Keep the raw label plus old value, new BA id, source rule, and migration version in
     `billing_events` (`type='migration_backfill'`) for audit.
   - `UPDATE organizations SET billing_account_id = ba_id` (label overwritten; `org_plan_label` switches to reading the joined plan).
3. `is_paid_principal` becomes: env allowlist OR personal-org BA plan is `pro` (fallback to `principals.plan_code` if BA missing — removed at P1).
4. Rollback: labels can be regenerated from BAs; no destructive step until v1.3 column drop.

Period fields: without Stripe, `current_period_start/end` = UTC calendar month, advanced by the rollup
job. With Stripe (P2), subscription period overwrites them via webhook.

---

## 4. Org management scope (this epic)

| Area | In scope | Out of scope |
|---|---|---|
| **Seats** | Enforce `included_seats` on team orgs at invite create + redeem + direct add (`403 seat_limit_exceeded` + upgrade CTA); personal org stays hard-1; members page shows `used/limit` seats; **existing over-cap orgs are grandfathered** (current members keep seats, new adds blocked) per locked Decision 4-A | Seat self-serve quantity purchase / proration (P3) |
| **Roles** | None — stays `admin|member` + library-level `reader|writer|maintainer` | Billing-only role, owner role split (revisit with SSO in v1.2) |
| **Settings** | `/ui/orgs/{id}/settings/` gains a **Billing tab** (org admins only): plan, seats, storage, upgrade CTA | Org rename/delete flows beyond what's shipped |
| **API** | `/api/me/billing`, `/api/orgs/{id}/billing` (GET summaries); admin `PATCH /api/admin/billing-accounts/{ba_id}` (§8); invite/add endpoints return structured seat errors | MCP org-management tools (`ma3_create_org` stays rejected per design/24) |
| **SSO/SCIM** | Nothing ships. Constraint honored: BA is org-scoped so SCIM-provisioned members later just consume seats; no schema blockers | Everything else in GitHub #3 |

---

## 5. Billing/payment scope

**Decisive call: admin-only first (P0/P1), Stripe second (P2).** Rationale: metering and enforcement
must be trustworthy before money changes hands; admin-set plans already have an ops UI and an
established support channel; this de-risks the epic and matches "incremental ship over big-bang".

- **P0/P1 (admin-only)**: plan changes via Observatory / admin API only. `/ui/billing/` shows plan +
  usage; per locked Decision 7 the SaaS surface shows no mailto upgrade funnel (CTA appears with
  Checkout in P2), while self-host shows admin-contact/docs copy. `past_due` settable by
  admins to handle manual invoicing.
- **P2 (Stripe, ma3.io only)**:
  - **Checkout**: Stripe Checkout hosted pages (no custom card UI). Pro = personal-org BA
    subscription; Team = org BA subscription with `quantity = seats` (fixed 5 included at launch;
    quantity editing is P3). Plan↔Price mapping via `MA3_STRIPE_PRICE_PRO` / `MA3_STRIPE_PRICE_TEAM` env.
  - **Webhooks**: `/webhooks/stripe`, signature-verified, idempotent via `billing_events.provider_event_id`.
    State machine: `checkout.session.completed` → activate plan; `invoice.payment_failed` → `past_due`;
    `invoice.paid` → `active`; `customer.subscription.deleted` → revert to free at period end.
  - **past_due**: reads always work; writes to owned libraries, library creation, invites blocked.
    Private/org RO keys and grants: **30-day grace then revoke** (Decision 8-A; amends ADR-012 §5
    "forced RW" for non-Community libs). Community `lib_default` contribution FORCE_RW unchanged.
    Notify: `/ui/billing/` + org billing **banner**, email at **T-7 / T-1 / T-0**, plus
    `structuredContent.quota` warning on MCP.
  - **Cancel/card management**: Stripe Customer Portal, linked from `/ui/billing/`.
- **Self-host**: `MA3_BILLING_PROVIDER=none` (default). Stripe routes 404, checkout CTA hidden,
  admin API is the only plan writer. No Stripe SDK import on the `none` path.

---

## 6. Enforcement matrix

"When" = the request that gets checked. All errors carry structured `detail.error` codes (existing pattern).

| Dimension | Checked at | Free (personal) | Pro (personal) | Team (org) | past_due (any) |
|---|---|---|---|---|---|
| RO key grant | key create / grant edit | 403 → Community grant **forced RW** (shipped) | allowed | allowed (org-billed keys) | private/org existing RO: 30d grace → **revoke**; Community FORCE_RW unchanged |
| Library count | create_library | 1 (shipped) | 5 (shipped) | 10/org paid; **stub=3** | creation blocked |
| Storage (bytes) | `ma3_report` to owned lib | 10 MB, per-record cap (shipped) | 100 MB/lib, 500 MB total | 10 GB org-pooled paid; **stub=1 GB** (**new, P1**) | writes blocked |
| Read units | `ma3_context`/`ma3_case` success | 10k/mo → 429 (**new, P1**) | 100k/mo → 429 | 500k/mo pooled paid; **stub=50k** | reads still allowed |
| Seats | invite create/redeem, member add | personal org: hard 1 (**new, P0**) | same | paid=`included_seats`=5; **stub=3** → 403 (**new, P0**) | invites blocked |
| Team org creation | org create | 0 (shipped) | 1 (shipped) | n/a | blocked |
| Rate limit (rpm/key) | every request | 60 (**new, P1**) | 120 | 300 | plan rate kept |
| Community `lib_default` | any | never counted for storage/library quotas; writes never penalized (contribution-first invariant, ADR-012 §3) | | | |

Warnings (non-blocking): ≥80% of read units or storage → `structuredContent.quota.warnings[]` + UI meter turns amber.

The "Team (org)" column above describes a **paid** Team subscription. Pro-created team orgs run
on **`team_stub`** (Decision 5a=A) with the stub numbers in the matrix notes; same checkpoints and
error codes (`team_upgrade_required` when stub caps bind). Per locked Decision 7, stub read/
storage caps stay observe/soft on SaaS until Checkout is live; seat/library admission enforces
from P0 (non-destructive, grandfathered).

---

## 7. UX surfaces

| Surface | Change | Phase |
|---|---|---|
| `/ui/billing/` | New. Personal plan card, read-units meter (month), storage meter, key count, upgrade CTA (contact → Stripe Checkout in P2), past_due banner | P1 (P2 adds checkout) |
| `/ui/orgs/{id}/billing/` | New, org-admin only. Team plan card, pooled storage, seats used/limit, per-member last-active, upgrade/manage-subscription | P1 |
| `/ui/orgs/{id}/members/` | Seat counter `used/limit`, invite button disabled at cap with tooltip + upgrade link | P0 |
| `/ui/orgs/new/` | Unchanged gate (shipped); error copy gains billing link | P0 |
| `/ui/libraries/{id}/storage/` | Org libraries switch from "preview" to enforced pooled numbers (closes design/24 D5) | P1 |
| Observatory (`/ui/observatory/`) | Billing overview reads `billing_accounts`; user/org detail gains plan/status/override editor; P2 adds Stripe reconciliation column | P0/P2 |
| MCP | `ma3_whoami` plan+quota; all data responses may carry `structuredContent.quota`; skill/policy bundle updated to relay warnings | P0/P1 |

Style: existing SSR + pure-CSS meters (`.storage-meter`), no chart library (design/24). All new POST
routes need `_assert_same_origin`; unauthorized deep links 404 (not 403).

---

## 8. API surface sketch

Route conventions follow shipped code: JSON APIs under `/api/...` (`routes_admin_api` uses prefix
`/api/admin`, orgs use `/api/orgs`), SSR pages under `/ui/...` with `_assert_same_origin` on every
POST, unauthorized org pages return **404 not 403**. All new error responses use the existing
structured shape `detail: {error, message, …}`.

### 8.1 Admin API (product admin; extends `routes_admin_api.py`) — P0

| Route | Purpose |
|---|---|
| `GET /api/admin/billing-accounts?owner_type=&q=&status=` | List/search billing accounts (plan, status, owner, usage summary) |
| `GET /api/admin/billing-accounts/{ba_id}` | Detail: plan, status, period, overrides, provider fields, recent `billing_events` |
| `PATCH /api/admin/billing-accounts/{ba_id}` | Set `plan_code` and/or `status` (`active|past_due|cancelled`); writes a `billing_events` audit row |
| `PUT /api/admin/billing-accounts/{ba_id}/overrides/{quota_key}` / `DELETE …` | Set/clear a `quota_overrides` row (value, reason, expires_at) |
| `PATCH /api/admin/users/{principal_id}/plan` (existing) | Kept as a thin alias that resolves the personal-org BA and writes through `billing_service`; removal earmarked v1.3 |

### 8.2 Portal APIs (session auth; extends `routes_me_api.py` / `routes_orgs_api.py`) — P1

| Route | Purpose |
|---|---|
| `GET /api/me/billing` | Personal BA summary: plan, status, read-units meter, storage, seats, key count, `upgrade_url` |
| `GET /api/orgs/{org_id}/billing` | Same for a team org; **org admin only** (member → 404) |
| Existing `POST /api/orgs/{org_id}/members`, `POST /api/orgs/{org_id}/invites`, `POST /api/invites/redeem` | Gain seat checks; over cap → `403 {error: "seat_limit_exceeded", used, included_seats, upgrade_url}` (P0) |
| Key-creation endpoints (portal keys flow) | Gain a billing-context field (personal vs team org, active-membership checked server-side); sets `api_keys.billing_account_id` |

### 8.3 UI pages (SSR) — P0/P1/P2 per §7

`/ui/billing/` (GET; P2 adds `POST /ui/billing/upgrade` → Stripe Checkout redirect and
`GET /ui/billing/portal` → Stripe Customer Portal redirect), `/ui/orgs/{org_id}/billing/` (GET,
org admin), Observatory `POST /ui/observatory/billing-accounts/{ba_id}/plan` (form twin of the
admin PATCH; same-origin enforced like existing `POST /ui/observatory/users/plan`).

### 8.4 Webhook (SaaS only) — P2

`POST /webhooks/stripe` — mounted **only** when `MA3_BILLING_PROVIDER=stripe`; authenticated by
`Stripe-Signature` header verification (no session/key auth); body size capped; idempotent via
`billing_events.provider_event_id` UNIQUE insert-first; returns 2xx quickly and defers heavy work.

### 8.5 MCP surface

No new tools. `ma3_whoami` gains a `plan` block (P0: plan_code, status, seats, library/storage
quota summaries — extends the shipped `storage_quota` block). Read/data responses may carry
`structuredContent.quota` (P1, §6 warnings). `ma3_doctor` gains `billing_schema_ok` and
`usage_rollup_lag` (P1). New/changed error codes agents can see: `seat_limit_exceeded`,
`read_quota_exceeded` (429), `org_storage_quota_exceeded`, `billing_past_due`,
`billing_context_required`, `rate_limited` (429).

---

## 9. Decisions — ratification status (2026-08-10)

**All owner decisions locked.** Owner ratified 1–4, 6, 7 earlier the same day; **5a = A** and
**8 = A** (grace 30d + banner/email) ratified subsequently.

1. **Pricing points — LOCKED: A.** Pro $9/mo, Team $49/mo (5 seats included, flat price).
   Prices live in Stripe Price IDs referenced via env (`MA3_STRIPE_PRICE_PRO` /
   `MA3_STRIPE_PRICE_TEAM`), **never hardcoded** in code or seed data.
2. **Stripe payment methods — LOCKED: Cards + Link first.** Alipay / WeChat Pay ship as a
   fast-follow **after** Stripe account/region/currency/refund/support operations are confirmed
   for ma3.io — not a day-1 promise anywhere in the UI.
3. **Team read-unit overage — LOCKED: A.** Hard 429 at cap, no overage billing this epic
   (subject to Decision 7 gating: the 429 stays observe/soft on SaaS until Checkout is live).
4. **Existing team orgs over the seat cap — LOCKED: A.** Grandfather current members, block
   new invites/adds until under cap or upgraded. Never auto-remove. (Stub seat cap = 3; paid
   Team = 5 — grandfathering applies relative to the org's effective plan.)
5. **Pro "create 1 team org" perk — LOCKED.** Perk stays; created org gets **`team_stub`**
   weak entitlements (Decision **5a = A**), not the Team SKU. Full Team requires a Team
   subscription (or explicit admin set). See §9.1 for the ratified package.
6. **Free plan storage number — LOCKED: A.** Ratify bytes: Free 10 MB / Pro 100 MB-per-lib +
   500 MB total / Team 10 GB pooled / stub 1 GB pooled; per-record cap 100 KB stays; record
   counts remain display-only metrics. ADR-012 amendment proceeds (§14 doc-sync).
7. **SaaS hard-gate timing — LOCKED.** P1 commercial hard gates on SaaS (read-quota 429,
   RPM 429, past_due write-blocks) stay **observe/soft until Stripe Checkout works** on ma3.io.
   The personal-org seat-abuse fix (direct add to personal org) still ships in P0 — that is a
   security fix, not a monetization gate. Mailto is **not** a SaaS upgrade funnel; it remains
   acceptable only for self-host/enterprise contact.
8. **past_due RO outcome — LOCKED: A (revoke).** After **30 calendar days** in `past_due`
   (grace starts when status flips to `past_due`):
   - **Private and org libraries:** revoke RO key grants / RO library grants (credential may
     remain listed as revoked; auth fails with `grant_revoked` / equivalent). **Never** escalate
     RO → RW on these libraries.
   - **Community `lib_default`:** contribution-first FORCE_RW for free writers unchanged.
   - **Notify:** billing + org-billing **banner** for the duration of grace; **email** to BA
     owner (and org admins for org BAs) at **T-7, T-1, and T-0** (zh/en). MCP
     `structuredContent.quota` carries a past_due / grace countdown warning while applicable.
   - Paying (`invoice.paid` / admin clear) before T-0 cancels the revoke job; after revoke,
     restoring plan does **not** auto-recreate grants — owner must re-issue.

### 9.1 Decision 5a — Stub entitlements — LOCKED: A (`team_stub`)

Options B/C remain archived below for history; **implement A only**.

Context: Pro ($9) may create exactly 1 team org. That org's BA is seeded as `team_stub`.

| Dimension | free personal | pro personal | **`team_stub` (LOCKED)** | full `team` |
|---|---|---|---|---|
| seats (incl. pending-invite reservations) | 1 | 1 | **3** | 5 |
| libraries | 1 | 5 | **3** | 10 |
| storage pooled | 10 MB | 100 MB/lib, 500 MB total | **1 GB** | 10 GB |
| read units / mo (org pool) | 10k (personal) | 100k (personal) | **50k** | 500k |
| RO keys | 0 | 1 | **1** | 1 |
| API keys (org-billed) | 10 | 50 | **25** | 200 |
| rpm / key | 60 | 120 | **120** | 300 |
| duration | perpetual | while Pro sub active | **perpetual** while creator is Pro | while Team sub active |

**Locked package rules (`team_stub`):**

- **Plan code**: `team_stub` (scope `org`), seeded in `plans`; new Pro-created team orgs get
  `plan_code='team_stub', status='active'` at creation.
- **Cap hit**: `403 {error: "team_upgrade_required", plan_code: "team_stub", limit, used,
  upgrade_url}`. Copy: *"This team runs on the starter tier included with Pro (3 seats,
  3 libraries, 1 GB). Upgrade to Team — $49/mo — for 5 seats, 10 libraries, 10 GB pooled
  storage and 500k reads."* `upgrade_url` = Stripe Checkout once P2 is live; before that, per
  Decision 7, read/storage caps are observe/soft on SaaS and only seat/library-count admission
  enforces from P0.
- **Lifecycle tie**: if the creator's Pro lapses, the stub org enters the same blocked-writes
  state as `past_due` (reads fine); re-upgrading Pro or buying Team reactivates. RO grace/revoke
  follows Decision 8.
- **Migration of existing team orgs**: label `plan:pro` → `team_stub`; label `plan:admin` →
  default `team_stub` with `quota_overrides` escape hatch. Decision-4 grandfathering vs stub
  caps (3 seats / 3 libs / 1 GB): over-cap members keep seats (no new adds); libraries over 3
  stay readable/writable but no new library creation; storage above 1 GB → existing records
  readable, new writes soft-warn until Checkout then 403.
- **Upgrade path**: org billing → Stripe Checkout (Team flat price) on the same BA; webhook
  flips `team_stub → team`, no data migration.
- **Deferred (not this epic):** Option B `team_trial` and Option C `team_starter` boost — see
  git history / prior §9.1 draft if revisited in v1.2.

<details><summary>Archived options B/C (not selected)</summary>

#### Option B — `team_trial` (rejected)

14-day full Team then freeze. Rejected: trial expiry must wait for Checkout (Decision 7), so
P0/P1 would still ship unpaid full Team; migration would schedule a synchronized freeze wave.

#### Option C — `team_starter` (rejected for this epic)

Weak base + one-time 14-day boost. Rejected as epic scope; viable v1.2 growth experiment on
top of `team_stub` numbers.

</details>

---

## 10. Acceptance criteria

### P0

- [ ] Fresh DB: first login creates personal org + `billing_accounts` row (plan=free); migration on an existing prod snapshot is **repeatable** (run twice, same result) and every org's `billing_account_id` is a real FK, zero `plan:` labels remain.
- [ ] Setting plan via `PATCH /api/admin/billing-accounts/{ba_id}` flips `is_paid_principal`, RO-key eligibility, library-count limits, and `principals.plan_code` projection — verified by existing quota tests passing unmodified.
- [ ] Team org on `team_stub` at 3 active seats (incl. pending invite reservations): invite create → `403 seat_limit_exceeded`; invite redeem of a pre-existing token at cap → same; personal org member-add → 403; last-admin protection unaffected. Paid `team` at 5 seats behaves analogously.
- [ ] Env allowlist `MA3_PAID_PRINCIPAL_IDS` still overrides to Pro (self-host break-glass).
- [ ] `ma3_whoami` returns `plan`, seats, library and storage quota summary.
- [ ] Self-host bootstrap (no Authing) gets a working default BA; `ma3_doctor` reports `billing_schema_ok`.

### P1

- [ ] 10 successful `ma3_context` calls → `usage_monthly.read_units == 10` for the key's BA; `ma3_report`/`ma3_feedback`/`ma3_validate` produce **zero** billable units; 4xx responses not counted.
- [ ] Free BA at 10,000 read units: next read → `429` with `Retry-After`; writes still succeed (contribution-first).
- [ ] At ≥80% of read or storage quota, MCP responses carry `structuredContent.quota.warnings`.
- [ ] Org library write over pooled Team bytes → `403`, reads unaffected; `libraries.storage_bytes` counter matches `sum_library_record_content_bytes` after backfill.
- [ ] `status='past_due'`: `ma3_report` to owned library 403, invite 403, `ma3_context` succeeds; after 30-day grace, private/org RO grants are **revoked** (not escalated to RW); Community `lib_default` FORCE_RW unchanged; banner visible during grace; email sent at T-7/T-1/T-0 (testable via job harness).
- [ ] `/ui/billing/` and `/ui/orgs/{id}/billing/` render for the right actors (non-admin org member → 404 on org billing), i18n zh/en complete, meters accurate against `usage_monthly`.
- [ ] New key creation requires choosing a billing context; non-member picking a team org → 403.
- [ ] `test_billing_enforcement.py` covers the whole §6 matrix and passes.

### P2

- [ ] `MA3_BILLING_PROVIDER=none` (default): `/webhooks/stripe` and checkout/portal routes are 404, no Stripe SDK import happens, full test suite passes — self-host unchanged.
- [ ] Completing a Stripe Checkout session activates the plan **only** via the webhook (success-URL visit alone changes nothing); the same event delivered twice mutates state once.
- [ ] `invoice.payment_failed` → BA `past_due` (P1 semantics kick in); `invoice.paid` → back to `active`; `customer.subscription.deleted` → free at period end, records untouched.
- [ ] Webhook with a bad/missing signature or a >5-minute-old timestamp → 400, no state change, no `billing_events` row.
- [ ] Observatory reconciliation view shows subscription id ↔ BA mapping and flags divergence (BA plan ≠ Stripe subscription state).

---

## 11. Rollout / rollback

Each phase deploys independently; all schema work is additive until the v1.3 column drop.

| Phase | Rollout | Rollback |
|---|---|---|
| P0 | Deploy → `initialize_database` creates tables, backfill pass runs; **one release of dual-read** (`billing_service` primary, `plan_code` fallback) with a divergence log counter; when divergence is zero, remove fallback (P1). Seat caps activate immediately — safe because existing over-cap orgs are grandfathered (Decision 4-A) and personal-org invites were already blocked | Revert deploy. Old code ignores the new tables; `plan:` labels regenerable from BAs; `principals.plan_code` projection kept current the whole time, so the legacy read path is never stale |
| P1 | Metering ships **observe-only for one release** (`MA3_READ_QUOTA_ENFORCE=0` default off → then flipped on): meters fill, no 429s, ops sanity-check `usage_monthly` against request logs. Rate limiter behind `MA3_RATE_LIMIT_ENABLED`, same two-step. `/ui/billing/` has no write path in P1 — safe to ship dark | Flip the two env flags off (no deploy needed); worst case revert deploy — usage rows are append-only and harmless |
| P2 | Stripe in test mode against staging first; then `MA3_BILLING_PROVIDER=stripe` on ma3.io only. First cohort: internal accounts. Checkout CTA visibility follows the provider flag | Set provider back to `none`: routes 404, plans freeze at last webhook state, admins keep the manual PATCH path. Stripe keeps billing (subscriptions live server-side at Stripe); reconcile via the Observatory view on re-enable |

Monitoring hooks (existing Prometheus setup, design/25): counters for seat-check denials,
read-quota denials, rate-limit 429s, webhook failures/replays, and backfill divergence.

---

## 12. Security / threat notes

| Threat | Mitigation |
|---|---|
| Webhook forgery / replay | `Stripe-Signature` verification (official SDK), reject stale timestamps (>5 min), `provider_event_id` UNIQUE insert-first idempotency, body-size cap, endpoint unmounted unless provider=stripe. Never log full payloads at info level; `billing_events.payload_json` stores the event as received (Stripe payloads carry no card data) |
| Out-of-order / duplicate events | State transitions are compare-and-set against the subscription snapshot in the event, never "apply delta in arrival order" |
| **past_due abuse** (stop paying, keep reading forever) | Reads stay open during `past_due` by design (contribution-first), but Stripe dunning ends in `customer.subscription.deleted` → free-plan caps (10k reads/mo) apply. Admin-set `past_due` on provider=none has no auto-escalation — documented as an ops responsibility. Every status flip is audit-logged in `billing_events` |
| **Seat race** (two invite redeems at cap, TOCTOU) | `check_seats` + `add_org_member` execute in **one transaction** (SQLite single-writer makes this atomic; Postgres uses the same transaction with the count query and insert together — take a per-org advisory lock `pg_advisory_xact_lock(hash(org_id))`). Accepting the lock cost only on member-add paths, not reads |
| Billing-context spoofing (key billed to an org you're not in) | Server-side active-membership check at key creation **and** at every metering write (membership revoked → key falls back to owner's personal BA and org admin sees it in the org key list); org admins can revoke org-billed keys |
| Checkout success-URL forgery | Success URL renders "pending" only; the webhook is the sole plan writer (acceptance-tested) |
| CSRF on new UI writes | `_assert_same_origin` on every new POST (existing pattern + `test_same_origin.py` extended) |
| Enumeration | Org billing pages 404 for non-admins (existing convention); BA ids are non-sequential (`ba_` + random) |
| Metering flood / storage growth | Metering never blocks the request path; raw `usage_events` pruned after 90 days (rollups are the durable record); buffered writer bounds memory (drop-oldest + warning metric on overflow) |
| Env break-glass abuse | `MA3_PAID_PRINCIPAL_IDS` / `MA3_PRINCIPAL_STORAGE_TIERS` remain operator-only (env), shown in Observatory as "env" source exactly as today (`billing_ops_service.enrich_user_billing_row`) |

---

## 13. Test plan

Existing suite layout: `code/server/tests/{unit,integration,e2e}`. **Hard rule from acceptance
criteria: the shipped quota tests pass unmodified after the P0 rewire** (`test_library_quota_service.py`,
`test_org_quota_service.py`, `test_storage_quota_service.py`, `test_storage_quota.py`,
`test_onboarding_service.py`).

New modules:

| Module | Phase | Covers |
|---|---|---|
| `unit/test_billing_service.py` | P0 | `effective_plan` / `effective_quota` precedence (env > override > plan), projection write-through to `principals.plan_code`, period math |
| `integration/test_billing_migration.py` | P0 | Backfill on a synthetic snapshot containing `plan:pro` / `plan:admin` / NULL labels and env-allowlisted users; **run twice, assert identical state**; zero `plan:` labels remain |
| `integration/test_seat_enforcement.py` | P0 | §6 seat row: invite create / redeem / direct add at cap, personal-org direct-add gap closed, grandfathered org (over cap: existing members OK, new add 403), last-admin protection untouched |
| `unit/test_usage_metering.py` | P1 | Unit formula (`max(1, ceil(n/10))`), 4xx/write tools not billable, buffer flush semantics, rollup idempotency |
| `unit/test_rate_limiter.py` | P1 | Per-key windows, per-plan rpm, `Retry-After` header, disabled-by-flag behavior |
| `integration/test_billing_enforcement.py` | P1 | The whole §6 matrix end-to-end (named in acceptance criteria) |
| `integration/test_billing_portal.py` | P1 | `/ui/billing/` + org billing pages: actor gating (member → 404), meters vs `usage_monthly`, i18n zh/en, same-origin on POSTs |
| `integration/test_stripe_webhook.py` | P2 | Signed fixtures for the four handled events, bad signature, replay, out-of-order pairs, provider=none → 404 |

Extended modules: `integration/test_observatory_billing_ops.py` (BA editor writes
`billing_accounts`, not `set_principal_plan_code`), `integration/test_org_invites_api.py` (seat
errors), `integration/test_mcp_integration.py` + `unit/test_mcp_schema_alignment.py` (whoami plan
block, `structuredContent.quota`), `unit/test_same_origin.py` (new POST routes),
`integration/test_migration_pg.py` (new tables on Postgres).

CI: full suite runs with `MA3_BILLING_PROVIDER=none` default (self-host parity is a standing
gate); Stripe tests use a fixture signing secret, no network.

---

## 14. Risks / doc sync

### Risks

| Risk | Mitigation |
|---|---|
| Metering on the hot read path (SQLite write per read) | In-process buffered writer flushing batches ≤1s / ≤100 events; usage loss tolerance 1 flush window; rollup job reconciles; never block or fail a read on metering errors |
| Double-plan-writer window during migration (`plan_code` vs BA) | Single write path through `billing_service` from P0; projection is write-through; fallback read removed in P1 |
| Webhook replay / out-of-order Stripe events | `billing_events.provider_event_id` unique + subscription-state compare-and-set, not event-order trust |
| Seat grandfathering confusion | Explicit `seats_used > included_seats` banner in org billing UI with the grandfather rule spelled out |
| Self-host drift (Stripe-only code creeping into shared paths) | Provider interface with `none` implementation; CI runs the suite with `MA3_BILLING_PROVIDER=none` |
| Read-unit 429 breaking agent loops mid-task | `Retry-After` set to period end is useless mid-month → include `upgrade_url` + quota block so agent policy can surface it to the human; warn at 80% first |
| Backfill on large prod DB | Additive migration + lazy per-login bootstrap keeps the one-shot script small; idempotency test on prod snapshot in CI |

### Doc-sync items (docs currently lag code and this design)

1. **ADR-012 amendment note**: storage quota unit = bytes (this doc §3.1); record counts demoted to display metrics.
2. `docs/03-backend/billing-and-quotas.md`: replace §3.1 plans schema (bytes columns), add `billing_events`, update §9 phase table to P0/P1/P2 here; fix §8 admin route to the real prefix (`PATCH /api/admin/billing-accounts/{ba_id}`, not `/admin/billing_accounts/{id}`); drop "transitional `principals.plan_code`" status line when P0 lands.
3. `docs/07-commercial/pricing-and-plans.md`: rows for storage-in-bytes, seat policy, past_due behavior; fill "To be added" from now-locked Decisions 1–3 (§9); prices referenced as Stripe Price IDs via env, not literals.
4. `docs/09-engineering/design-archive/24-*`: invite links shipped early (correct the v1.2 defer note); D5 (storage preview-only) closed by P1.
5. `docs/03-backend/authorization-and-libraries.md`: RO-key eligibility now resolved via billing account, not `entitlement` fields.
6. **ADR-012 §8 correction**: `principals.entitlement` / `organizations.entitlement` columns were never implemented (code resolves entitlements from grants + org membership in `entitlement_service`); the amendment should state the projection kept is `principals.plan_code`, not `entitlement`.
7. `.zh.md` counterparts for the touched docs; this archive doc itself needs no zh twin (archive is non-contractual).
8. GitHub #3: comment linking this design; restate SSO/SCIM as v1.2 design-only with no schema blockers.

---

## 15. Reviewer brief (GPT + Grok) — completed 2026-08-10

Dual review archived: `27-org-billing-review-gpt56.md`, `27-org-billing-review-grok.md`.
Must-fixes folded into §0.1; owner decisions fully ratified in §9 (including **5a=A `team_stub`**,
**8=A revoke** after 30d + banner/email).

**Known-accepted risks:** metering loses ≤1 flush window on crash; provider=none has no
auto-escalation out of `past_due`; grandfathered team orgs keep **`team_stub`** entitlements
plus Decision-4 grandfathered over-cap resources (not full Team) until they buy Team via Checkout;
B/C stub variants deferred to v1.2.
