# 27 — Org+Billing P0: Executable Test Scenarios (Fable)

> Status: **all green 2026-08-10** — P0 implemented (Composer) and accepted (Fable), see
> `27-org-billing-p0-acceptance-fable.md`. Historical "red by design" notes below kept for the record.
> Source of truth: `27-org-billing-implementation-fable.md` (§0.1 amendments, §2 P0, §3, §6, §9 locked
> decisions, §10 P0 acceptance, §13 test plan). This doc is the scenario-ID ↔ test ↔ acceptance map
> plus the public-API contract the tests assume. Archive doc, no zh twin needed.

## Run

```bash
cd code/server
# the whole P0 acceptance set (red until P0 lands):
python -m pytest -m billing_p0 -q
# everything else, unaffected (must stay green throughout):
python -m pytest -q -m "not deploy and not postgres and not docker and not e2e and not billing_p0"
```

Marker `billing_p0` is registered in `pytest.ini`. CI can keep itself green during the
implementation window with `-m "... and not billing_p0"`; remove the exclusion when P0 ships.

## Current expected state (post-P0 acceptance, 2026-08-10)

- **38 PASS**, 0 fail, 0 skip (`python -m pytest -m billing_p0 -q`).
- Full suite `-m "not deploy and not postgres and not docker and not e2e"`: 427 passed.
- Pre-implementation expectation (for the record): 20 FAIL / 3 SKIP / 2 PASS.

## Files

| File | Kind |
|---|---|
| `code/server/tests/helpers/billing_p0.py` | shared fixtures/helpers + contract docstring |
| `code/server/tests/unit/test_billing_p0_service.py` | unit — billing_service (skips until module exists) |
| `code/server/tests/integration/test_billing_p0_migration.py` | integration — backfill (skips until module exists) |
| `code/server/tests/integration/test_billing_p0_seat_enforcement.py` | integration — seat caps (fails now) |
| `code/server/tests/integration/test_billing_p0_admin_api.py` | integration — admin BA API (fails now) |
| `code/server/tests/integration/test_billing_p0_mcp_selfhost.py` | integration — whoami/doctor/self-host (fails now) |

Design §13 named these `unit/test_billing_service.py`, `integration/test_billing_migration.py`,
`integration/test_seat_enforcement.py`; the `_p0_` names cover the same P0 rows (parent-task naming
convention). If Composer prefers the §13 names, renaming the files is fine — keep the scenario IDs.

## Scenario map

Acceptance column = the §10 P0 checkbox the scenario proves. State = expected result **today**.

### `unit/test_billing_p0_service.py` (module skips until `billing_service` exists)

| ID | Test | Covers | Acceptance |
|---|---|---|---|
| BP0-U1 | `test_plans_seeded_with_team_stub` | plans seeded free/pro/team_stub/team; seats 1/1/3/5, libs 1/5/3/10 (§3.1(4), §9.1) | bullet 1 |
| BP0-U2 | `test_login_bootstrap_creates_free_personal_billing_account`, `test_login_bootstrap_is_idempotent` | login bootstrap → BA plan=free, owner_type=org, calendar-month period (§3.1(3), §3.3) | bullet 1 |
| BP0-U3 | `test_effective_plan_and_quota_defaults`, `test_quota_override_beats_plan_default`, `test_env_allowlist_beats_db_plan` | env > override > plan precedence (§3.1(5)) | bullets 2, 4 |
| BP0-U4 | `test_set_plan_writes_through_principal_projection` | write-through projection to `principals.plan_code` (§3.2) | bullet 2 |
| BP0-U5 | `test_pro_creator_team_org_gets_team_stub` | Pro-created team org → `team_stub`, never full team (§0.1(1), Decision 5a=A) | bullet 3 |
| BP0-U6 | `test_seat_usage_counts_pending_invite_reservations` | seats_used = active + remaining_uses of non-expired invites (§0.1(2)) | bullet 3 |

### `integration/test_billing_p0_migration.py` (module skips until `billing_service` exists)

