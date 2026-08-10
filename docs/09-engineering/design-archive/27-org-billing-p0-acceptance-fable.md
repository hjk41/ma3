# 27 — Org+Billing P0: Acceptance Report (Fable)

> Date: 2026-08-10. Acceptor: Fable (test author). Implementer: Composer.
> Basis: `27-org-billing-implementation-fable.md` §10 P0 + §0.1 amendments + Decision 5a=A,
> scenario map `27-org-billing-p0-test-scenarios-fable.md`. Archive doc, no zh twin needed.

## Verdict: **PASS-with-notes**

All 6 §10 P0 acceptance bullets pass; the full P0 test set (38 tests) and the whole
regression suite (427 tests) are green with zero product-code changes during acceptance.
Two genuine design deviations were found (D1, D2 below); neither breaks a P0 bullet, but
both are prerequisites for P1 metering/overrides and must be scheduled there.

## Test results

Environment: `./.venv` Python 3.12, SQLite, `cd code/server`.

| Run | Result |
|---|---|
| `python -m pytest -m billing_p0 -q --tb=short` | **38 passed**, 416 deselected, 35.5s |
| `python -m pytest -q -m "not deploy and not postgres and not docker and not e2e" --tb=line` | **427 passed**, 27 deselected, 156s |

Per-file (all pass): `unit/test_billing_p0_service.py` 9, `integration/test_billing_p0_migration.py` 6,
`integration/test_billing_p0_seat_enforcement.py` 9, `integration/test_billing_p0_admin_api.py` 10,
`integration/test_billing_p0_mcp_selfhost.py` 4.

Pre-implementation state was 20 FAIL / 3 SKIP / 2 PASS — every red scenario turned green,
both regression guards (BP0-S9, BP0-A8) still hold.

## §10 P0 checklist

| # | §10 P0 bullet | Status | Evidence |
|---|---|---|---|
| 1 | Fresh DB: first login creates personal org + BA (plan=free); migration repeatable; every org `billing_account_id` a real `ba_*` FK; zero `plan:` labels remain | **PASS** | BP0-U2, BP0-G1–G6; `onboarding_service.ensure_personal_org` → `ensure_org_billing_account(plan_code=free/pro)`; `run_billing_backfill()` runs on every `initialize_database` (idempotent, `db.py:606`). Caveat: see D3 (`set_user_paid` temporarily re-writes a `plan:` label; self-repairing) |
| 2 | `PATCH /api/admin/billing-accounts/{ba_id}` flips `is_paid_principal`, RO-key eligibility, library limits, `principals.plan_code` projection; existing quota tests pass unmodified | **PASS** | BP0-A1–A9; `billing_service.set_billing_account_plan` write-through projection (`billing_service.py:137-140`); pre-existing quota tests in full suite green unmodified |
| 3 | `team_stub` at 3 seats (incl. pending-invite reservations): invite create 403, redeem-at-cap 403, personal-org member-add 403, last-admin protection unaffected | **PASS** | BP0-S1–S9, BP0-U5/U6, BP0-G4; atomic `admit_org_member` (Postgres `pg_advisory_xact_lock` / SQLite `BEGIN IMMEDIATE`); invite create reserves capacity and clamps `max_uses` to remaining seats (`org_invite_service.py:107-121`); race test S8 proves no oversell; `create_team_org` seeds `team_stub`, backfill maps `plan:pro` **and** `plan:admin` team orgs → `team_stub`, never full `team` (Decision 5a=A honored) |
| 4 | `MA3_PAID_PRINCIPAL_IDS` env allowlist still overrides to Pro | **PASS** | BP0-A8 (guard), BP0-U3; precedence env > override > plan in `effective_quota` |
| 5 | `ma3_whoami` returns plan, seats, library and storage quota summary | **PASS** | BP0-M1; `plan = {plan_code, status, seats, libraries, storage}` block (`mcp_tool_service.py:416-425`); shipped `storage_quota` block preserved |
| 6 | Self-host bootstrap gets working default BA; `ma3_doctor` reports `billing_schema_ok` | **PASS** | BP0-M2/M3; doctor checks all 4 billing tables on both SQLite and Postgres; no `stripe` import anywhere in `app/` (only doc-string mentions in `billing_ops_service`); no `/webhooks/stripe` route |

