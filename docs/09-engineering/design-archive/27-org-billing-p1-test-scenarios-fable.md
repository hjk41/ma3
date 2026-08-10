# 27 — Org Billing P1: Executable Test Scenarios (Fable, tests-first)

> Status: **tests written before product code** (marker `billing_p1`).
> Companion to `27-org-billing-implementation-fable.md` (the ratified design;
> §0.1 amendments 4+6+7, §2 P1, §6, §7, §8, §9 Decisions 7/8, §10 P1, §13)
> and to the P0 twin `27-org-billing-p0-*` suite (`billing_p0`).
> Composer implements against the contract in
> `code/server/tests/helpers/billing_p1.py` (single source of expected symbols).

## How to run

```bash
cd code/server
source ../../.venv/bin/activate
python -m pytest -m billing_p1 -q          # P1 acceptance only
python -m pytest -m "not billing_p1" -q    # everything else must stay green
```

Pre-implementation state: unit modules **skip** (`importorskip` on the new
services); integration tests either skip (metering-dependent) or **fail with
explicit "P1 not implemented yet: …" messages** (missing routes/flags/tables).
After Composer lands P1, every test must pass — no test may stay skipped.

Verified pre-implementation baseline (2026-08-10, P0 landed):
**12 failed / 1 passed / 5 skipped** for `-m billing_p1`. The single pass is
BP1-K5 (registration key → personal BA), a deliberate P0 regression guard.
The 5 skips are the three unit modules plus the two metering-dependent
integration entry points. The rest of the suite
(`-m "not deploy and not postgres and not docker and not e2e and not
billing_p0 and not billing_p1"`) stays green: 389 passed / 4 skipped.

## Contract Composer must implement (summary; authoritative docstring in helpers)

| Symbol | Kind | Key semantics |
|---|---|---|
| `app.services.usage_service.read_units(n)` | fn | `max(1, ceil(n/10))` (ADR-012) |
| `usage_service.record_read_usage(ba, tool_name=, records_returned=, status_code=)` | fn | **synchronous durable** monthly counter (§0.1(4)); returns units; 0 for non-billable tool or non-2xx |
| `usage_service.BILLABLE_READ_TOOLS` | const | `{"ma3_context", "ma3_case"}` only |
| `usage_service.monthly_read_units(ba)` / `read_quota_state(ba)` | fn | state incl. `warn` (≥80%) / `exceeded` |
| `usage_service.flush_usage_events()` / `rollup_usage_monthly()` | fn | async detail buffer → `usage_events`; idempotent rollup |
| tables `usage_events`, `usage_monthly` | schema | via `initialize_database` (inline idempotent pattern) |
| `libraries.active_record_count`, `libraries.storage_bytes` | columns | maintained counters == `sum_library_record_content_bytes` |
| `plans.rpm` seed | schema | free 60 / pro 120 / team_stub 120 / team 300 |
| quota keys `read_units_per_month`, `storage_bytes_total`, `rpm` | convention | resolved via P0 `billing_service.effective_quota` |
| `app.services.rate_limit_service.check_rate_limit(key_id, rpm=, now=)` | fn | sliding 60s window per key; `{"allowed", "retry_after"}`; `reset()` test hook |
| `app.services.billing_grace_service.run_past_due_grace_job(now=)` | fn | Decision 8-A: +30d revoke private/org RO grants; T-7/T-1/T-0 notifications; idempotent; reactivation cancels |
| `Settings.read_quota_enforce` (`MA3_READ_QUOTA_ENFORCE`, def. off) | flag | observe→enforce two-step (§11) |
| `Settings.rate_limit_enabled` (`MA3_RATE_LIMIT_ENABLED`, def. off) | flag | limiter inert by default |
| `Settings.org_storage_quota_enforce` (`MA3_ORG_STORAGE_QUOTA_ENFORCE`, def. off) | flag | Decision 7 soft/hard switch for the org pool |
| `Settings.billing_provider` (`MA3_BILLING_PROVIDER`, def. `"none"`) | flag | self-host parity (§0.1(6)) |
| HTTP 429 + `Retry-After` on `/mcp` | behavior | `read_quota_exceeded` (over cap, enforce on) and `rate_limited` (over rpm, limiter on) |
| `structuredContent.quota` w/ `warnings[]` | behavior | on MCP data responses at ≥80% read/storage or soft-overflow |
| 403 `org_storage_quota_exceeded` / `billing_past_due` | behavior | pool overflow (enforce on) / past_due writes+invites |
| `GET /api/me/billing`, `GET /api/orgs/{id}/billing` | routes | JSON meters; org variant admin-only (member → 404) |
| `GET /ui/billing/`, `GET /ui/orgs/{id}/billing/` | routes | SSR, zh/en, meters; `id="past-due-banner"` during grace; **no** `/ui/billing/upgrade` until P2 |
| i18n `billing.*` keys | catalogs | identical non-empty key set in zh-CN and en-US |
| `POST /api/keys` + required `billing_org_id` | route change | missing → 400 `billing_context_required`; non-member team org → 403; sets `api_keys.billing_account_id` |