| ID | Test | Covers | Acceptance |
|---|---|---|---|
| BP0-G1 | `test_backfill_run_twice_same_state` | run twice → byte-identical billing state | bullet 1 |
| BP0-G2 | `test_backfill_removes_all_plan_labels_and_links_real_fks` | zero `plan:` labels; every org → real `ba_*` FK | bullet 1 |
| BP0-G3 | `test_backfill_personal_plan_mapping` | `plan_code=pro`/env-allowlist → pro BA; others free (§3.3(2)) | bullets 1, 4 |
| BP0-G4 | `test_backfill_team_orgs_land_on_team_stub_never_full_team` | `plan:pro` AND `plan:admin` → `team_stub` (§0.1(1)) | bullet 3 |
| BP0-G5 | `test_backfill_populates_api_key_billing_account` | `api_keys.billing_account_id` backfill to owner personal BA (§0.1(3), P0) | bullet 1 |
| BP0-G6 | `test_backfill_writes_audit_billing_events` | `billing_events` `type='migration_backfill'` audit (§3.3(2)) | bullet 1 |

### `integration/test_billing_p0_seat_enforcement.py` (fails now)

| ID | Test | Covers | State today |
|---|---|---|---|
| BP0-S1 | `test_invite_create_at_cap_403` | invite create at 3 active seats → `403 seat_limit_exceeded` | FAIL (201) |
| BP0-S2 | `test_invite_create_clamps_max_uses_to_remaining_seats` | `max_uses` clamped to remaining seats (§0.1(2)) | FAIL (no clamp) |
| BP0-S3 | `test_pending_invite_reservation_blocks_direct_add` | reservations consume capacity | FAIL (201) |
| BP0-S4 | `test_redeem_preexisting_invite_at_cap_403` | redeem pre-existing token at cap → 403; redeemer not admitted | FAIL (200) |
| BP0-S5 | `test_direct_add_at_cap_403` | direct add at cap → 403 | FAIL (201) |
| BP0-S6 | `test_personal_org_direct_add_blocked` | personal-org direct-add security fix (Decision 7) + invite-block regression guard | FAIL (201) |
| BP0-S7 | `test_grandfathered_over_cap_org_keeps_members_blocks_new_adds` | Decision 4-A grandfathering + removal + last-admin protection | FAIL (add succeeds) |
| BP0-S8 | `test_concurrent_direct_adds_never_oversell` | TOCTOU race: 5 concurrent adds, 1 seat → exactly 1 winner (§0.1(2) atomic `admit_org_member`, §12) | FAIL (oversell 7/3) |
| BP0-S9 | `test_expired_invite_releases_reserved_seats` | expired invites reserve nothing | PASS (guards over-counting) |

All map to §10 P0 bullet 3.

### `integration/test_billing_p0_admin_api.py` (fails now)

| ID | Test | Covers | State today |
|---|---|---|---|
| BP0-A1 | `test_admin_billing_account_detail` | `GET /api/admin/billing-accounts/{ba_id}` | FAIL |
| BP0-A2 | `test_patch_plan_flips_paid_projection_and_quotas` | PATCH plan → `is_paid_principal`, projection, team-org gate flip (bullet 2) | FAIL |
| BP0-A3 | `test_patch_status_past_due_roundtrip`, `test_patch_rejects_unknown_plan_and_status` | status transitions + input validation | FAIL |
| BP0-A4 | `test_patch_writes_billing_events_audit_row` | audit row per PATCH (§8.1) | FAIL |
| BP0-A5 | `test_quota_override_put_and_delete` | `PUT/DELETE …/overrides/{quota_key}` | FAIL |
| BP0-A6 | `test_non_admin_cannot_touch_billing_accounts` | actor gating 403 | FAIL |
| BP0-A7 | `test_legacy_user_plan_patch_still_works` | `PATCH /api/admin/users/{pid}/plan` alias writes through to BA | FAIL |
| BP0-A8 | `test_env_allowlist_still_overrides_to_pro` | env break-glass (bullet 4) | PASS (guard) |
| BP0-A9 | `test_patch_unknown_billing_account_404` | unknown BA → 404 | FAIL (guarded against spurious pass) |

### `integration/test_billing_p0_mcp_selfhost.py` (fails now)

| ID | Test | Covers | State today |
|---|---|---|---|
| BP0-M1 | `test_whoami_returns_plan_and_quota_summary`, `test_whoami_plan_reflects_plan_change` | `ma3_whoami` `plan` block (bullet 5); shipped `storage_quota` block survives | FAIL / SKIP |
| BP0-M2 | `test_doctor_reports_billing_schema_ok` | `ma3_doctor.billing_schema_ok` (bullet 6) | FAIL |
| BP0-M3 | `test_selfhost_bootstrap_gets_default_ba_without_stripe` | provider=none default BA, no `stripe` import, no `/webhooks/stripe` (bullet 6, G7) | FAIL |

