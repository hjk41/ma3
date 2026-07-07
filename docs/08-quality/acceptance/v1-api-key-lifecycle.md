# v1 Acceptance — API Key Lifecycle (design/14)

- **Tester**: fable (QA acceptance)
- **Date**: 2026-07-04 (updated after layout pass)
- **Target**: 192.168.31.202, ma3 `http://192.168.31.202:8000`, Postgres, Authing enabled
- **Scope**: design/14 §10 criteria A1–A12 (see [../../04-frontend/api-keys-ui-and-api.md](../../04-frontend/api-keys-ui-and-api.md))
- **Method**: real-browser Playwright E2E (`code/server/scripts/e2e_authing_ui.py`) against 202 with the real Authing test account `user:6a45abec4d2ef946d80649f6`, plus the shipped integration suite `tests/integration/test_self_service_onboarding.py` (15 tests) run locally, plus code inspection of `routes_keys.py` / `db.py` for criteria without a dedicated test.

## Verdict

**PASS-WITH-NITS.** The full lifecycle — create, list/copy, rename, grants edit, delete — works end-to-end in a real browser with a real Authing account. List page now exposes per-row **复制** and **删除** in an Actions column (`cell-actions`); detail page merges label + grants into one form with a single **保存** button (`POST /ui/keys/{id}/edit`), with delete isolated in a `danger-zone` block. Every destructive-path criterion verified directly: `DELETE /api/keys/{key_id}` hard-deletes rows, deleted keys fail MCP auth immediately (`-32001`), disappear from both `GET /api/keys` and `/ui/keys/`, and free quota. The 撤销 vocabulary is gone from self-service surfaces. Nits unchanged (A6/A9/rename-owner-only tests missing). Logout E2E remains flaky and unrelated.

## A1–A12 mapping

| # | Criterion | Result | Evidence |
|---|---|---|---|
| A1 | Fresh Authing developer opens `/ui/keys/`, creates a key, copies it, uses it for `ma3_whoami` | **PASS** | Real-browser E2E on 202 with Authing account `user:6a45abec4d2ef946d80649f6`: `/ui/keys/` reachable after login (no redirect back to `/auth/login`), create form submit → 303 → list shows label `e2e-authing-key` and full `ma3k_` plaintext in the copyable input. Key usability over MCP covered by `test_mcp_roundtrip_with_created_key` (whoami dual libs, headless `ma3_report`) and by the account's live key working against 202 MCP. |
| A2 | No `撤销`/`已撤销` on self-service surfaces; destructive action is `删除` | **PASS** | E2E asserts `撤销 not in keys_html` and clicks the `删除` form button; `test_ui_delete_key_form_post` asserts `删除` present and `撤销` absent. `grep -rn '撤销\|revoke' code/server/app`: remaining hits are only the legacy `db.revoke_api_key` helper (kept for legacy/admin rows per design §6), the `revoked_at` resolver check, and the MCP `-32001` error string ("unknown, revoked, or expired") — none is keys-UI copy. The two stragglers from review N3 (legacy-key hint, quota error) are fixed. |
| A3 | `DELETE /api/keys/{key_id}` removes the `api_keys` row and all `api_key_grants` rows | **PASS** | Verified on 202: row and grants gone after delete. `test_delete_key_blocks_mcp` asserts `db.get_api_key_for_principal(...) is None`; `test_delete_key_hard_deletes_grants` asserts `db.get_api_key_grants(key_id) == []`. |
| A4 | Deleted keys immediately fail MCP authentication | **PASS** | `test_delete_key_blocks_mcp`: after `DELETE`, `api_key_service.resolve_api_key(plaintext) is None` and `tools/call ma3_whoami` with the deleted plaintext → JSON-RPC `-32001`. |
| A5 | Deleted keys absent from `GET /api/keys` and `/ui/keys/` | **PASS** | E2E post-delete steps: renamed key row gone from the page, and browser `fetch('/api/keys')` JSON no longer contains it. `test_ui_delete_key_form_post` asserts the label is absent from the next list render. |
| A6 | `write_audit_log` rows survive key deletion with the original `api_key_id` string | **PASS** (code inspection) | `write_audit_log` has no FK to `api_keys` (db.py schema), and `db.delete_api_key` touches only `api_keys` + `api_key_grants` — structurally nothing can cascade. No dedicated `test_delete_key_keeps_write_audit_history` was shipped; see nit 1. |
| A7 | Key deletion frees quota | **PASS** | `test_quota_frees_after_delete`: with `max_keys_per_principal=1`, second create → 400, delete first → create succeeds. Quota SQL counts `revoked_at IS NULL` rows, so hard-deleted rows naturally stop counting. |
| A8 | Cannot delete/rename another user's key; 404 without existence leak | **PASS** (delete tested; rename by inspection) | `test_delete_key_owner_only`: session user B deleting A's key → 404. Rename path uses the same ownership predicate (`db.update_api_key_label` has `principal_id` in the WHERE, route returns 404 on `None`) but has no dedicated test; see nit 2. |
| A9 | Mutating routes reject missing/cross-origin `Origin`/`Referer` | **PASS** (code inspection) | `_assert_same_origin` is called by `POST/PATCH/DELETE /api/keys*` and all `/ui/keys/*` form routes; it raises 403 for missing headers ("origin or referer required") and mismatched origin/referer ("cross-origin request rejected"). No test exercises the 403 path for the new DELETE/PATCH verbs; see nit 3. |
| A10 | Free tier requires Community writer; paid principals can customize | **PASS** | `test_create_key_with_custom_grants`: free user requesting Community `reader` → 400 with free-tier detail. `test_paid_user_can_create_reader_community_key`: principal in `paid_principal_ids` → 200 with Community `reader` grant stored. |
| A11 | Rename updates only label; plaintext/hash/grants/audit unchanged | **PASS** | `test_update_key_label`: PATCH → 200 with new label, original plaintext still resolves via `resolve_api_key`. `test_ui_rename_key_form_post` covers unified SSR `/edit` form (single 保存). E2E renamed via `form[action$="/edit"]` in a real browser. |
| A12 | Optional Authing Playwright E2E passes with `AUTHING_TEST_USER` | **PASS** (keys steps) | On 202: login, keys create form, no-撤销 check, unified save (rename + grants), list `cell-actions` copy/delete present, delete via danger-zone — all green. Logout step flaky (residual). |

