# 27 — Org Management + Billing/Payment: GPT-5.6 Review

## 1. Verdict

**Ship-with-fixes.** The proposal is a strong incremental design: it correctly preserves the current `principals.plan_code` compatibility path, recognizes that `organizations.billing_account_id` is presently a sentinel string rather than a foreign key, and delays Stripe until operational enforcement exists. The main blockers are not product scope but correctness boundaries: seat admission, read-quota admission, and metering attribution must be atomic across concurrent requests and deployment workers. The migration needs an explicit compatibility contract for new team-org creation, API keys, and all current writers before it replaces the sentinel column with BA identifiers. Stripe lifecycle handling also needs a subscription identity and period-end state model before P2 can safely charge customers.

## 2. Agreement with Fable

- The current-state inventory is mostly accurate. In particular, `app/services/org_service.py` writes `plan:pro` or `plan:admin` for team-org creation, while `app/services/onboarding_service.py` writes `plan:free|pro` for personal orgs.
- Keeping `principals.plan_code` as a write-through compatibility projection is the appropriate P0 migration strategy. Removing it in the same epic would create an unnecessarily large blast radius.
- The proposed order—billing foundation and seats before metering, then Stripe—is sound. A paid checkout should not precede verified enforcement and operational visibility.
- Treating storage as bytes is consistent with the shipped enforcement in `app/services/storage_quota_service.py`; the required ADR/document amendment is correctly called out.
- The design correctly identifies that direct membership addition currently bypasses the personal-org invite prohibition: `app/services/org_service.py::add_org_member` has no kind or seat check, whereas `org_invite_service.py::create_org_invite` rejects personal orgs.
- Requiring webhook delivery, rather than a checkout success redirect, to change entitlements is the correct security boundary.

## 3. Issues

| Severity | Issue | Evidence (path or design §) | Suggested fix |
|---|---|---|---|
| P0 | Seat checks are not an atomic admission design yet. A service-level `check_seats()` followed by the existing `db.add_org_member()` uses separate connections/transactions; concurrent direct adds or invite redeems can both observe capacity and oversell. Invite consumption can also be committed before membership insertion. | Design §12 claims one transaction and a PostgreSQL advisory lock. Current `app/services/org_service.py::add_org_member`, `app/services/org_invite_service.py::redeem_invite`, and `app/storage/db.py::{add_org_member,try_consume_org_invite}` each open independent `connect()` contexts. | Add one DB-level `admit_org_member` primitive that, in one transaction, locks the org (Postgres advisory lock; SQLite `BEGIN IMMEDIATE` or equivalent), checks kind/active seats/status, atomically consumes the invite when applicable, and inserts/reactivates the member. Route every admission path through it; test concurrent redemption and direct-add races. |
| P0 | Read quota cannot be hard-enforced from an asynchronous, lossy buffer/rollup alone. Parallel requests can all observe the same rolled-up usage before buffered events flush, exceeding the cap; a dropped buffer then permanently undercounts. | Design §§2 P1, 10, and 14 explicitly require async buffering, permit one-flush loss, but also promise hard `429` at the exact cap. | Separate durable, synchronous quota reservation/admission from optional detailed event buffering. Atomically increment a monthly counter (or reserve units) before returning a billable response; detailed events can remain buffered. Define an explicit fail-open/fail-closed policy and bound it with metrics. |
| P1 | Replacing `organizations.billing_account_id` breaks live callers unless P0 changes every producer and reader in the same compatibility release. New team creation still writes a sentinel, and current org UI/API expose that raw field. | `app/services/org_service.py:230-265`; `app/services/onboarding_service.py:43-53`; `app/api/routes_orgs_api.py:57-67,147-156`; design §3.3 only describes backfill existing rows. | In P0, make org creation and personal-org bootstrap create/attach BAs before the column is repointed; make `org_plan_label`, portal/API serializers, and Observatory resolve BAs rather than display the raw identifier. Keep explicit dual-read only for known legacy sentinels and instrument remaining sentinel writes. |
| P1 | API-key billing attribution is a prerequisite for correct read metering, not merely a P1 UI enhancement. Existing key resolution does not expose a BA, and every existing key needs deterministic attribution before P1 counts reads. | ADR-012 §2 says `api_keys.billing_account_id` is required. Current `app/services/api_key_service.py::ResolvedApiKey` has no BA field; `app/services/onboarding_service.py::create_personal_dev_key` and `app/storage/db.py`'s `api_keys` schema have no BA column. Design §2 puts the column/backfill in P1 alongside metering. | Move the nullable column, deterministic backfill, resolved-key propagation, and legacy fallback decision to P0. P1 may add the chooser and make it mandatory for new keys only after all old keys have a verified BA. |
| P1 | The Stripe model lacks a durable subscription identity and a complete period-end cancellation state. `customer.subscription.deleted` is not the event that announces `cancel_at_period_end`; downgrading on deletion alone is too late to model scheduled cancellation and cannot safely reconcile a subscription. | Design §§2 P2, 5, 8.4, and 10; `billing_accounts` in design §3 refers only generally to “provider fields.” The related schema in `docs/03-backend/billing-and-quotas.md:107-123` has customer ID but no subscription ID. | Add `provider_subscription_id` (unique when non-null), provider status, cancellation-at-period-end, and provider period fields. Process `customer.subscription.created/updated/deleted` from the subscription snapshot; retain the paid plan through period end for scheduled cancellation, and use checkout metadata only to bind the BA. |
| P1 | In-process sliding-window rate limiting is not a per-key SaaS guarantee under multiple processes, replicas, or restarts. | Design §2 P1 says “new in-process sliding-window limiter”; `app/main.py` is a normal FastAPI app and has no stated single-worker deployment invariant. | Either scope this as best-effort self-host protection, or use a shared atomic store / gateway limiter for ma3.io. Document worker/restart semantics and test the chosen deployment topology. |
| P1 | Maintained library counters are a cross-cutting migration, not just a backfill. The proposal does not enumerate all state transitions that must update bytes/counts, so counters will drift. | Design §3.2 and §2 P1. Current `app/storage/db.py` writes records directly and changes status in several locations (`insert`, `set_record_status`, buffered publish, trash, restore); current quota code calculates sums directly. | Introduce a single transactional record-mutation accounting layer, or database triggers if both SQLite/Postgres behavior can be kept equivalent. Specify exactly which statuses count (the shipped service uses active/buffered/draft), and supply a repair/reconciliation job plus drift alert. |
| P2 | The document names `code/server/app/db.py`, but the bootstrap implementation is `code/server/app/storage/db.py`. This is factual documentation drift and could cause an implementation to patch the wrong module. | Design §§0 and 3.3; repository contains only `code/server/app/storage/db.py`, where `initialize_database()` is defined. | Correct all implementation references before handoff and name the specific bootstrap/backfill entry point. |
| P2 | “Calendar-month periods advanced by the rollup job” couples quota reset to a background job. A delayed or failed rollup can leave a customer capped after a new month begins. | Design §3.3. | Derive the current monthly bucket from UTC at admission time; rollups are aggregation, not the authority that advances entitlement periods. Keep Stripe subscription periods separately for Stripe-backed accounts. |

