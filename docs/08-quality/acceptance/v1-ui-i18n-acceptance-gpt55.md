# v1 UI i18n Acceptance

> Chinese version: [v1-ui-i18n-acceptance-gpt55.zh.md](v1-ui-i18n-acceptance-gpt55.zh.md)

> Note: the zh-CN UI copy asserted during acceptance below (Home = *wǒ de zhǔyè*, Libraries = *kù*, Records = *jìlù*, Votes = *tóupiào*, Sign out = *tuìchū*) is spelled out in pinyin plus its English gloss rather than reproducing the CJK glyphs.

Verdict: **PASS-WITH-NITS**

Date: 2026-07-06

Commit: `a80b280`

## Pytest Results

Command:

```bash
cd <REPO_ROOT>/code/server && env -u MA3_PUBLIC_BASE_URL -u MA3_DATABASE_URL .venv/bin/pytest tests/integration/test_ui_i18n.py tests/integration/test_user_portal*.py tests/integration/test_portal_html_regression.py -q --tb=short
```

Result: **PASS**

- `41 passed`
- `1 warning`
- Runtime: `7.34s`
- Warning: Starlette `TestClient` deprecation warning from `fastapi/testclient.py`.

## Curl Smoke Results

Manual smoke used a temporary local uvicorn instance on `127.0.0.1:8765` with an authenticated test portal user, and all curl commands were run with proxy variables unset and `NO_PROXY=127.0.0.1`.

- `GET /ui/me/?lang=en-US`: **PASS**
  - `HTTP/1.1 200 OK`
  - `<html lang="en-US">`
  - English shell/page text present: `Home`, `Libraries`, `Records`, `Votes`, `Account`, `Sign out`
  - `set-cookie: ma3_locale=en-US; Max-Age=31536000; Path=/; SameSite=lax`
- `GET /ui/me/writes/?lang=en-US`: **PASS**
  - `HTTP/1.1 200 OK`
  - `<html lang="en-US">`
  - English writes text present: `Records`, `All`, `Published`, `Pending`, `Deleted`, `Batch actions`, `No records`
  - `set-cookie: ma3_locale=en-US; Max-Age=31536000; Path=/; SameSite=lax`
- `GET /ui/me/?lang=zh-CN`: **PASS**
  - `HTTP/1.1 200 OK`
  - `<html lang="zh-CN">`
  - Chinese shell/page text present (zh-CN strings for): `Home`, `Libraries`, `Records`, `Votes`, `Sign out`
  - `set-cookie: ma3_locale=zh-CN; Max-Age=31536000; Path=/; SameSite=lax`

## I18N Checklist

| Criteria | Status | Notes |
|---|---|---|
| I18N-1 Locale Resolution | PASS | `?lang=en-US` resolves English, renders `<html lang="en-US">`, and sets `ma3_locale=en-US`; covered by pytest and curl. |
| I18N-2 Default zh-CN | PASS | Default renders `zh-CN`; covered by pytest. |
| I18N-3 Cookie Persistence | PASS | Cookie-driven English rendering is covered by pytest on `/ui/me/writes/`. |
| I18N-4 Query Overrides Cookie | PASS | `?lang=zh-CN` overrides English cookie and updates cookie; covered by pytest. |
| I18N-5 Accept-Language Fallback | PASS | `Accept-Language: en-US,en;q=0.8,zh-CN;q=0.5` renders English; covered by pytest. |
| I18N-6 Header Switcher | PASS | Migrated `render_page(...)` Phase 1 pages receive `request`/`locale` and render alternate language links preserving path/query behavior. |
| I18N-7 Shared Shell Localized | PASS | Nav, login/account/logout, account subnav, pagination/list footer, table empty state, brand aria label, and copy feedback are locale-aware. |
| I18N-8 Overview Localized | PASS | `/ui/me/` title/subtitle, stats, cards, tables, empty state, and CTAs are localized. |
| I18N-9 Settings and Setup Localized | PASS | `/ui/me/settings/` and `/ui/me/setup/` metadata, help text, labels, and buttons are localized. Raw validation details remain a nit. |
| I18N-10 Writes Localized | PASS | Filters, sortable headers, UI-controlled status badges, batch labels, deleted placeholder, empty state, and selection error are localized. |
| I18N-11 Votes Localized | PASS | Filters, headers, unavailable badge, empty state, and page metadata are localized. |
| I18N-12 Keys Localized | PASS | Key list/detail primary labels, grants, roles, empty states, copy/save/delete controls, confirmations, and authing-disabled page are localized. Unused created-page helper remains a nit. |
| I18N-13 Auth Error Localized | PASS | Auth error page uses resolved locale, localized title/action, and shared page shell lang. Some dynamic detail messages remain a nit. |
| I18N-14 Catalog Fallback | PASS | Missing current-locale keys fall back to `zh-CN`; missing keys render `[[key]]` and log a warning. Catalog completeness is covered by pytest. |
| I18N-15 HTML Safety Preserved | PASS | `tr()` returns plain text; route call sites continue escaping translated/user-interpolated text; catalogs contain no arbitrary HTML. |
| I18N-16 No API Contract Change | PASS | Translation changes are scoped to SSR UI; API/MCP JSON contracts are not translated. |
| I18N-17 Incremental Migration | PASS | Helpers retain default `zh-CN` locale values and partially migrated pages continue rendering. |
| I18N-18 Tests | PASS | Pytest covers zh/en overview, writes, votes, keys, locale persistence, query override, Accept-Language fallback, catalog completeness, and missing-key markers on Phase 1 pages. |

## Deferred Scope

- `/ui/libraries/`, `/ui/libraries/{library_id}/`, `/ui/libraries/{library_id}/settings/`: **DEFERRED** to Phase 2 per design. Current implementation still contains hardcoded Chinese/English strings and does not pass locale/request into `render_page(...)`.
- `/ui/records/{record_id}/`: **DEFERRED** to Phase 2 per design. Current implementation still contains hardcoded record detail, buffer action, and feedback text and does not pass locale/request into `render_page(...)`.

## Open Nits and Recommendations

- Auth callback detail messages are not consistently translated. The page title/action and lang are localized, but error bodies such as Authing callback failures, expired state, token exchange failures, and user resolution failures can still render Chinese inside an English page. Recommendation: map known user-facing auth errors to catalog keys; keep low-level exception details API-like or append after localized context.
- Setup/settings POST validation messages can surface raw service `HTTPException.detail` strings, including mixed English/Chinese. Recommendation: map known setup validation errors to UI catalog keys when rendering/redirecting back to setup.
- `_render_created_page(...)` in `routes_keys.py` still has hardcoded Chinese strings. It appears unreachable after create now returns to the list, so this is not a Phase 1 blocker. Recommendation: either localize it if it remains as a fallback UI path or delete it in a cleanup pass.
- `render_list_footer(...)` localizes the page-size phrase with inline locale branches instead of the existing `shell.list.per_page` catalog key. Recommendation: use the catalog key for consistency in a cleanup pass.