Spot-checked implementation surface (read, not re-implemented): `app/services/billing_service.py`
(full contract from the scenario doc: `run_billing_backfill`, `get_billing_account[_for_org]`,
`effective_plan`, `effective_quota`, `set_billing_account_plan`, `set/clear_quota_override`,
`seat_usage`, `admit_org_member`), `app/storage/db.py` (plans seeded free/pro/team_stub/team with
exact §9.1 numbers — seats 1/1/3/5, libs 1/5/3/10, `team_stub` 1 GB/50k reads/25 keys/120 rpm;
`billing_accounts` with `UNIQUE(owner_type, owner_id)`; `quota_overrides`; `billing_events`;
`api_keys.billing_account_id` nullable column), `app/api/routes_admin_api.py` (GET/PATCH BA,
PUT/DELETE overrides, product-admin gated, legacy `PATCH /users/{pid}/plan` alias writes through
to the BA), `org_service.py` (direct add routes through `admit_org_member`), `org_invite_service.py`
(create = advisory check + reservation; redeem = authoritative via `admit_org_member`). Seat error
contract matches the pinned shape `403 {"error": "seat_limit_exceeded", used, included_seats,
upgrade_url}`; `upgrade_url` is `null` per Decision 7 (no SaaS funnel before Checkout).

## Design deviations found

| ID | Deviation | Severity | Disposition |
|---|---|---|---|
| D1 | **`ResolvedApiKey` does not propagate `billing_account_id`** (`api_key_service.py:32-38`). §0.1(3) explicitly puts "propagation through `ResolvedApiKey`" in P0. Column, deterministic backfill (BP0-G5) and create-key plumbing all exist; only the resolved-auth dataclass lacks the field. | **Medium** — no P0 behavior depends on it (no test asserted it), but §0.1(3)'s "metering must never start on keys without a verified BA" makes it a hard prerequisite for P1 metering. | Accept P0; **must land at the very start of P1**, before any `usage_*` counter work. |
| D2 | **Quota services not rewired onto `billing_service`.** `library_quota_service`, `org_quota_service`, `storage_quota_service` still resolve paid status via `onboarding_service.is_paid_principal` → `principals.plan_code` projection, not `effective_quota`. Design P0 table row said "rewire … to resolve via billing_service". Because the projection is write-through, plan flips propagate correctly (bullet 2 passes), but **`quota_overrides` have no effect on library-count / storage / team-org-gate decisions**. | **Medium-low** — functionally equivalent for everything P0 tests; overrides only bite in P1 (admin override of `max_libraries` / storage for a single BA silently won't apply through these services). | Accept P0 (write-through projection is a defensible reading); rewire during P1 enforcement work, covered by the planned `test_billing_enforcement.py`. |
| D3 | **`set_user_paid` re-writes the legacy `plan:{code}` label** onto `organizations.billing_account_id` after updating the BA (`onboarding_service.py:58`, deliberate compat for older Observatory callers). Until the next startup backfill repairs it, `get_billing_account_for_org` returns `None` for that personal org (whoami `plan` block absent, `seat_usage` falls back to `included_seats=1` — harmless for personal orgs, hard-1 anyway). Strictly this violates the "zero `plan:` labels remain" invariant between an Observatory plan flip and the next restart. | **Low** — self-repairing, personal-org-only, BA stays authoritative. | Note for P1: drop the label re-write once Observatory reads BAs directly. |
| D4 | `effective_quota` interpolates `quota_key` into an SQL f-string in the env-allowlist branch (`billing_service.py:67`). All current callers pass literals ("max_libraries" etc.), and the admin overrides route stores keys parameterized, so no untrusted input reaches it today. | **Low** (hygiene) | Whitelist `quota_key` against plan columns in P1, when the key set grows. |
| D5 | `run_billing_backfill` re-derives the personal-org id inline (`"org_personal_" + sha256(...)[:12]` with `__import__("hashlib")`) instead of importing `onboarding_service.personal_org_id`. Values match; duplication only. | **Cosmetic** | Fold into any P1 touch of the backfill. |

No critical bugs. Nothing here makes acceptance impossible; no product code was changed during
acceptance.

## Notes for P1

1. **D1 first**: add `billing_account_id` to `ResolvedApiKey` (+ require BA choice on new key
   creation per §8) before any read-unit counter increments — this is the §0.1(3) gate.
2. **D2**: rewire the three quota services onto `effective_quota` so `quota_overrides` become
   effective; the §6 matrix tests (`test_billing_enforcement.py`) should assert override paths.
3. Scenario-doc ambiguity resolutions held: `seat_limit_exceeded` for seat admission,
   `team_upgrade_required` remains free for the stub's library/storage/read caps in P1.
4. `admit_org_member`'s invite branch admits over-cap only when the redeemer's reservation is
   already counted (`used > included_seats` check) — P1 grandfathering work should keep that
   invariant when it adds Decision-4 library/storage grandfathering.
5. Self-host defaults (§0.1(6)) untested beyond schema/bootstrap because the read-quota
   enforcer and rate limiter do not exist yet — P1 must add the `MA3_READ_QUOTA_ENFORCE=0` /
   `MA3_RATE_LIMIT_ENABLED=0` default-off tests together with the features.
6. The scenario doc's status header was refreshed to green (38/38) as part of this acceptance;
   scenario IDs and contract text are unchanged.
