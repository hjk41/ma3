# 27 — Org Billing P2 (Stripe): Executable Test Scenarios (Fable, tests-first)

> Status: **tests written before product code** (marker `billing_p2`).
> Companion to `27-org-billing-implementation-fable.md` (the ratified design;
> §2 P2, §7 org upgrade path, §8.3/8.4, §9 Decisions 1–2, §10 P2, §12 threat
> table, §13 `test_stripe_webhook.py`) and to the P0/P1 twins
> (`billing_p0` / `billing_p1`). Composer implements against the contract in
> `code/server/tests/helpers/billing_p2.py` (single source of expected symbols).

## How to run

```bash
cd code/server
source ../../.venv/bin/activate
python -m pytest -m billing_p2 -q          # P2 acceptance only
python -m pytest -m "not billing_p2" -q    # everything else must stay green
```

Pre-implementation state: the webhook unit module and the checkout-UI
integration module **skip** (`importorskip` on
`app.services.stripe_billing_service`); the provider=none integration module
**passes already** — those tests are the standing self-host guard (routes 404
today because they do not exist; they must KEEP answering 404 per request once
they do). After Composer lands P2, every test must pass — no test may stay
skipped.

Verified pre-implementation baseline (2026-08-10, P0+P1 landed):
see the bottom of this doc.

## Contract Composer must implement (summary; authoritative docstring in helpers)

| Symbol | Kind | Key semantics |
|---|---|---|
| `app.services.stripe_billing_service.create_checkout_session(ba_id, plan_code=, success_url=, cancel_url=)` | fn | returns `{"id","url"}`; `stripe.checkout.Session.create` with `mode="subscription"`, `client_reference_id=ba_id`, `metadata={billing_account_id, plan_code}`, price = `settings.stripe_price_pro`/`stripe_price_team` (Decision 1: env Price IDs, never hardcoded amounts) |
| `stripe_billing_service.create_portal_session(ba_id, return_url=)` | fn | returns `{"url"}` via `stripe.billing_portal.Session.create(customer=<provider_customer_id>)`; unlinked BA → 4xx, no Stripe call |
| `stripe_billing_service.handle_webhook_event(payload: bytes, sig_header: str)` | fn | verify via `stripe.Webhook.construct_event` (300s tolerance); failure → `HTTPException(400)`, no row, no state change; insert-first idempotency on `billing_events(provider='stripe', provider_event_id)`; event read with mapping-style access |
| checkout.session.completed handler | behavior | BA from `metadata.billing_account_id`; plan from `metadata.plan_code`; status `active`; persist `provider/provider_customer_id/provider_subscription_id` |
| invoice.payment_failed / invoice.paid handlers | behavior | resolve BA via `provider_subscription_id` → status `past_due` / `active` |
| customer.subscription.deleted handler | behavior | resolve via subscription id → plan `free` (event fires at period end), status not past_due, **clear** `provider_subscription_id` (makes late out-of-order invoice events no-ops, §12 compare-and-set); records untouched |
| unknown event types | behavior | acknowledged, no exception, no state change |
| `Settings.stripe_secret_key` (`MA3_STRIPE_SECRET_KEY`) | config | test fixture `sk_test_fake` |
| `Settings.stripe_webhook_secret` (`MA3_STRIPE_WEBHOOK_SECRET`) | config | test fixture `whsec_test_fake` |
| `Settings.stripe_price_pro` / `stripe_price_team` (`MA3_STRIPE_PRICE_PRO/TEAM`) | config | test fixtures `price_test_pro` / `price_test_team` |
| `POST /ui/billing/upgrade` | route | session + same-origin (§12 CSRF); 30x → Checkout url |
| `POST /ui/orgs/{org_id}/billing/upgrade` | route | org ADMIN only (member → 404); Team price on the ORG BA |
| `GET /ui/billing/portal` | route | 30x → Customer Portal url; unlinked BA → 4xx |
| `POST /webhooks/stripe` | route | no session/key auth, only `Stripe-Signature`; body-size cap (>1 MiB → 400/413); 2xx on success AND duplicate; 400 on bad sig |
| provider gating | behavior | evaluated **per request** against `settings.billing_provider`; `none` → all four routes 404 **and** stripe SDK never imported (lazy import inside the stripe path only) |
| `/ui/billing/` CTA | UI | provider=stripe + free plan: form with `action="/ui/billing/upgrade"`; provider=none: P1 page unchanged (coming_soon, no form, no stripe.com link) |
| success URL | UI | `{public_base_url}/ui/billing/?checkout=success` renders "pending" only; visiting it never changes the plan (webhook is the sole plan writer) |
| Observatory reconciliation | UI | `/ui/observatory/billing/` surfaces `provider_subscription_id` ↔ BA mapping |