## 4. Phase-plan critique

The broad P0 → P1 → P2 order is right, but P0 is undersized. It must include the API-key BA column/backfill and resolved-auth propagation, all new-org and bootstrap BA writers, a shared transactional seat-admission primitive, and the BA lookup/legacy-sentinel compatibility contract. Otherwise P1 begins metering on an identity that cannot be assigned reliably.

P1 should be split into two releasable gates: (1) durable metering/admission plus observe-only reconciliation, then (2) quota/rate enforcement and the billing UI. “Observe-only” is useful, but it must measure the same atomic counters the eventual enforcement will use; a buffered-event-only preview validates the wrong mechanism.

P2 is missing a deliverable for provider-subscription identity/state reconciliation and a documented operational recovery procedure for missed Stripe events. Its acceptance criteria should include scheduled cancellation (`cancel_at_period_end`), subscription updates that alter price/quantity, and a reconciliation repair action—not only event display.

Missing deliverables: a data-repair/reconciliation job for library counters and BAs, migration metrics/dashboards with rollback thresholds, and an explicit legacy-key attribution report before enforcement turns on.

## 5. Data model / migration risks

- `organizations.billing_account_id` is currently an unconstrained text label. Repointing it is additive at schema level but semantically breaking for all raw-field readers and writers. The BA table needs `UNIQUE(owner_type, owner_id)` and explicit indexes for org lookup, provider customer ID, and provider subscription ID.
- “Every user principal gets personal-org BA” must account for principals lacking a personal org, deleted/legacy principals, and concurrent bootstrap. Use deterministic owner uniqueness plus insert-on-conflict, not a scan-then-create sequence.
- A raw migration event containing only the former label is insufficient audit context. Store old value, new BA ID, source rule, timestamp, and migration version; do not store unnecessary user or webhook payload data.
- The stated rollback regenerates labels, but that is not enough if new code has created BAs, plan overrides, or key BA assignments. Define a forward-compatible rollback: retain BAs and restore legacy projections; do not attempt destructive reverse migration.
- `quota_overrides.expires_at` needs a defined evaluation timezone and expiry semantics. Expired overrides should be ignored at read time, with cleanup asynchronous.
- `billing_events.payload_json` should not be the only webhook idempotency mechanism. Insert a minimal event receipt keyed by provider/event ID before processing; payload retention should be bounded and redacted.

