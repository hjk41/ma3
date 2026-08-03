# Portal Playwright regression

> Chinese version: [portal-playwright-regression.zh.md](portal-playwright-regression.zh.md)

Design lead: Fable ([archive](../../09-engineering/design-archive/26-quality-playwright-eval-cadence-fable.md)).

## Decision record

| Tier | When | Secrets | Suite |
|------|------|---------|-------|
| **A — local-auth smoke** | **Every PR** (`ci.yml` job `e2e-portal`) + nightly | None | `code/server/tests/e2e/test_portal_smoke.py` (P1–P12) |
| **B — Authing** | Nightly + pre-release checklist | `AUTHING_TEST_USER` / `AUTHING_TEST_PASS` + `MA3_E2E_BASE_URL` | `code/server/scripts/e2e_authing_ui.py` (unchanged); SKIP with summary if secrets absent |

## In scope

- Login/session: local-auth forms (Tier A); Authing hosted login / logout / account (Tier B)
- Portal SSR under `/ui/*`: me dashboard, settings, writes, votes, libraries, keys (+ detail), Observatory **403** for non-admin
- Browser-only behaviors: JS confirm on key delete, copy helper, nav/form POST → HTML (not bare JSON), first-run setup gate

## Out of scope

- Duplicating HTTP assertions already in `tests/integration/test_user_portal*.py` / `test_portal_html_regression.py`
- Observatory admin internals, org/billing ops pages
- Visual/pixel, mobile, cross-browser (Chromium only)
- MCP protocol (unit/integration + agent eval)

## Case table (Tier A)

| ID | Case |
|----|------|
| P1 | Setup / owner login after first-run |
| P2 | Bad password re-renders HTML login form |
| P3 | Dashboard stat cards → writes |
| P4 | Nav present; member has no Observatory href |
| P5 | Member Observatory → HTML 403 |
| P6 | Writes sort/filter links navigate |
| P7 | Empty batch submit → HTML, not JSON |
| P8 | Key create → `ma3k_` + copy → rename → delete |
| P9 | Votes page smoke |
| P10 | Libraries list → detail |
| P11 | Logout clears session |
| P12 | Locale `en-US` / `zh-CN` render without 500 |

## How to run locally

```bash
cd code/server
pip install -r requirements.txt -r requirements-e2e.txt
playwright install chromium
pytest -q -o addopts= -m e2e tests/e2e --browser chromium
```

Default `pytest` excludes `e2e` via `pytest.ini` `addopts`.
