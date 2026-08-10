# 27 — Org + Billing Implementation Review (Grok)

> Reviewer: Grok (Cursor), 2026-08-10  
> Design under review: `27-org-billing-implementation-fable.md`  
> Spot-check: `code/server/app` (orgs, invites, quotas, billing_ops, db bootstrap) — light, not a rebuild.

---

## 1. Verdict

**ship-with-fixes**

Fable’s ground truth is accurate, the data-model pivot (`billing_accounts` as SoT, bytes storage, inline bootstrap migration) is the right shape, and admin-first for *schema/enforcement plumbing* is sane. The plan is **not** shippable as written for a SaaS that intends to charge money: it grandfathers every team org onto full Team entitlements, keeps Pro’s “create 1 team org” perk, and then ships hard seat/read enforcement with a **mailto** upgrade CTA until Stripe in P2. That is a giveaway window plus a hostile self-serve dead-end. Fix the Team entitlement model, seat-reservation math, past_due/RO semantics, self-host defaults, and either pull minimal Checkout earlier or keep hard commercial 429s dark until payment works.

---

## 2. What Fable got right

- **§0 ground truth matches code** (spot-checked): `billing_account_id` is a `plan:{code}` label; team create writes `plan:pro` / `plan:admin` via `org_quota_service` + `create_team_org` — **never** `plan:team`; personal invites blocked in `org_invite_service` while `add_org_member` / `POST /api/orgs/{id}/members` has no personal-kind guard; `is_paid_principal` = env allowlist ∪ `principals.plan_code==pro`; storage is bytes tiers; `ma3_whoami` exposes `storage_quota` only; schema via `db.py::initialize_database` + `_column_exists` (no Alembic); no seat checks; metrics count 429s but no limiter produces them.
- **BA owned by org uniformly** — one code path; personal plan on personal org BA.
- **Env break-glass precedence** (`MA3_PAID_PRINCIPAL_IDS`, `MA3_PRINCIPAL_STORAGE_TIERS`) kept above DB overrides — correct for self-host ops.
- **Seat race** called out with txn + Postgres advisory lock — necessary, not hand-waved.
- **Webhook as sole plan writer** for Checkout success URL — correct anti-forgery stance.
- **Observe-then-enforce flags** for read quota / rate limit — right rollout instinct (but see sequencing critique).
- **Contribution-first** preserved: Community writes unmetered; read tools only; 4xx not billed.
- **Doc-sync list** (ADR-012 bytes amendment, entitlement fiction, admin route prefix) is honest and needed.

---

## 3. Issues table