## Scenario map

### `tests/unit/test_billing_p1_usage_metering.py` (skips until `usage_service`)

| ID | Scenario | Design ref |
|---|---|---|
| BP1-U1 | Formula `max(1, ceil(n/10))`: 0→1, 1→1, 10→1, 11→2, 25→3, 100→10, 101→11 | §2 P1, ADR-012 |
| BP1-U2 | `ma3_context`/`ma3_case` bill ≥1 unit; `ma3_report`/`ma3_feedback`/`ma3_validate` bill 0 | §10 P1 b1 |
| BP1-U3 | status 400/404/429/500 → 0 units (2xx only) | §2 P1 |
| BP1-U4 | Sync counter visible immediately + durable in `usage_monthly` (no flush needed); observe mode reads the same counters | §0.1(4) |
| BP1-U5 | Async buffer flush lands detail rows in `usage_events` with correct per-tool units | §14 risks |
| BP1-U6 | `rollup_usage_monthly()` twice → identical totals | §13 |
| BP1-U7 | `read_quota_state`: warn flips at 80%, exceeded at cap, remaining 0 | §6 warnings |

### `tests/unit/test_billing_p1_rate_limiter.py` (skips until `rate_limit_service`)

| ID | Scenario | Design ref |
|---|---|---|
| BP1-R1 | rpm=3 → 3 pass, 4th denied with `retry_after` ∈ (0, 60] | §2 P1 |
| BP1-R2 | Windows keyed per api_key_id (other keys unaffected) | §2 P1 |
| BP1-R3 | Injectable `now`: events older than 60s leave the window | §13 |
| BP1-R4 | `plans.rpm` seeded 60/120/120/300 | §3.1(4)+§9.1 |
| BP1-R5 | `Settings.rate_limit_enabled` defaults False (fresh env) | §0.1(6) |

### `tests/unit/test_billing_p1_past_due_grace.py` (skips until `billing_grace_service`)

| ID | Scenario | Design ref |
|---|---|---|
| BP1-G1 | Day 1 of grace: nothing revoked | Decision 8-A |
| BP1-G2 | T-0 (+30d): private-lib RO key grant + RO library grant revoked; **never** escalated to RW; `lib_default` grants untouched; pre-existing RW grants untouched | §0.1(5), Decision 8-A |
| BP1-G3 | Notifications emitted at T-7 / T-1 / T-0; not re-sent on same-day rerun | Decision 8-A |
| BP1-G4 | BA back to `active` before T-0 → revoke cancelled | Decision 8-A |
| BP1-G5 | Second run after revoke → revokes nothing new (idempotent) | §13 |

### `tests/integration/test_billing_p1_enforcement.py` (§6 matrix end-to-end; skips until `usage_service`)