**Test suite**: `pytest tests/integration/test_self_service_onboarding.py` → **18 passed** locally (adds `test_ui_list_shows_copy_and_delete`; rename/grants forms use `/edit`).

## Nits / observations (non-blocking)

1. **A6 has no dedicated test.** The design's §9 matrix lists `test_delete_key_keeps_write_audit_history` but it was not shipped. The property holds structurally (no FK, delete helper touches two tables only), but a 5-line DB assertion test would pin it against future schema changes.
2. **Rename owner-only untested.** `test_update_key_label_owner_only` from the matrix is missing; only the delete variant exists. Same DB predicate, low risk, but cheap to add.
3. **No same-origin 403 test for DELETE/PATCH.** Review gap #6 stands: `_assert_same_origin` is wired to all mutating verbs but nothing asserts the 403 for the new verbs. One parametrized test would close it.
4. **`db.delete_api_key` retains the SELECT-then-DELETE shape** (review N4 recommended DELETE-first with rowcount). Functionally correct — ownership is re-checked in the DELETE's WHERE clause — just one redundant round trip.
5. **Copy affordance verified as presence-only.** E2E confirms the `ma3k_` plaintext is rendered in a selectable input; the clipboard-JS click itself is not asserted (headless clipboard is unreliable). Acceptable — manual fallback (select + copy) is the designed degradation.

## Known residuals (unrelated to key lifecycle)

- **Logout E2E flakiness**: the `e2e_authing_ui.py` logout step ("still authenticated after logout") intermittently fails on 202 — the session appears to persist after `GET /auth/logout`. This is a session/Authing-logout concern from the design/13 scope, not an API-key lifecycle criterion; none of A1–A12 depends on it. Tracked separately.

## Operations log (condensed)

```text
e2e_authing_ui.py vs 192.168.31.202:8000, AUTHING_TEST_USER=user:6a45abec4d2ef946d80649f6
  login → /ui/keys/ loads (no login redirect)
  create form label=e2e-authing-key → 303 → detail shows label + ma3k_ plaintext
  assert 撤销 not in page                                    → OK
  unified save (form /edit): rename + grant_personal reader  → OK
  list page cell-actions copy/delete present                 → OK
  delete via danger-zone → row gone; fetch /api/keys omits key → OK
  logout step                                                → FLAKY (residual, non-keys)
pytest tests/integration/test_self_service_onboarding.py     → 18 passed
psql/DB on 202: DELETE /api/keys/{id} → api_keys row gone, api_key_grants rows gone
PATCH /api/keys/{id} {"label": ...} → label updated, key still authenticates
grep -rn '撤销|revoke' code/server/app → legacy helper + MCP error copy only
code inspection: write_audit_log no FK to api_keys; _assert_same_origin on all mutating routes
```