| Pri | Issue | Why it hurts | Fix |
|-----|-------|--------------|-----|
| **P0** | **Pro → free Team entitlements.** §3.3 maps *every* team org → `plan=team` + Decision 5-A keeps Pro’s create-1-team-org perk. Today team library quotas already assume `"team"` (`library_quota_service`), so P0/P1 **productizes unpaid Team** (5 seats, 10 libs, 10 GB, 500k reads) until Stripe. | Revenue leak + abuse: one Pro purchase (or admin flip) unlocks Team pool; mailto CTA cannot close it. Known-accepted risk is underweighted — it *is* the commercial model until P2. | Introduce an explicit **`team_trial` / `team_stub` / unpaid team** plan (or keep team orgs on a **Pro-org stub**: e.g. seats=1–3, libs≤2, storage≪10 GB, reads≪500k) until a Team subscription/`billing_accounts.status=active`+`plan_code=team`. Migration must **not** silently upgrade all orgs to full Team. |
| **P0** | **Hard enforcement + mailto upgrade (P1).** Seat 403 / read 429 / past_due write blocks ship before Checkout. | Agents mid-task get 429 with `upgrade_url=mailto:…`; humans hit a dead-end billing page. Support load spikes; conversion dies. | Either (a) **minimal Stripe Checkout for Pro+Team in P1** (webhook+Checkout only; portal can wait), or (b) keep `MA3_READ_QUOTA_ENFORCE=0` and seat UX as **soft banners** on SaaS until Checkout is live; mailto only for enterprise/invoice. |
| **P0** | **Seat math ignores pending invite capacity.** Invites allow `max_uses` up to **100** (`org_invite_service`); design checks create+redeem but never defines `used = active_members + reserved_invite_slots`. | Classic oversell: at 4/5 seats mint invite `max_uses=100`, or mint five single-use invites; races beyond advisory lock on add alone. | Define `seats_used = active_members + sum(remaining_uses of non-expired invites)`; create invite must reserve; redeem consumes reservation; UI shows reserved vs joined. Cap `max_uses` by remaining seats. |
| **P0** | **RO grace → “forced RW” without revoke.** ADR-012 allows RW *or revoke*; Fable only forces RW. | Non-payment can **escalate** a `reader` key/grant to `writer` on private/org libraries — abuse path (get Pro, issue RO to outsider, go past_due, wait). | Default **revoke or freeze RO grants** after grace; if Community FORCE_RW is required, scope it **only** to `lib_default` grants (ADR-011 contribution rule), never private libs. |
| **P1** | **past_due UX is ops-shaped in P1, product-shaped copy in §5.** Admin can set past_due; no self-serve recover; reads unlimited until someone remembers to cancel→free. | Users see “past due” with no Pay/Update-card button; on SaaS pre-Stripe, status is theater. On Stripe, dunning→deleted path is sketched but **cancel_at_period_end / subscription.updated** handling is thin. | P1: past_due banner copy = “Contact admin” only on `provider=none`; hide consumer past_due chrome on SaaS until Stripe. P2: explicit state machine including `cancel_at_period_end`, `updated` quantity/status, and recovery `past_due→active` without relying only on `invoice.paid`. |
| **P1** | **In-process sliding-window rate limiter.** | Multi-worker / multi-host SaaS makes per-process RPM meaningless (N× limit) or uneven. | Document single-worker assumption **or** use Redis/shared store for SaaS; self-host may keep in-process. Ship limiter behind flag until shared backend exists. |
| **P1** | **Deferred webhook work (“2xx then defer”) with no job queue.** | SQLite single-writer + “defer heavy work” implies a worker that doesn’t exist; easy to ship sync-in-request or lose events. | Process idempotent apply **in-request** if cheap; otherwise durable outbox table + startup/cron worker (same pattern as usage rollup). Acceptance tests must cover crash between insert and apply. |
| **P1** | **Admin PATCH vs Stripe dual-writer in P2.** | Ops flip plan while webhook reconciles → flap / support hell; Observatory “source of truth” unclear. | When `MA3_BILLING_PROVIDER=stripe`, admin PATCH is **override with reason + expires_at** (quota_overrides style) or blocked for `plan_code` except `provider=none` break-glass; Stripe snapshot wins on reconcile. |
| **P1** | **Self-host defaults hostile if enforce flags get flipped globally.** | Private deployments inherit 10k reads/mo + RPM; operators expect unlimited or admin-set only. | Defaults: `provider=none` ⇒ read-quota enforce **off**, rate limit **off** (or astronomical); SaaS deploy compose sets them on. Document in self-host onboarding. |
| **P2** | **Storage totals for Pro (500 MB) and Team pooled 10 GB are new product numbers** not equal to today’s paid=100 MB/lib only. | Silent tightening/loosening at P1 ship surprises existing Pro users. | Call out migration messaging; grandfather over-total libs read-only like seat grandfathering; show meters before enforce. |
| **P2** | **Checkout `quantity=seats` while quantity editing is P3.** | Confused Stripe Price model (per-seat vs flat Team). | Launch Team as **flat Price** (5 seats included); don’t send quantity until self-serve seats exist. |
| **P2** | **Personal-org direct-add gap fix is bundled with seat caps — good — but error copy still 400 string today.** | Inconsistent structured errors (`detail` string vs `{error,...}`). | Personal-org add → `403 {error: "personal_org_seat_limit", …}` aligned with seat_limit_exceeded. |

---

## 4. Product / UX critique

### Billing pages (P1)

- Shipping `/ui/billing/` as a **read-only dashboard + mailto** teaches users the wrong mental model (“this is where I pay”) before payment exists. Prefer: meters + “Plans managed by operator” on self-host; on SaaS, **don’t link Upgrade** until Checkout route exists (feature-flag the CTA).
- Org billing at `/ui/orgs/{id}/billing/` **and** a Settings → Billing tab risks two sources of truth in nav. Pick one primary surface; Settings link should deep-link to the same page.
- Unauthorized → 404 is fine for anti-enumeration; ensure the members page seat tooltip doesn’t 404-loop non-admins toward org billing.

### Seat messaging

- `used/limit` without **pending invites** will look “wrong” the day someone hits cap with open invites. Show `joined + pending = used`.
- Grandfather banner (“you’re over 5 seats; can’t add”) is mandatory — Fable notes it; make it the **first** thing on members + billing, with zh/en parity.
- Personal org: today invites 400-text, direct add succeeds — closing the gap is good; UX should say “Personal accounts are single-user; create a Team org to collaborate” not a generic seat_limit.

### past_due

- Contribution-first reads-during-past_due is a principled ADR call; UX must still say **what is blocked** (writes to owned libs, invites, new libs) and **what still works** (reads, Community write-back).
- P1 admin-set past_due without Pay CTA is confusing on ma3.io. Don’t show Stripe-ish “Update payment method” copy until Portal exists.
- 30-day RO grace needs a visible countdown for org admins (not only MCP `structuredContent`).