| ID | Scenario | Design ref |
|---|---|---|
| BP1-E1 | 10 successful `ma3_context` → `usage_monthly.read_units == 10` for the key's BA; write tools bill 0; failed `ma3_case` bills 0; successful `ma3_case` bills by formula | §10 P1 b1 |
| BP1-E2 | Observe default (`MA3_READ_QUOTA_ENFORCE=0`): 5 reads over a cap of 3 all return 200; counter still reaches 5 | Decision 7, §0.1(4)(6) |
| BP1-E3 | Enforce on: over cap → HTTP 429 + `Retry-After` + `read_quota_exceeded`; `ma3_report` still succeeds | §10 P1 b2 |
| BP1-E4 | ≥80% of read quota → `structuredContent.quota.warnings` non-empty | §10 P1 b3 |
| BP1-E5 | Org pool soft mode (flag off, default): over-pool write succeeds **with** warning | Decision 7 |
| BP1-E6 | Org pool enforce on: over-pool write → `org_storage_quota_exceeded`; reads on the library unaffected | §6 storage row |
| BP1-E7 | `libraries.storage_bytes`/`active_record_count` == `sum_library_record_content_bytes` | §10 P1 b4 |
| BP1-E8 | past_due personal BA: `ma3_report` → `billing_past_due`; `ma3_context` still fine. past_due org BA: invite create → 403 | §10 P1 b5 |
| BP1-E9 | Limiter enabled + rpm override 3 → 4th `/mcp` request 429 + `Retry-After` + `rate_limited`; flag off (default) → inert | §2 P1 |
| BP1-E10 | Fresh `Settings()` with clean env: provider `none`, all three enforce flags False | §0.1(6) |

### `tests/integration/test_billing_p1_portal.py`

| ID | Scenario | Design ref |
|---|---|---|
| BP1-P1 | `/ui/billing/` renders 200 for a session user in zh-CN and en-US; anonymous does not render | §7 |
| BP1-P2 | `/api/me/billing` shape (plan/status/read_units/storage/seats); reads meter equals `usage_monthly` | §8.2, §10 P1 b6 |
| BP1-P3 | `/ui/orgs/{id}/billing/`: org admin 200; non-admin member 404; outsider 404 | §10 P1 b6 |
| BP1-P4 | `/api/orgs/{id}/billing`: admin 200 (`team_stub`); member 404 | §8.2 |
| BP1-P5 | `billing.*` i18n keys: identical non-empty sets in zh-CN / en-US | §7 |
| BP1-P6 | No Stripe link, no `/ui/billing/upgrade` link, POST `/ui/billing/upgrade` → 404 (Checkout CTA hidden/disabled until P2) | Decision 7 |
| BP1-P7 | `id="past-due-banner"` on personal + org billing pages while `past_due` | Decision 8-A |

### `tests/integration/test_billing_p1_key_billing.py`

| ID | Scenario | Design ref |
|---|---|---|
| BP1-K1 | `POST /api/keys` without `billing_org_id` → 400 `billing_context_required` | §8.2/§8.5 |
| BP1-K2 | Personal org context → key's `billing_account_id` = personal BA | §2 P1 r2 |
| BP1-K3 | Team org context (active member) → org BA; ex-member (removed) → 403 | §12 spoofing |
| BP1-K4 | Non-member picking a team org → 403; no org-billed key row created | §10 P1 b7 |
| BP1-K5 | Registration bootstrap key defaults to personal BA (P0 regression guard) | §0.1(3) |

## Deliberate scope notes

- **Decision 7 encoding**: read-429 and org-pool-403 are tested **behind flags**
  that default off; past_due write/invite blocks are tested as hard (admin-set
  `past_due` is a deliberate operator action in P1, per §10 P1 acceptance
  wording). Flipping SaaS gates on is compose config, not code.
- **T-7/T-1/T-0 email**: unit-tested via the job harness return value
  (`notifications` list), not via an SMTP fake — transport is Composer's choice.
- **Banner/CTA markers**: the only HTML contracts pinned are
  `id="past-due-banner"` and the absence of upgrade/Stripe links; all other
  page content is asserted through i18n catalogs and JSON APIs to avoid
  over-coupling to markup.
- **Not covered here (P2)**: Stripe checkout/webhooks/portal
  (`test_stripe_webhook.py` per §13), provider=stripe routing.
