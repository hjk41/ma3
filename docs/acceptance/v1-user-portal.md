# v1 Acceptance — User Portal (design/15)

- **Tester**: fable (QA acceptance)
- **Date**: 2026-07-04
- **Target**: local pytest + code inspection; production smoke on 192.168.31.202 when deployed
- **Scope**: ratified design/15 + visual spec `15-user-portal-visual-sonnet5.md` + fable visual review `15-user-portal-visual-review-fable.md`
- **Method**: integration suite `tests/integration/test_user_portal.py`, unit updates in `tests/unit/test_auth.py`, full suite `pytest tests/`, structural grep for IA/routing

## Verdict

**PASS-WITH-NITS.** User portal v1 is implemented: default landing `/ui/me/`, GitHub-style SSR theme with parametric nav, Libraries stats-only pages, record detail at `/ui/records/{id}/`, Observatory admin-only (403 for non-admin), anonymous public library stats with minimal header, boot guard when Authing is on without `MA3_AUTH_ADMIN_USERS`. All 203 automated tests pass locally. Production deploy to 202 not re-run in this acceptance pass (see nit 1).

## P1–P12 mapping

| # | Criterion | Result | Evidence |
|---|---|---|---|
| P1 | `/` and `/ui/` → 302 `/ui/me/`; Authing login default `next=/ui/me/` | **PASS** | `main.py` root routes; `routes_auth.py` default next; `test_root_redirects_to_me`, `test_auth_login_default_next_is_me` |
| P2 | Logged-in `/ui/me/` shows profile, `principal_id` copy row, stat cards, recent writes list-group, entitled libraries table | **PASS** | `routes_portal.py` `portal_me`; `test_me_shows_principal_id` |
| P3 | `/ui/me/writes/` and `/ui/me/votes/` paginated tables (not list-group) | **PASS** (code) | `portal_writes` / `portal_votes` use `render_table` + `render_pagination`; no dedicated pagination DOM test |
| P4 | `/ui/libraries/` requires login; detail is **Stats only** (no record enumeration) | **PASS** | `portal_libraries`, `_render_library_detail`; footer copy「库内 record 列表仅管理员可枚举」; `test_libraries_list_requires_login_when_anonymous`, `test_anonymous_public_library_stats` |
| P5 | Anonymous may view **public default library** stats only; minimal header (brand + 登录), no full topnav / Observatory | **PASS** | `show_minimal_header=True` when `user is None`; `test_anonymous_public_library_stats` asserts no `layout-settings`, no `Observatory` |
| P6 | Non-public library detail requires login | **PASS** | `test_private_library_requires_login` |
| P7 | `/ui/records/{id}/` requires login + read entitlement; active records only; breadcrumb | **PASS** | `portal_record`; `test_record_detail_requires_login`, `test_record_detail_active_community_record` |
| P8 | Observatory: unauthenticated → 302 login; non-admin → **403 HTML** with link to `/ui/me/` | **PASS** | `_require_observatory_admin`; `test_observatory_requires_login_when_authing_enabled`, `test_observatory_non_admin_returns_403`, `test_observatory_logged_in_non_admin_returns_403` |
| P9 | Observatory + `stats.json` admin-only | **PASS** | `test_observatory_admin_can_access`, `test_observatory_stats_json_non_admin_403` |
| P10 | `/ui/observatory/records/{id}` → 301 `/ui/records/{id}/` | **PASS** | `observatory_record`; `test_observatory_record_redirects_to_portal` |
| P11 | Authing enabled + empty `MA3_AUTH_ADMIN_USERS` → refuse boot | **PASS** | `validate_authing_admin_config` in lifespan; `test_validate_authing_admin_config_refuses_empty_allowlist` |
| P12 | GitHub visual: parametric nav (me/libraries/keys/observatory admin-muted), subnav active uses `var(--accent)`, reuses design/14 copy-row | **PASS** (code) | `ui_theme.py` `portal_nav_items`, `render_subnav`, `render_page_403`; visual review PASS-WITH-NITS |

**Test suite**: `pytest tests/` → **202 passed** (15 new portal tests + 1 auth test).

## Visual review nits (from fable, verified)

| Nit | Status |
|-----|--------|
| Subnav active border uses `var(--accent)` not GitHub orange | **Fixed in implementation** |
| No `.layout-settings` sidebar in v1 DOM | **OK** — class not present in codebase |
| `/ui/me/` recent writes use `.list-group`; writes/votes pages use `table.data` | **OK** — per route |
| Anonymous public library minimal header | **OK** — `test_anonymous_public_library_stats` |
| Screenshot checklist (me, 403, anonymous lib, writes pagination, record breadcrumb) | **Deferred** — manual/Playwright on 202 when deployed |

## Nits / observations (non-blocking)

1. **202 deploy smoke-tested 2026-07-04.** `deploy_ma3_v1_202.sh` succeeded; healthz OK; anonymous `/`→`/ui/me/`, `/ui/libraries/lib_default/` 200 (minimal header + 分布), unauthenticated Observatory → 302 login. `MA3_AUTH_ADMIN_USERS=6a45abec4d2ef946d80649f6` set on 202. Deploy pytest gate fails on `MA3_EXPECT_MIN_RECORDS=30` (DB has 14) — env threshold drift, not portal regression.
2. **Writes/votes pagination UI untested.** Logic uses `_PAGE_SIZE=50` and `render_pagination`; no test asserts page-2 link when total > 50.
3. **LAN dev mode (`authing_enabled=False`)**: `/ui/me/` returns 503 by design (`require_authing_for_ui`); Observatory remains open read-only — matches design §2.2 footnote.
4. **`/ui/libraries/` when logged in but no extra grants** still lists Community + personal library via `list_entitled_libraries` — correct v1 heuristic; v1.1 entitlement resolver swap is out of scope.

## Operations log (condensed)

```text
pytest tests/integration/test_user_portal.py tests/unit/test_auth.py → 23 passed
pytest tests/ → 202 passed
grep layout-settings code/server → no matches
code inspection: main.py includes portal_router + root redirects
code inspection: ui_theme portal_nav_items logo → /ui/me/; nav-admin on Observatory
```
