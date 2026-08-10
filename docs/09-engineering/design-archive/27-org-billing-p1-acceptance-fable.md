# 27 — Org+Billing P1: Acceptance Report (Fable)

> Date: 2026-08-10. Acceptor: Fable (test author). Implementer: Composer.
> Basis: `27-org-billing-implementation-fable.md` §2 P1 + §0.1 amendments 4/6/7 + §6 + §8
> + §9 Decisions 7/8 + §10 P1, scenario map `27-org-billing-p1-test-scenarios-fable.md`,
> contract `code/server/tests/helpers/billing_p1.py`. Archive doc, no zh twin needed.
> P0 twin: `27-org-billing-p0-acceptance-fable.md`.

## Verdict: **PASS-with-notes**

All 8 §10 P1 acceptance bullets pass; the full P1 test set (63 tests, zero skips — the
scenario doc's "no test may stay skipped" rule holds) and the whole regression suite
(490 tests) are green with zero product-code changes during acceptance. Of the P0
carried deviations, **D1 is resolved** and **D2 is still open** (partially mitigated).
Seven new deviations were found (D6–D12 below); none breaks a P1 bullet, but D6 (dead
duplicate route module), D9 (no scheduler/email wiring) and D11 (no membership re-check
at metering time) should be scheduled for P2.

## Test results

Environment: `./.venv` Python 3.12, SQLite, `cd code/server`.

| Run | Result |
|---|---|
| `python -m pytest -m billing_p1 -q --tb=short` | **63 passed**, 454 deselected, 37.4s |
| `python -m pytest -q -m "not deploy and not postgres and not docker and not e2e" --tb=line` | **490 passed**, 27 deselected, 196.5s |

Per-file (all pass): `unit/test_billing_p1_usage_metering.py` 21,
`unit/test_billing_p1_rate_limiter.py` 5, `unit/test_billing_p1_past_due_grace.py` 8,
`integration/test_billing_p1_enforcement.py` 15, `integration/test_billing_p1_portal.py` 8,
`integration/test_billing_p1_key_billing.py` 6.

Pre-implementation baseline (scenario doc, 2026-08-10) was 12 FAIL / 1 PASS / 5 SKIP —
every red scenario turned green, every `importorskip` module now imports, and the P0
regression guard BP1-K5 still holds.

## §10 P1 checklist

| # | §10 P1 bullet | Status | Evidence |
|---|---|---|---|
| 1 | 10 successful `ma3_context` → `usage_monthly.read_units == 10` for the key's BA; `ma3_report`/`ma3_feedback`/`ma3_validate` bill zero; 4xx not counted | **PASS** | BP1-E1, BP1-U1–U6. `usage_service.record_read_usage` is the synchronous durable counter (§0.1(4)): atomic upsert into `usage_monthly` before the response returns; returns 0 for non-billable tools / non-2xx (`usage_service.py:28-45`); `BILLABLE_READ_TOOLS = {"ma3_context","ma3_case"}` only; `ma3_case` raises 404 *before* the billing line, so failed reads bill 0 (`mcp_tool_service.py:507-529`) |
| 2 | Free BA at cap: next read → 429 + `Retry-After`; writes still succeed | **PASS** | BP1-E2/E3. `_assert_billing_read_allowed` → 429 `read_quota_exceeded` + `Retry-After` only when `MA3_READ_QUOTA_ENFORCE=1` (`mcp_tool_service.py:357-367`); default-off observe mode fills the same counters (BP1-E2) per Decision 7 / §0.1(6); `ma3_report` unaffected (contribution-first) |
| 3 | ≥80% of read/storage quota → `structuredContent.quota.warnings` | **PASS** | BP1-E4, BP1-U7. `read_quota_state` flips `warn` at `used >= 0.8*limit` (`usage_service.py:55-59`); `_quota_warning` attaches `{read_units, warnings[]}` to every `ma3_context`/`ma3_case` data response (`mcp_tool_service.py:346-354, 497, 530`); org-pool soft-overflow warning at `mcp_tool_service.py:822` |
| 4 | Org write over pooled Team bytes → 403, reads unaffected; `libraries.storage_bytes` == `sum_library_record_content_bytes` | **PASS** | BP1-E5/E6/E7. `ma3_report` to an org library projects `sum_org_storage_bytes + new bytes` against `effective_quota(ba, "storage_bytes_total")`; 403 `org_storage_quota_exceeded` only when `MA3_ORG_STORAGE_QUOTA_ENFORCE=1` (`mcp_tool_service.py:717-723`), soft-warn otherwise (Decision 7); counters maintained on insert/status change (`db.py:1203-1220`) and backfilled at startup with the same statuses+formula as `sum_library_record_content_bytes` (`db.py:478-497` vs `db.py:1636`) |
| 5 | past_due: `ma3_report` 403, invite 403, `ma3_context` fine; +30d grace revokes private/org RO grants (never RO→RW); `lib_default` untouched; banner during grace; T-7/T-1/T-0 notifications via job harness | **PASS** | BP1-E8, BP1-G1–G5, BP1-P7. Write block at `mcp_tool_service.py:657-663`, invite block at `org_invite_service.py:102-104` (both `billing_past_due`); `billing_grace_service.run_past_due_grace_job` revokes reader-role key/library grants on private+org libraries only, skips `lib_default`, is idempotent, and reactivation cancels (status filter); notifications deduped by PK on `billing_grace_notifications` (`db.py:415-422`); `id="past-due-banner"` on both billing pages. Email transport is deliberately out of test scope (scenario doc) — but see D9 |
| 6 | `/ui/billing/` + `/ui/orgs/{id}/billing/` render for the right actors (member → 404), i18n zh/en complete, meters accurate against `usage_monthly` | **PASS-with-notes** | BP1-P1–P5. Live handlers: `routes_portal.py:55`, `routes_org_portal.py:56` (admin-only, member/outsider → 404), `routes_me_api.py:69`, `routes_orgs_api.py:162` (member → 404); reads meter equals the `usage_monthly` counter (BP1-P2); `billing.*` key sets identical and non-empty in zh-CN/en-US (`app/api/i18n/*.json:349-354`). Notes: page body copy is hardcoded English and the i18n keys are only consumed by a dead module — see D6/D7 |
| 7 | New key creation requires a billing context; non-member picking a team org → 403 | **PASS-with-notes** | BP1-K1–K5. `POST /api/keys`: missing `billing_org_id` → 400 `billing_context_required`; non-member / inactive / ex-member → 403 `billing_context_forbidden`, no org-billed row created; chosen org's BA written to `api_keys.billing_account_id` and echoed in the response (`routes_keys.py:502-553`). Note: the 400 fires only for callers with ≥1 active team membership — see D8 |
| 8 | `test_billing_enforcement.py` covers the whole §6 matrix and passes | **PASS** | Shipped as `integration/test_billing_p1_enforcement.py` (15 tests; the P1 rows: read units E1–E4, storage E5–E7, past_due E8, rate limit E9, flags E10). §6 rows owned by P0 (RO keys, library count, seats, team-org creation) stay covered by the green `billing_p0` suite in the same run. Naming difference from §13 is cosmetic |

Spot-checked implementation surface (read, not re-implemented): `app/services/usage_service.py`
(full contract: `read_units` = `max(1, ceil(n/10))`, `BILLABLE_READ_TOOLS`, sync
`record_read_usage`, `monthly_read_units`, `read_quota_state`, `flush_usage_events`,
`rollup_usage_monthly`), `app/services/rate_limit_service.py` (per-key 60s sliding window,
injectable `now`, `retry_after` ∈ (0,60], `reset()` hook), `app/services/billing_grace_service.py`
(GRACE_DAYS=30, Decision 8-A semantics), `app/core/config.py:68-73` (all four flags present with
the §0.1(6) defaults: `billing_provider="none"`, three enforce flags False), `app/storage/db.py`
(`usage_events` + `usage_monthly` with `PRIMARY KEY (billing_account_id, period_start)`,
`billing_grace_notifications`, `plans.rpm` seeded 60/120/120/300 per §9.1, `libraries.
active_record_count`/`storage_bytes` columns + startup backfill), rate limiter wired on
`/mcp` tools/call via `effective_quota(ba, "rpm")` (`mcp_tool_service.py:370-390`), and the
key-creation billing picker (`routes_keys.py`). Error codes match §8.5: `read_quota_exceeded`
and `rate_limited` are 429 with `Retry-After`; `org_storage_quota_exceeded`, `billing_past_due`
403; `billing_context_required` 400.

## P0 deviation follow-up (D1–D5)

| ID | P0 disposition | P1 status |
|---|---|---|
| D1 (`ResolvedApiKey.billing_account_id` missing) | "must land at the very start of P1" | **RESOLVED.** Field exists and is populated from the key row (`api_key_service.py:36, 86-91`); metering resolves the BA from `api_keys.billing_account_id` first, falling back to the caller's personal-org BA (`mcp_tool_service.py:331-343`), so no counter increments without a real BA — the §0.1(3) gate holds |
| D2 (quota services not rewired onto `effective_quota`) | "rewire during P1 enforcement work" | **STILL OPEN.** `library_quota_service`, `org_quota_service`, `storage_quota_service` still resolve via `onboarding_service.is_paid_principal` → `principals.plan_code` projection; `quota_overrides` on `max_libraries` / personal storage / team-org-gate still have no effect. Partially mitigated: every **new** P1 quota key (`read_units_per_month`, `storage_bytes_total`, `rpm`) resolves via `effective_quota`, so overrides work everywhere P1 enforcement bites (BP1-E3/E6/E9 exercise the override path). Carry to P2 |
| D3 (`set_user_paid` re-writes `plan:` label) | note for P1 | **STILL PRESENT** (`onboarding_service.py:55-58`, deliberate compat comment). Same self-repairing, personal-org-only caveat as P0 |
| D4 (`effective_quota` f-string interpolation of `quota_key` in env branch) | whitelist in P1 | **STILL PRESENT** (`billing_service.py:67`). All callers still pass literals (now also `"rpm"`, `"storage_bytes_total"`, `"max_keys"`); still hygiene, not exploitable today |
| D5 (backfill re-derives personal-org id inline) | fold into next touch | **STILL PRESENT** (`billing_service.py:280`, `__import__("hashlib")`); `routes_me_api.py:33` adds a similar inline `__import__` hygiene case |

## New design deviations found (P1)

| ID | Deviation | Severity | Disposition |
|---|---|---|---|
| D6 | **`app/api/routes_billing.py` is dead code.** A complete, i18n-correct implementation of all four billing surfaces (`/api/me/billing`, `/api/orgs/{id}/billing`, `/ui/billing/`, `/ui/orgs/{id}/billing/`) exists in this module but its router is never imported or registered in `main.py`. The live routes are four *separate* hand-rolled handlers in `routes_me_api.py` / `routes_orgs_api.py` / `routes_portal.py` / `routes_org_portal.py`. Two parallel implementations of the same summary logic will drift. | **Medium** (hygiene/drift, no behavior bug) | **RESOLVED (post-acceptance).** `billing_router` registered in `main.py`; the four inline handlers deleted. |
| D7 | **Live billing pages are not localized.** Body copy is hardcoded English (`"Payment is past due."`, `"Checkout coming soon."` — `routes_portal.py:70-73`, `routes_org_portal.py:72-74`); the `billing.*` catalog keys (zh+en, identical sets) are consumed **only** by the dead module from D6. §7/§10-b6 "i18n zh/en complete" is met by the pinned contract (page chrome via `render_page` is localized, catalogs complete, banner id present) but not in spirit for page content. | **Low-medium** | **RESOLVED (with D6).** Live pages now use `billing.*` / `nav.billing` catalogs. |
| D8 | **`billing_org_id` is only conditionally required.** Contract says missing → 400 unconditionally; implementation 400s only when the caller has ≥1 active team membership, else silently defaults to the personal BA (`routes_keys.py:511-520`, explicit compat comment). All tests pass because BP1-K1's fixture has a team org. Defensible (personal-only callers have exactly one possible context; avoids breaking P0 clients), but it diverges from the helper-doc contract text. | **Low** | Either amend the contract docstring to codify the compat rule, or tighten to unconditional 400 in P2 when the picker UI ships |
| D9 | **No scheduler or transport is wired.** `run_past_due_grace_job`, `flush_usage_events` and `rollup_usage_monthly` are never invoked by any app code (no startup task, no cron); grace "notifications" exist only as the job's return value — no email sender. Within the scenario doc's stated scope (transport is Composer's choice, job harness testing), but in production nothing will revoke grants, send T-7/T-1/T-0 mail, or persist the `usage_events` detail buffer (in-process list, lost on restart) until ops wires a scheduler. | **Medium-low** — invisible while Decision 7 keeps SaaS gates soft | **PARTIALLY RESOLVED (post-acceptance).** Lifespan `_billing_maintenance_loop` flushes usage events (`MA3_USAGE_FLUSH_INTERVAL_SEC`, def. 60s) and runs `run_past_due_grace_job` (`MA3_BILLING_GRACE_INTERVAL_SEC`, def. 3600s) via `billing_jobs.run_billing_maintenance_once`; notifications/revokes are **logged** only — real mail transport still P2. |
| D10 | **Rollup is a stub; no `usage_daily`.** `rollup_usage_monthly()` = flush + `{"rolled_up": 0}` (`usage_service.py:71-73`); no `usage_daily` table; no `usage_events` → `usage_monthly` reconciliation. Defensible under §0.1(4) (the sync counter is authoritative, buffer is audit-only, BP1-U6 idempotency holds trivially), but §2 P1 row 1 promised a daily/monthly rollup job and §14 promised reconciliation; `ma3_doctor` also lacks the §8.5 `usage_rollup_lag` field, and `billing_schema_ok` does not cover the two `usage_*` tables. | **Low** | Revisit in P2 when Stripe periods make reconciliation matter; extend doctor then |
| D11 | **No membership re-check at metering time.** §12 pins "membership check at key creation **and** at every metering write (membership revoked → key falls back to owner's personal BA)". Implementation checks membership only at creation; metering reads `api_keys.billing_account_id` as-is (`mcp_tool_service.py:331-336`), so an ex-member's org-billed key keeps debiting the org BA until the key itself is revoked, and no org-admin view of org-billed keys was found. | **Medium-low** — bounded (reads only debit quota, no money in P1; org admins can ask ops to revoke) | P2, together with the org key list §12 promises |
| D12 | **Small enforcement-detail gaps** (grouped): (a) grace clock = latest `admin_plan_change` billing event, so *any* admin plan/status write during grace (even unrelated) restarts the 30-day clock; (b) `Retry-After` for `read_quota_exceeded` is a hardcoded 60s and the 429 detail lacks the `upgrade_url`/quota block §14 asked for; (c) the rate limiter runs per `tools/call`, not on every `/mcp` request (initialize/tools-list uncounted — §6 says "every request"); (d) `/api/me/billing` `keys` meter is a placeholder `{"used": 0}`; (e) `usage_events` 90-day pruning (§12) not implemented; (f) revocation deletes grant rows rather than marking them revoked ("may remain listed as revoked" was optional wording, allowed). | **Low** (each individually cosmetic-to-minor) | Sweep in P2; (a) deserves a dedicated `past_due_since` timestamp when Stripe drives status |

No critical bugs. Nothing here makes acceptance impossible; no product code was changed during
acceptance.

## Notes for P2

1. **D6/D7 first touch**: consolidate on one billing-routes implementation (register
   `routes_billing.py`, delete the four inline handlers) — that fixes the i18n gap for free
   and removes the drift hazard before Checkout adds more billing UI.
2. **D9 is the real gate for flipping Decision 7**: before `MA3_READ_QUOTA_ENFORCE=1` /
   past_due enforcement on ma3.io, wire a scheduler for the grace job + event flush and a
   real mail transport; otherwise revocations and T-7/T-1/T-0 mail silently never happen.
3. **D2 carry-over**: rewire the three legacy quota services onto `effective_quota` so
   `max_libraries`/storage overrides work; the projection write-through still masks this for
   plain plan flips, exactly as in P0.
4. **D11 + org key list** belong to the Stripe phase (§12 spoofing row): re-resolve the BA
   (or fall back to personal) on metering writes once membership lapses, and give org admins
   the promised org-billed-key view with revoke.
5. Stripe scope pinned by the P1 tests: `POST /ui/billing/upgrade` currently 404s (BP1-P6
   guards it) — P2 flips that route live behind `MA3_BILLING_PROVIDER=stripe` together with
   `test_stripe_webhook.py` (§13); `plans.rpm`/quota seeds need no further migration.
6. Grace-clock precision (D12a): add `billing_accounts.past_due_since` (or filter grace-start
   events by status transition) before webhooks start flipping status automatically —
   admin-set flips are rare, Stripe-driven ones will not be.
7. The scenario doc's pre-implementation status header (12F/1P/5S) can now be refreshed to
   green (63/63); scenario IDs and contract text unchanged during acceptance.