No new tables: P0's `billing_accounts.provider*` columns and
`billing_events(provider, provider_event_id)` partial UNIQUE index are reused.

## Scenario map

### `tests/unit/test_billing_p2_webhook.py` (skips until `stripe_billing_service`)

Signature fixtures are real: the helper signs payloads with Stripe's v1 scheme
(`t=<unix>,v1=HMAC_SHA256(whsec, f"{t}.{body}")`) and a faithful fake
`stripe.Webhook.construct_event` (same scheme, same 300s tolerance) is
installed in `sys.modules` — no network, no real SDK needed.

| ID | Scenario | Design ref |
|---|---|---|
| BP2-W1 | Correct payload signed with the wrong secret → 400, no `billing_events` row, no state change | §10 P2 b3 |
| BP2-W2 | Missing / garbage `Stripe-Signature` header → 400 | §12 |
| BP2-W3 | Valid HMAC but timestamp 6 min old → 400 (reject stale >5 min) | §12 |
| BP2-W4 | `checkout.session.completed` → personal BA free→pro active; provider customer/subscription persisted; one `billing_events` row | §10 P2 b2 |
| BP2-W4b | Team checkout on an org BA → plan `team` active | §7 |
| BP2-W5 | Same `provider_event_id` delivered twice mutates state ONCE (state forced divergent between deliveries; replay must not re-apply) | §10 P2 b2 |
| BP2-W6 | `invoice.payment_failed` (resolved via subscription id) → `past_due` | §10 P2 b4 |
| BP2-W7 | `invoice.paid` → back to `active` | §10 P2 b4 |
| BP2-W8 | `customer.subscription.deleted` → plan `free`, subscription link cleared, status not past_due | §10 P2 b4 |
| BP2-W9 | Out-of-order: late `invoice.paid` (fresh event id) for a deleted subscription → no-op, plan stays free | §12 compare-and-set |
| BP2-W10 | Unknown event type (`charge.succeeded`) → no exception, no state change | §8.4 |

### `tests/integration/test_billing_p2_provider_none.py` (PASSES pre-impl; standing guard)

| ID | Scenario | Design ref |
|---|---|---|
| BP2-N1 | provider=none: `POST /ui/billing/upgrade`, `GET /ui/billing/portal`, `POST /ui/orgs/{id}/billing/upgrade` all 404 (even for session/org-admin actors) | §10 P2 b1 |
| BP2-N2 | provider=none: correctly signed `POST /webhooks/stripe` → 404, no `billing_events` row, no plan change | §8.4 |
| BP2-N3 | After purging `stripe*` from `sys.modules` and exercising the billing page + all four P2 routes: no stripe module imported | §10 P2 b1, §14 drift risk |
| BP2-N4 | Billing page keeps its P1 shape: coming_soon copy present, no upgrade form, no stripe.com link (BP1-P6 regression) | §7, Decision 7 |

### `tests/integration/test_billing_p2_checkout_ui.py` (skips until `stripe_billing_service`)