## Public contract Composer implements against

(Full docstring version in `tests/helpers/billing_p0.py`.)

**Module `app.services.billing_service`:**

```python
run_billing_backfill() -> dict                    # idempotent pass after initialize_database (§3.3)
get_billing_account(ba_id) -> dict | None
get_billing_account_for_org(org_id) -> dict | None
effective_plan(billing_account_id) -> dict        # includes "code"
effective_quota(billing_account_id, quota_key) -> int   # env > quota_overrides > plan
set_billing_account_plan(ba_id, *, plan_code=None, status=None,
                         actor_principal_id=None) -> dict   # write-through projection
set_quota_override(ba_id, quota_key, value, *, reason=None, expires_at=None)
clear_quota_override(ba_id, quota_key)
seat_usage(org_id) -> {"used", "active_members", "pending_invite_uses", "included_seats"}
```

**Tables** (created by `db.py::initialize_database`, schema per `docs/03-backend/billing-and-quotas.md`
§3 + design/27 §3.1 amendments): `plans` (must include columns `code, scope, included_seats,
max_libraries`; seeded free/pro/team_stub/team), `billing_accounts` (`id ba_*, owner_type='org',
owner_id, plan_code, status, current_period_start/end`), `quota_overrides`
(`billing_account_id, quota_key, value, reason, expires_at`), `billing_events` (incl. `type`,
`billing_account_id`; backfill rows use `type='migration_backfill'`), plus column
`api_keys.billing_account_id` (nullable).

**Routes:** `GET/PATCH /api/admin/billing-accounts/{ba_id}` (PATCH body `{plan_code?, status?}`,
detail body includes `plan_code, status, owner_type, owner_id`), `PUT/DELETE
/api/admin/billing-accounts/{ba_id}/overrides/{quota_key}` (PUT body `{value, reason?, expires_at?}`).

**Error contract:** seat denials are `403 {"detail": {"error": "seat_limit_exceeded", "used": …,
"included_seats": …, "upgrade_url": …}}` on invite create, invite redeem, and direct add — including
the personal-org direct-add block. `upgrade_url` presence is NOT asserted in P0 (Decision 7:
no SaaS funnel before Checkout).

**MCP:** `ma3_whoami` structured content gains
`plan = {plan_code, status, seats: {used, included_seats}, libraries: {used, limit}, storage: {…}}`;
`ma3_doctor` gains `billing_schema_ok: true`.

## Ambiguities resolved / TODOs left in tests

1. **Seat error code**: §10 says `seat_limit_exceeded`, §9.1 says stub caps use
   `team_upgrade_required`. Tests pin **`seat_limit_exceeded` for seat admission** (the §10
   acceptance wording is explicit about seats); `team_upgrade_required` is read as the code for
   the *other* stub caps (libraries/storage/reads, mostly P1). If the owner rules otherwise,
   update `_assert_seat_limit_error` in one place.
2. **Personal-org direct-add block** also asserts `seat_limit_exceeded` (hard-1 seat cap semantics,
   §6 seat row). A dedicated error code would need a test edit.
3. **`quota_key` names** assumed: `included_seats`, `max_libraries` (aligned with `plans` column
   names in billing-and-quotas.md §3.1).
4. **Race test on SQLite**: exercises the §0.1(2) atomic-admission requirement with 5 threads via
   TestClient. If `database is locked` surfaces, the fix belongs in `admit_org_member`
   (BEGIN IMMEDIATE + retry), not in the test.
5. **whoami plan block shape** (key names `seats/libraries/storage`) is my concretization of
   "§8.5 plan + quota summary"; nothing else in the design pins it. Composer may adjust names only
   together with this doc + tests.
6. **billing_events on PATCH**: tests assert only "count increased for that BA", not the event
   `type` string.
7. **P1 rows intentionally not covered** (metering, rate limits, `/ui/billing/`, past_due
   semantics, pooled storage): the §13 P1 modules (`test_usage_metering.py`,
   `test_billing_enforcement.py`, …) are a separate tests-first pass after P0 is green.