### Upgrade CTA: P1 mailto vs P2 Stripe

- **Disagree with mailto as the P1 SaaS upgrade path** if any hard commercial gate is on. Mailto is fine for self-host/observatory-assisted sales; it is not an upgrade funnel.
- Acceptable compromise: P1 meters + soft warnings only on SaaS; hard 429/seat caps for Free→Pro pressure wait for Checkout; seat cap on personal-org abuse can still ship in P0 (security, not monetization).

---

## 5. Abuse / edge cases Fable underweighted

1. **Pro-as-Team mule** — buy/flip Pro, create team org, invite 5, point keys at org BA, burn 500k pooled reads + 10 GB. Design explicitly grandfathers this.
2. **Invite reservation hole** — `max_uses≤100` + check-at-redeem only (or check-at-create without summing pending) oversells seats; shareable links amplify it.
3. **RO→RW escalation** on non-payment (see P0).
4. **Key billing-context revoke race** — membership removed → fallback to personal BA at metering time is good; also need: **immediate** block of org-BA keys when membership ends (not only on next meter write), else ex-member keeps org RPM/read pool until somehow noticed.
5. **Library grants ≠ seats** (ADR-012 §7) — correct, but Free external-grant cap deferred means **unlimited collaborators via grants** while seats are enforced. Seat product feels fake if grants bypass collaboration limits; at least document as intentional loophole or accelerate Free grant cap.
6. **Env allowlist stealth Pro** — fine for break-glass; Observatory must keep showing source=`env` (design says so). Abuse = anyone with deploy env access; accept.
7. **Metering buffer drop-oldest** — attacker floods reads to push others’ events out of buffer pre-flush → under-billing. Bound per-key in buffer or fail-open with metric + sampled durable write.
8. **past_due forever on provider=none** — unpaid tenant keeps full read quota of prior plan until admin moves to free; design docs ops responsibility — add Observatory “aging past_due” alert.
9. **Success-URL + webhook delay** — “pending” UI is right; specify polling/`ma3_whoami` refresh so agents don’t assume upgrade failed and open tickets.
10. **Re-activated removed members** — `seat_status=removed` re-add must hit seat check (likely yes via add path; test it).

---

## 6. Self-host vs SaaS risks

| Area | Risk | Mitigation |
|------|------|------------|
| Provider split | Stripe imports/routes leak into `none` | Keep CI gate Fable already wants; add import-linter or runtime assert in `none` |
| Defaults | Read/RPM limits punish private boxes | Enforce flags default **off** when `provider=none` |
| Team seed | Full Team plan rows exist locally | Self-host admins need clear Observatory “set plan” docs; stub vs team distinction matters here too |
| Dual product UX | Billing pages imply SaaS checkout | CTA/copy driven by provider flag; self-host shows admin contact / docs only |
| Rollback P2 | `provider=none` freezes plans at last Stripe state while Stripe still charges | Runbook must say: cancel in Stripe first **or** accept orphan subscriptions; add Observatory “Stripe says active, BA free” alarm (design has reconcile view — make it P2 acceptance must-pass) |
| Auth bootstrap | Acceptance mentions self-host without Authing | Good; verify `bootstrap_selfhost` creates BA on first ensure_personal_org, not only login paths used by OIDC |

---

## 7. Open decisions — Agree / Disagree

| # | Fable Recommend | Grok | Why |
|---|-----------------|------|-----|
| **1 Pricing** A: Pro $9 / Team $49 | **Agree (weakly)** | Fine mid-market anchor; doesn’t matter until Checkout exists. Prefer locking prices only with Price IDs in env, not in code. |
| **2 Payment methods** B: Cards + Alipay + WeChat | **Agree** | CN-skewed users on ma3.io; verify Stripe Checkout support + tax/invoice display for each method before promising in UI. Fallback: Cards first week, wallets as fast follow. |
| **3 Team overage** A: Hard 429 | **Agree** | Don’t build metered overage before basic Checkout/dunning works. Soft burst (C) is a footgun for agent loops. |
| **4 Over-cap seats** A: Grandfather members | **Agree** | Never auto-remove. Require banner + block adds. Reject C’s sunset unless sales explicitly wants forced churn. |
| **5 Pro keeps create-1-team-org** A: Keep | **Disagree as specified** | Keep the *perk* only if the created org is **not** full Team. As written, A + §3.3 migration = unpaid Team. Prefer: Pro may create 1 org on **stub entitlements**; full Team requires Team subscription (closer to B for entitlements, A for creation right). C (14-day trial) is the cleanest growth experiment — better than silent forever Team. |
| **6 Storage bytes** A: Ratify bytes | **Agree** | Code already ships bytes; dual-enforcing record counts (C) is pure complexity. Update commercial docs so marketing stops promising “3,000 records”. |