| ID | Scenario | Design ref |
|---|---|---|
| BP2-C1 | provider=stripe + free session user: `/ui/billing/` renders a form with `action="/ui/billing/upgrade"` | §7 |
| BP2-C2 | `POST /ui/billing/upgrade` → 30x to `https://checkout.stripe.com/...`; recorded call: mode=subscription, `client_reference_id`=BA, metadata `{billing_account_id, plan_code=pro}`, price `price_test_pro` | §2 P2, Decision 1 |
| BP2-C2b | Cross-origin POST rejected; no Checkout Session created | §12 CSRF |
| BP2-C3 | Visiting `/ui/billing/?checkout=success` after an upgrade POST → 200 pending page, plan stays `free` in DB | §12, §10 P2 b2 |
| BP2-C4 | Route-level webhook: signed checkout event → 2xx + plan pro; duplicate delivery → 2xx, single `billing_events` row | §10 P2 b2 |
| BP2-C4b | Bad signature at the route → 400, no trace | §10 P2 b3 |
| BP2-C4c | 2 MiB signed body → 400/413 (body-size cap), no trace | §8.4 |
| BP2-C5 | Portal: unlinked BA → 4xx (no Stripe call); after linking `provider_customer_id` → 30x to `https://billing.stripe.com/...` with `customer=cus_...` | §2 P2 |
| BP2-C6 | Org admin `POST /ui/orgs/{id}/billing/upgrade` → Checkout with `price_test_team` on the ORG BA; plan_code metadata `team` | §7 |
| BP2-C6b | Non-admin member → 404, no Checkout Session | existing org-page convention |
| BP2-C7 | Observatory smoke: `/ui/observatory/billing/` shows a linked BA's `provider_subscription_id` | §2 P2 last row |

## Deliberate scope notes

- **No real Stripe SDK, no network** (§13: "Stripe tests use a fixture signing
  secret, no network"). The helper installs a fake `stripe` module whose
  `Webhook.construct_event` re-implements the official v1 verification exactly;
  Checkout/Portal `Session.create` are recorded and return canned urls. This
  forces two implementation properties: stripe is imported **lazily** (so the
  per-test `sys.modules` substitution — and the provider=none no-import rule —
  hold), and events are read with **mapping-style access** (real
  `StripeObject` supports it too).
- **Fixture credentials only**: `sk_test_fake` / `whsec_test_fake` /
  `price_test_pro` / `price_test_team`. Never real secrets in the repo.
- **Per-request provider gating**: "mounted only when provider=stripe" (§8.4)
  is encoded as its observable behavior — 404 under `provider=none` on the
  live app — because tests (and the §11 rollback story: flip env back to
  `none`, routes 404, no deploy) monkeypatch settings without rebuilding the
  app.
- **"Free at period end"** (§2 P2 downgrade row) is encoded as: the
  `customer.subscription.deleted` handler flips the plan when the event
  arrives — Stripe fires it at period end, so no scheduler is required. The
  grace/revoke machinery itself is P1-tested (`billing_p1` grace suite).
- **Out-of-order strategy pinned loosely**: the contract requires clearing
  `provider_subscription_id` on deletion, which makes stale invoice events
  unresolvable — the simplest §12-compliant compare-and-set. Stronger
  snapshot-compare implementations also pass BP2-W9.
- **Not covered here**: Alipay/WeChat Pay (Decision 2: cards+Link first,
  fast-follow), seat-quantity self-serve / proration (P3), dunning email
  content, real Stripe test-mode integration against staging (§11 rollout is
  an ops step, not a CI test).

## Pre-implementation baseline (2026-08-10)

```
python -m pytest -m billing_p2 -q --tb=line
```

**4 passed, 2 skipped** — the 4 passes are the provider=none self-host guard
(BP2-N1..N4, meaningful today: routes absent → 404, no stripe import); the 2
skips are the whole webhook unit module (11 tests) and the whole checkout-UI
module (10 tests), each gated at collection by
`importorskip("app.services.stripe_billing_service")` with a
"P2 not implemented yet" reason. The rest of the suite stays green
(`-m "not billing_p0 and not billing_p1 and not billing_p2"` within the
default addopts selection).
