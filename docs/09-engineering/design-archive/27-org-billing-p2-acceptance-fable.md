# 27 — Org+Billing P2 (Stripe): Acceptance Report (Fable)

> Date: 2026-08-10. Acceptor: Fable (test author). Implementer: Composer.
> Basis: `27-org-billing-implementation-fable.md` §2 P2 + §7 + §8.3/8.4 + §9 Decisions 1/2
> + §10 P2 + §12 threat table + §13, scenario map `27-org-billing-p2-test-scenarios-fable.md`,
> contract `code/server/tests/helpers/billing_p2.py`. Archive doc, no zh twin needed.
> P0/P1 twins: `27-org-billing-p0-acceptance-fable.md`, `27-org-billing-p1-acceptance-fable.md`.

## Verdict: **PASS-with-notes**

All 5 §10 P2 acceptance bullets pass on test-suite evidence; the full P2 set (26 tests,
zero skips — both `importorskip` modules now import, honoring the scenario doc's "no test
may stay skipped" rule), the combined billing suite (127 tests) and the whole regression
suite (517 tests) are green with **zero product-code changes during acceptance**. The one
partial item is bullet 5: the Observatory view ships the subscription↔BA mapping but does
not yet *flag divergence* (D13 below). Five new deviations were found (D13–D17); none
breaks a §10 bullet, and none blocks flipping `MA3_BILLING_PROVIDER=stripe` on staging,
but D13/D16/D17 should be closed before real-money rollout on ma3.io.

## Test results

Environment: `./.venv` Python 3.12, SQLite, `cd code/server`.

| Run | Result |
|---|---|
| `python -m pytest -m billing_p2 -q --tb=short` | **26 passed**, 518 deselected, 13.2s |
| `python -m pytest -m "billing_p0 or billing_p1 or billing_p2" -q --tb=short` | **127 passed**, 417 deselected, 85.4s |
| `python -m pytest -q -m "not deploy and not postgres and not docker and not e2e" --tb=line` | **517 passed**, 27 deselected, 209.2s |

Per-file (all pass): `unit/test_billing_p2_webhook.py` 11 (BP2-W1–W10 + W4b),
`integration/test_billing_p2_checkout_ui.py` 11 (BP2-C1–C7 + C2b/C4b/C4c/C6b),
`integration/test_billing_p2_provider_none.py` 4 (BP2-N1–N4).

Pre-implementation baseline (scenario doc, 2026-08-10) was 4 PASS / 2 module SKIPs —
both skipped modules (webhook unit, checkout UI) now import
`app.services.stripe_billing_service` and pass in full; the 4 provider=none standing
guards (routes existed nowhere then, exist-but-404 now) still hold, which is exactly the
"KEEP answering 404 per request" property the guard was written for.

## §10 P2 checklist

| # | §10 P2 bullet | Status | Evidence |
|---|---|---|---|
| 1 | `MA3_BILLING_PROVIDER=none` (default): `/webhooks/stripe` + checkout/portal routes 404, no Stripe SDK import, full suite passes — self-host unchanged | **PASS** | BP2-N1–N4. Default is `none` (`config.py:68`); gating is evaluated **per request** in every route (`routes_stripe_webhook.py:17`, `routes_billing.py:25-27` via `_require_stripe_routes`) so the §11 rollback story (flip env, no deploy) holds; `stripe` import is lazy inside function bodies only (`stripe_billing_service.py:35-42`, module docstring pins it) and BP2-N3 proves `sys.modules` stays stripe-free across the billing page + all four routes; BP2-N4 keeps the P1 coming_soon page (no form, no stripe.com link); full regression 517 green |
| 2 | Checkout activates the plan **only** via webhook (success-URL visit changes nothing); same event delivered twice mutates once | **PASS** | BP2-C3 (success URL renders `checkout-pending` alert, plan stays `free` in DB — `routes_billing.py:91` renders, no write path), BP2-C4, BP2-W4/W4b/W5. Insert-first idempotency on `billing_events(provider='stripe', provider_event_id)` partial-unique index: `_insert_event_row` inserts before any handler runs and a duplicate returns `{"duplicate": true}` without re-applying (`stripe_billing_service.py:260-262`); BP2-W5 forces state divergence between deliveries to prove the replay is a true no-op. `checkout.session.completed` sets plan from `metadata.plan_code`, status `active`, persists `provider/provider_customer_id/provider_subscription_id` (`stripe_billing_service.py:186-199`) |
| 3 | Webhook with bad/missing signature or >5-min-old timestamp → 400, no state change, no `billing_events` row | **PASS** | BP2-W1/W2/W3, BP2-C4b. `stripe.Webhook.construct_event` with `tolerance=300` (`stripe_billing_service.py:236-242`); any verification failure raises 400 **before** the insert, so no row and no state change (asserted in all four tests). Signature fixtures are real v1 HMACs (`t=<unix>,v1=HMAC_SHA256`), not mocks-that-always-pass. Body-size cap: 2 MiB signed body → 413 before verification (BP2-C4c, `WEBHOOK_MAX_BODY_BYTES` at `stripe_billing_service.py:230-231`) — but see D14 |
| 4 | `invoice.payment_failed` → `past_due` (P1 semantics kick in); `invoice.paid` → `active`; `customer.subscription.deleted` → free at period end, records untouched | **PASS** | BP2-W6/W7/W8/W9. Both invoice handlers resolve the BA via `provider_subscription_id` (`stripe_billing_service.py:202-209`); deletion flips plan `free` / status `active` and **clears** `provider_subscription_id` (`stripe_billing_service.py:212-225`), which makes the late out-of-order `invoice.paid` in BP2-W9 unresolvable → no-op (§12 compare-and-set); records untouched (no record-table writes anywhere in the module); `past_due` handoff to the P1 grace machinery is the P1-tested path (BP1-G1–G5 green in the same run). Unknown types acknowledged without state change (BP2-W10) |
| 5 | Observatory reconciliation view shows subscription id ↔ BA mapping and flags divergence (BA plan ≠ Stripe subscription state) | **PASS-with-notes** | BP2-C7. `/ui/observatory/billing/` renders a "Stripe 对账（subscription ↔ BA）" table (`routes_observatory_ops.py:70-93`) listing every BA with a linked subscription: BA id, plan, status, `provider_subscription_id`, `provider_customer_id` (`billing_ops_service.list_stripe_linked_accounts`). The **mapping** half is met and tested; the **divergence-flagging** half is not implemented — the view lists local rows only, with no Stripe-side comparison and no local heuristic. The scenario doc deliberately pinned only the mapping (no-network rule), so the tested contract is met in full; the design bullet is met partially — see D13 |

Spot-checked implementation surface (read, not re-implemented):
`app/services/stripe_billing_service.py` (full contract: lazy `_stripe()`, env Price IDs via
`_price_for_plan` — Decision 1, never hardcoded amounts; `payment_method_types=["card","link"]`
— Decision 2; `create_checkout_session` with `mode="subscription"`, `client_reference_id`,
`metadata={billing_account_id, plan_code}`; `create_portal_session` 400 `stripe_customer_missing`
for unlinked BA with no Stripe call; mapping-style event access throughout),
`app/api/routes_stripe_webhook.py` (signature-only auth, no session/key dependency),
`app/api/routes_billing.py` (CTA form `action="/ui/billing/upgrade"` only for provider=stripe
+ free plan, org variant for `team_stub`/`free`; `assert_same_origin` on both upgrade POSTs —
§12 CSRF; org upgrade behind `assert_org_admin`, member → 404 per BP2-C6b; portal link only
when `provider_customer_id` set; 303 redirects to the Stripe-hosted urls), settings
(`stripe_secret_key/webhook_secret/price_pro/price_team` env-driven, empty defaults,
`config.py:69-73` — fixture values only in tests, no real secrets in repo). No new tables:
P0's `billing_accounts.provider*` columns and the `billing_events` partial-unique index are
reused exactly as the scenario doc pinned.

## Live spot-check (informational, not acceptance evidence)

The locally reachable instance (`http://127.0.0.1:8010`, the dev/preserve server) is healthy:
`/healthz` 200, `GET /ui/billing/` → 302 to `/auth/login?next=/ui/billing/` (auth-gated as
expected). This is not the live "202" box; per the task note, live 202 may run with test
Stripe — acceptance is based on the test-suite evidence above, not on live behavior.

## P1 deviation follow-up (D2, D8–D12)

| ID | P1 disposition | P2 status |
|---|---|---|
| D2 (legacy quota services not on `effective_quota`) | carry to P2 | **STILL OPEN.** `library_quota_service` / `org_quota_service` / `storage_quota_service` still resolve via `is_paid_principal` (each module's import + call sites unchanged); untouched by the Stripe work — plan flips now arriving via webhook keep working because `set_billing_account_plan` maintains the `principals.plan_code` projection, same masking as P0/P1 |
| D8 (`billing_org_id` conditionally required) | amend contract or tighten in P2 | **UNCHANGED.** Key-creation picker not touched by P2; still 400s only for callers with ≥1 active team membership |
| D9 (scheduler/transport) | partially resolved post-P1 | **UNCHANGED remainder.** Lifespan maintenance loop runs flush + grace job; notifications are still **logged only** — `billing_jobs.py:3-4` says so explicitly, no mail transport. Now that `invoice.payment_failed` flips BAs to `past_due` automatically (not just admin PATCH), the missing T-7/T-1/T-0 mail becomes user-visible on ma3.io — close before enforcing |
| D10 (rollup stub, no reconciliation) | revisit in P2 when Stripe periods matter | **STILL OPEN.** `rollup_usage_monthly()` still returns `{"rolled_up": 0}` (`usage_service.py:71-73`); no `usage_daily`, no doctor `usage_rollup_lag`. Stripe subscriptions bill flat per-seat/plan (no metered billing yet), so period reconciliation still has no money on it — defer to the metered-billing/P3 phase |
| D11 (no membership re-check at metering) | P2 with org key list | **STILL OPEN.** Metering still reads `api_keys.billing_account_id` as-is (`mcp_tool_service.py:331-336`); no org-billed-key view shipped in P2. Unblocked-by but not part of the Stripe scope; schedule with the §12 spoofing row |
| D12 (grouped small gaps) | sweep in P2 | **MOSTLY OPEN.** (d) `/api/me/billing` `keys.used` still hardcoded 0 (`routes_billing.py:50-53`); (a)/(b)/(c)/(e) not re-audited this round, no P2 change touched them. (a) grace-clock precision becomes more urgent now that webhooks flip status automatically — `invoice.payment_failed` writes a billing event that the grace job keys off, so Stripe-driven flips are now the common case the P1 note warned about |

## New design deviations found (P2)

| ID | Deviation | Severity | Disposition |
|---|---|---|---|
| D13 | **Observatory divergence flagging missing.** §10 P2 b5 asks the reconciliation view to "flag divergence (BA plan ≠ Stripe subscription state)". The view lists local `billing_accounts` rows only; there is no Stripe-side fetch and not even a local heuristic (e.g. `plan_code='free'` while `provider_subscription_id` is set — a state the deletion handler makes impossible in normal flow but manual admin PATCHes can produce). Tested contract (mapping only) was deliberately narrower because CI has no network. | **Low-medium** — this is the §11 rollback/re-enable reconciliation tool; without divergence marking, ops diff by eye | Add a local heuristic column now (cheap); add an optional live-Stripe comparison (button/CLI, not page-load) before the first real rollback drill |
| D14 | **Webhook body cap applied after full buffering.** `routes_stripe_webhook.py:19` does `await request.body()` before the service's 1 MiB check, so an attacker can still make the process buffer an arbitrarily large body in memory; the contract's "before verification work" holds (cap precedes HMAC) but the DoS-hardening intent is only half-met. Uvicorn does not cap request bodies by default. | **Low** (endpoint is unauthenticated but Caddy fronts prod and can cap `request_body`) | Enforce a streaming/Content-Length cap at the route or document the reverse-proxy cap as the real control in the deploy templates |
| D15 | **Duplicate detection by exception-string matching.** `_insert_event_row` classifies any exception whose name/message contains "unique"/"integrity"/"duplicate" as a replay (`stripe_billing_service.py:140-152`). A non-uniqueness `IntegrityError` (e.g. NOT NULL/FK violation from a future schema change) would be silently swallowed as `{"duplicate": true}` — event acknowledged 2xx, handler never runs, Stripe never retries. | **Low-medium** (latent; today the only integrity constraint on that INSERT is the intended unique index) | Narrow to a `SELECT`-after-catch confirming the event id exists, or match on the specific constraint name |
| D16 | **No server-side guard against double subscription.** `POST /ui/billing/upgrade` creates a Checkout Session regardless of current plan/status; only the UI hides the form for paid users (`routes_billing.py:98-100`). A paid user re-POSTing (stale tab, scripted) gets a second live Stripe subscription on completion; the webhook then just overwrites `provider_subscription_id`, orphaning the first subscription (still billing at Stripe, invisible locally). | **Medium-low** — real-money duplicate charge path, though it requires completing Checkout twice | Before ma3.io rollout: 409/redirect-to-portal when the BA already has an active `provider_subscription_id`; Stripe-side `customer` is already passed when linked, so Portal is the correct upgrade path for existing subscribers |
| D17 | **Invoice-event field pinned to legacy Stripe API shape.** Handlers resolve via top-level `data.object.subscription` (`stripe_billing_service.py:203, 254`). Recent Stripe API versions (2025+ "basil" line) removed `invoice.subscription` in favor of `parent.subscription_details.subscription`; the fake-SDK fixtures use the legacy shape, so tests cannot catch this. If the live webhook endpoint is created on a new default API version, `invoice.payment_failed`/`invoice.paid` become silent no-ops (BA never enters/leaves `past_due`). | **Medium** for production correctness, invisible in CI by design | Ops step for §11 rollout: pin the webhook endpoint's API version to one that carries `invoice.subscription`, or read both shapes in `_handle_invoice`. Verify once against Stripe test mode on staging (already the planned §11 step) |

No critical bugs. Nothing here makes acceptance impossible; no product code was changed
during acceptance.

## Notes for rollout / P3

1. **D17 first**: when creating the real webhook endpoint in the Stripe dashboard, pin the
   API version (or make `_handle_invoice` shape-tolerant) and run one live test-mode
   payment on staging — this is the single P2 risk the no-network test suite structurally
   cannot see.
2. **D16 before real money**: block/redirect upgrade POSTs for already-subscribed BAs;
   the Customer Portal (already shipped) is the intended change-plan path.
3. **D9 remainder is now user-visible**: with `invoice.payment_failed` auto-flipping BAs
   to `past_due`, the promised T-7/T-1/T-0 grace mail must exist before the 30-day revoke
   job fires on a paying-but-card-expired customer. Wire a transport to the already-logged
   notifications.
4. **D13**: add the cheap local divergence heuristic to the Observatory table now; a live
   Stripe comparison can wait for the first rollback drill.
5. **D2/D11/D12 carry-overs** remain scheduled work, unaffected by (and not masked any
   further by) the Stripe phase; D12(a) grace-clock precision graduates from "rare" to
   "common case" once webhooks drive status flips — add `past_due_since` alongside D9's
   mailer work.
6. The scenario doc's pre-implementation baseline (4P/2S) can be refreshed to green
   (26/26); scenario IDs and contract text unchanged during acceptance.