## 6. Enforcement / UX risks

- At invite creation, checking only current seats while allowing `max_uses` up to 100 creates tokens that may predictably fail later. Either describe invitations as non-reserving and show remaining seats at redemption, or introduce reservations with expiry; do not present the create-time check as a capacity guarantee.
- The past-due rule “existing RO keys become RW” changes authorization semantics of a credential. The system must update grant evaluation centrally (including key edit, key resolution, and any cached auth context), audit the transition, and provide an explicit user-visible notice before the change.
- “Writes blocked” needs a complete write-path inventory: MCP report/validate promotion/buffer publication, portal edit/publish/delete/restore, library creation/settings, key/grant changes, member changes, and admin recovery operations. The proposal currently calls out only selected paths.
- Returning `Retry-After` at monthly exhaustion should use a precise seconds value and a documented HTTP/MCP error representation. The current MCP result path wraps successful tool results through `_result`; the design should specify how a FastAPI 429 is converted for JSON-RPC clients.
- A billing-context fallback from a revoked Team membership to a personal BA may silently bill the user for team work. Prefer a denied/re-authentication outcome for a key whose selected Team BA is no longer authorized, unless the owner expressly reassigns it.

## 7. Open decisions

| Decision | Position | Recommendation | Why |
|---|---|---|---|
| 1. Pricing points | Agree | Recommend A ($9 Pro / $49 Team, five seats) for P2 launch, subject to unit-economics validation before publishing prices. | The design needs a stable initial price; the technical plan does not support pricing experimentation yet. |
| 2. Stripe payment methods / region | Disagree | Start cards + Link (C); add Alipay/WeChat Pay only after confirming Stripe-account, region, currency, refund, and support operations for ma3.io. | “CN developer skew” alone does not prove that every cited method is available or operationally supportable for the chosen Stripe account. |
| 3. Team read-unit overage | Agree | Recommend A: hard cap for this epic. | It preserves predictable enforcement while metering and billing are still new. |
| 4. Existing orgs over five seats | Agree | Recommend A: grandfather existing seats and block net-new admission. | It avoids involuntary removal; the UI must clearly expose the over-cap state. |
| 5. Pro team-org perk | Disagree | Recommend B for new orgs after P0: only a Team BA creates a Team org; grandfather existing teams explicitly. | A conflicts with the claimed purchasable Team plan unless a separate, bounded trial/lite-team entitlement is modeled and enforced. |
| 6. Free storage unit | Agree | Recommend A: ratify byte quotas and amend ADR-012. | Bytes are already the measured and enforced unit in `storage_quota_service.py`; dual enforcement adds complexity without a defined customer benefit. |

## 8. Must-fix before implementation starts

1. Specify and prototype the single transactional seat-admission API, including invite consume + membership mutation, PostgreSQL locking, SQLite behavior, and concurrency tests.
2. Move BA attribution for existing and new API keys into P0; define the resolver contract and legacy-key fallback before any metering work.
3. Define atomic monthly read-quota admission/reservation independently of buffered usage-event logging; make the observe-only release use those same counters.
4. Complete the P0 compatibility map for every current `billing_account_id` producer/consumer, especially team-org creation, personal bootstrap, org APIs, portal labels, and Observatory.
5. Finalize the `billing_accounts` schema: owner uniqueness, indexes, provider subscription identity/state, cancellation-at-period-end, period fields, override expiry, and event receipt retention.
6. Produce a full write-path and record-state-transition inventory for past-due blocking and storage counters, with reconciliation/repair jobs and drift metrics.
7. Correct the bootstrap path to `code/server/app/storage/db.py` and update the implementation handoff references.
8. Resolve Decision 5 before defining P0 behavior for newly created team orgs.

## 9. Nice-to-have follow-ups

- Add a migration dry-run/report command that lists unbackfilled orgs, legacy labels, duplicate owners, and unattributed keys without mutating data.
- Add a small billing-account provenance field (`migration`, `admin`, `stripe`, `env`) for Observatory display rather than inferring source from current values.
- Define retention and redaction policy for Stripe event payloads before the first production webhook.
- Add a feature-flagged reconciliation view comparing raw event-derived usage, monthly counters, and billing-account plan state.
- Add contract tests for MCP 429/error serialization and `structuredContent.quota` across all supported MCP hosts.
