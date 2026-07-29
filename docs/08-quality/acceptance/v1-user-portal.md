# v1 Acceptance — User Portal (design/15)

> Chinese version: [v1-user-portal.zh.md](v1-user-portal.zh.md)

> Note: the zh-CN UI copy referenced below (Libraries = *kù*, Records = *jìlù*, Votes = *tóupiào*, Pending publish = *dài fābù*, Overview = *gàilǎn*, Settings = *shèzhì*) is spelled out in pinyin plus its English gloss rather than reproducing the CJK glyphs.

- **Tester**: fable (QA acceptance)
- **Date**: 2026-07-04 (P1–P12); design/22 implementation 2026-07-05 (P13–P19)
- **Target**: local pytest + code inspection; production smoke on the LAN staging host when deployed
- **Scope**: ratified design/15 + visual spec `15-user-portal-visual-sonnet5.md` + fable visual review `15-user-portal-visual-review-fable.md`
- **Method**: integration suite `tests/integration/test_user_portal.py`, unit updates in `tests/unit/test_auth.py`, full suite `pytest tests/`, structural grep for IA/routing

## Verdict

**PASS** for **P1–P19** (design/15 baseline + design/22 unified layout).

Implementation true source: [../../04-frontend/information-architecture.md](../../04-frontend/information-architecture.md) (the historical design/22 fable has been archived and removed).

## P1–P12 mapping

| # | Criterion | Result | Evidence |
|---|---|---|---|
| P1 | `/` and `/ui/` → 302 `/ui/me/`; Authing login default `next=/ui/me/` | **PASS** | `main.py` root routes; `routes_auth.py` default next; `test_root_redirects_to_me`, `test_auth_login_default_next_is_me` |
| P2 | Logged-in `/ui/me/` shows profile, stat cards, recent writes list-group, entitled libraries table | **PASS** | `routes_portal.py` `portal_me`; profile/settings split per design/17 |
| P3 | `/ui/me/writes/` and `/ui/me/votes/` paginated tables with sort/filter/footer | **PASS** | `portal_writes` / `portal_votes`; `test_user_portal_writes.py`, `test_user_portal_votes.py` |
| P4 | `/ui/libraries/` requires login; detail is **Stats only** (no record enumeration) | **PASS** | `portal_libraries`, `_render_library_detail` |
| P5 | Anonymous may view **public default library** stats only; minimal header | **PASS** | `test_anonymous_public_library_stats` |
| P6 | Non-public library detail requires login | **PASS** | `test_private_library_requires_login` |
| P7 | `/ui/records/{id}/` requires login + read entitlement; active records only | **PASS** | `portal_record` |
| P8 | Observatory: unauthenticated → 302; non-admin → **403 HTML** | **PASS** | `_require_observatory_admin` |
| P9 | Observatory + `stats.json` admin-only | **PASS** | integration tests |
| P10 | `/ui/observatory/records/{id}` → 301 `/ui/records/{id}/` | **PASS** | `observatory_record` |
| P11 | Authing enabled + empty `MA3_AUTH_ADMIN_USERS` → refuse boot | **PASS** | `validate_authing_admin_config` |
| P12 | GitHub visual: parametric nav, subnav accent, copy-row | **PASS** (code) | `ui_theme.py` |

## P13–P19 — design/22 (implemented 2026-07-05)

| # | Criterion | Result | Evidence |
|---|---|---|---|
| P13 | `/ui/me/` stat cards clickable → writes/buffered/libraries/votes/keys | **PASS** | `render_stat_cards` href tuples; `test_stat_card_links_to_buffered_filter` |
| P14 | `/ui/me/writes/` column sort (`sort`/`dir`) | **PASS** | `render_sort_link`; `test_writes_page_has_filter_sort_and_footer` |
| P15 | writes status filter + batch publish/delete (buffered) | **PASS** | `portal_writes_batch`; `test_writes_status_filter_buffered`, `test_writes_batch_publish` |
| P16 | Personal library name `{display_name}'s personal library` | **PASS** | `ensure_personal_library` sync; `test_ensure_personal_library_syncs_stale_display_name` |
| P17 | writes pagination + `per_page` 10/25/50/100 | **PASS** | `render_list_footer`; writes integration tests |
| P18 | `/ui/me/votes/` same list UX (sort, vote filter, per_page) | **PASS** | `portal_votes`; `test_votes_page_has_filter_and_footer`, `test_votes_after_feedback` |
| P19 | Top nav peer: Libraries/Records/Votes/API Keys; subnav Overview+Settings only | **PASS** | `portal_nav_items`; `test_user_portal_nav.py` |

**Backlog index**: see [../../04-frontend/page-specifications.md](../../04-frontend/page-specifications.md)
**Unified design**: see [../../04-frontend/information-architecture.md](../../04-frontend/information-architecture.md)

### P13 stat hrefs (when implemented)

| Stat | href |
|------|------|
| Records | `/ui/me/writes/` |
| Pending publish | `/ui/me/writes/?status=buffered` |
| Accessible libraries | `/ui/libraries/` |
| Votes | `/ui/me/votes/` |
| API Keys | `/ui/keys/` |

## Fable sign-off (design/22, 2026-07-05)

**Verdict: PASS-WITH-NITS**

| # | Result | Evidence |
|---|---|---|
| P13 | **PASS** | `portal_me` stat cards use `render_stat_cards` with hrefs; labels Records/Votes |
| P14 | **PASS** | `portal_writes` + `render_sort_link`; integration test |
| P15 | **PASS** | filter pills + `portal_writes_batch`; batch publish test |
| P16 | **PASS** | `ensure_personal_library` sync via `set_library_name`; unit test |
| P17 | **PASS** | `render_list_footer` with per_page 10/25/50/100 |
| P18 | **PASS** | `portal_votes` mirror UX; votes integration tests |
| P19 | **PASS** | `portal_nav_items` peer nav; subnav Overview+Settings only |

**Nits (non-blocking):**

1. Batch bar always visible on writes page even with zero rows — acceptable v1; could hide when no buffered owner rows.
2. Sort on the Records column is display-only (no DB column) — matches design/19 deferral.
3. Production smoke requires Authing login; automated HTML checks run via pytest only.

> The design/22 two-level navigation, standard list shell, and stat quick entries all landed per spec; all 246 pytest tests green, deployed to 202. Acceptance is **PASS-WITH-NITS**; ready for owner visual confirmation.

## Visual review nits (from fable, verified)

| Nit | Status |
|-----|--------|
| Subnav active border uses `var(--accent)` | **Fixed in implementation** |
| No `.layout-settings` sidebar in v1 DOM | **OK** |
| `/ui/me/` recent writes use `.list-group`; writes/votes pages use `table.data` | **OK** |
| Screenshot checklist | **Deferred** |

## Nits / observations (non-blocking)

1. **202 deploy smoke-tested 2026-07-04.**
2. **202 deploy smoke** — post design/22 deploy 2026-07-05.
3. **LAN dev mode**: `/ui/me/` returns 503 when Authing off — by design.

## Operations log (condensed)

```text
pytest tests/ → 246 passed (2026-07-05, includes P13–P19 integration tests)
deploy/deploy.sh deploy/deploy.<lan>.env → <LAN host>:8000
```