---

## 8. Pre-implementation must-fix checklist

- [ ] **Rewrite §3.3 team mapping**: unpaid/pro-created team orgs → stub plan (or trial), not full `team`.
- [ ] **Redefine Decision 5** so Pro creation perk ≠ Team SKU entitlements.
- [ ] **Seat reservation formula** including pending invite remaining uses; clamp `max_uses`; tests for oversell.
- [ ] **RO grace policy**: revoke/freeze on private libs; Community FORCE_RW only on `lib_default`.
- [ ] **SaaS upgrade path**: Checkout-before-hard-429 **or** enforce flags stay off on ma3.io until P2; no mailto-as-upgrade for hard gates.
- [ ] **Self-host defaults**: `provider=none` ⇒ quota/RPM enforce off; CTA hidden.
- [ ] **Rate limiter**: multi-worker story decided (shared store vs single worker).
- [ ] **Webhook apply path**: sync vs outbox; crash consistency test.
- [ ] **P2 dual-writer policy**: Stripe vs admin PATCH.
- [ ] **Team Stripe Price**: flat 5-seat price at launch (no quantity).
- [ ] **Personal org member-add** structured error + test (gap Fable already flagged).
- [ ] **Key revocation on membership loss** immediate, not only metering fallback.
- [ ] Doc-sync items Fable listed (ADR-012 bytes, pricing table, design/24 invite note) scheduled with P0, not “later”.

### Spot-check notes (code vs §0)

| Claim | Result |
|-------|--------|
| `plan:` labels on `organizations.billing_account_id` | **Confirmed** (`onboarding_service.set_user_paid`, `org_service.create_team_org`) |
| `plan:team` never written | **Confirmed** (team create uses `pro`/`admin` from quota summary) |
| Personal invite blocked; direct add not | **Confirmed** (`org_invite_service` vs `add_org_member`) |
| Inline `initialize_database` / no Alembic | **Confirmed** |
| Seat limits absent on invite/add | **Confirmed** |
| `ma3_whoami` storage_quota only | **Confirmed** (`mcp_tool_service`) |
| No rate-limit middleware | **Confirmed** (metrics observe 429 only) |

---

## 9. Optional: alternative sequencing

Disagree with **“admin-first *then* Stripe”** if that means **monetization gates before payment rails**.

**Preferred sequence:**

1. **P0 (same spirit)** — `plans` / `billing_accounts` / overrides / projection rewire / **personal-org add fix** / seat enforcement with **reservation math** / stub-vs-team plan distinction / whoami plan block / Observatory BA editor. *No* unpaid full Team grandfathering.
2. **P1a — SaaS Checkout thin slice** — `MA3_BILLING_PROVIDER=stripe` on ma3.io; Checkout + webhook idempotency for Pro + flat Team; Customer Portal can be same slice or days later. Self-host remains `none`.
3. **P1b — Metering & UI** — usage rollups, `/ui/billing/` with **real** Upgrade/Manage; observe-only then enforce; past_due from `invoice.payment_failed`; RPM limiter only when shared store ready (or accept single-worker).
4. **P2 — Hardening** — reconcile view, dunning edge cases, grace jobs, annual prices, wallets polish.

Admin-only remains the **self-host and break-glass** path forever; it should not be the **SaaS customer** upgrade path for a whole phase after hard caps turn on.

If Stripe truly cannot start yet: ship P0 + billing UI meters with **soft** caps only; do not turn `MA3_READ_QUOTA_ENFORCE=1` or sell “Team” on mailto.

---

## Reviewer brief responses (Fable §15)

1. **Migration two-writers** — Repeatable backfill + login bootstrap is fine; missing pieces are **stub vs team mapping**, NULL personal-org labels (`ensure_personal_org` today often leaves `billing_account_id` unset), and locking Observatory/`set_user_paid` behind `billing_service` in the same release (or divergence will never hit zero).
2. **Enforcement / seat race** — Lock on add is necessary but insufficient without invite reservation; free→paid leak is the Team grandfather, not the seat txn.
3. **Stripe state machine** — Four events are a minimum; add `subscription.updated` semantics, period-end cancel, and dual-writer rules. past_due→paid via `invoice.paid` OK if `updated` can’t leave status sticky.
4. **Phase ordering** — `api_keys.billing_account_id` is correctly P1 for metering; **not** required for P0 seats. P0 *does* need stub plan decision before seat/library numbers mean anything commercially.
5. **Open decisions** — Challenged #5 hard; #2/#3/#4/#6 agree; #1 agree weakly.
