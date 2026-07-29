# v1 Acceptance — User Portal UI (SSR)

> Chinese version: [v1-user-portal-ui.zh.md](v1-user-portal-ui.zh.md)

- **Version**: 2026-07-06 (revised on top of design/22 + write-buffer + keys finalization)
- **Design source of truth**: [information-architecture.md](../../04-frontend/information-architecture.md), [portal-permissions.md](../../04-frontend/portal-permissions.md), [visual-design-system.md](../../04-frontend/visual-design-system.md)
- **Automation**: `tests/integration/test_user_portal*.py`, `test_portal_html_regression.py`
- **Goal**: **every behavior that can be asserted via SSR must have a pytest**; relying only on "previously passed acceptance" or a single manual click is forbidden

## Acceptance verdict template

```text
Verdict: PASS | PASS-WITH-NITS | FAIL
Date:
Commit:
pytest: N passed, 0 failed
202 smoke: healthz OK / skipped
Browser E2E: run / skipped (AUTHING_TEST_*)
Open nits:
```

---

## 0. Global SSR invariants (**R series — mandatory release gate**)

These items specifically guard against "the page opens but the HTML renders incorrectly" defects (a real regression seen on 2026-07-06).

| ID | Condition | Expectation | Automation |
|----|------|------|--------|
| **R1** | GET on any list page with `render_sort_link` | Response is `text/html`; sortable column headers are **clickable `<a href>`**; escaped `&lt;a href=` must **not** appear | `test_portal_html_regression::test_*_sort_headers_are_links` |
| **R2** | `render_table` header contains an HTML fragment | Header cells must **not** double-`esc()` existing HTML | Same as above + code review of `ui_theme._render_table_cell` |
| **R3** | Any portal **SSR form POST** (batch, delete, edit) fails validation | Must **303/302 back to an HTML page** or intercept via inline JS; must **not** return a bare JSON `{"detail":...}` to the browser | `test_writes_batch_empty_selection_redirects_with_message` |
| **R4** | Logged-in user GETs a portal page | Must not 500; when Authing is unconfigured, `/ui/me/` etc. → **503 HTML** (not JSON) | `test_me_requires_login_when_authing_enabled`, etc. |
| **R5** | Badges / links / buttons on the page | No unclosed HTML tag strings, and no HTML tags rendered as literal text | Manual spot-check + R1 |

---

## 1. Routing and navigation (N series)

| ID | Condition | Expectation | Automation |
|----|------|------|--------|
| N1 | GET `/`, `/ui/` | 302 → `/ui/me/` | `test_root_redirects_to_me` |
| N2 | Not logged in, GET `/ui/me/` (Authing on) | 302 → `/auth/login?next=...` | `test_me_requires_login_when_authing_enabled` |
| N3 | Top bar | Regular user: **Home \| Libraries \| Records \| Votes \| API Keys**; admin gets **Observatory** appended (de-emphasized) | `test_user_portal_nav.py` |
| N4 | Top bar active state | `/ui/me/writes/?status=buffered` → **Records** active | `test_user_portal_nav.py` |
| N5 | subnav | **Only** `/ui/me/*` has an **Overview \| Settings** subnav; writes/votes/libraries/keys have **no** subnav | `test_writes_page_has_filter_sort_and_footer`, `test_votes_page_has_filter_and_footer` |
| N6 | GET `/auth/login` default next | `/ui/me/` | `test_auth_login_default_next_is_me` |
| N7 | Non-admin GET `/ui/observatory/` | **403 HTML** (not a 302 into the backend) | `test_observatory_non_admin_returns_403` |

---

## 2. Overview `/ui/me/` (M series)

| ID | Condition | Expectation | Automation |
|----|------|------|--------|
| M1 | Logged-in GET | 200; contains `.profile-header`, 5 `stat-card-link` cards | `test_me_overview_is_dashboard_without_account_chrome` |
| M2 | Overview page | **No** Principal ID, **no** "edit display name", **no** `ma3CopyFrom` | Same as above |
| M3 | Stat links | Records→`/ui/me/writes/`; Pending publish→`?status=buffered`; Libraries→`/ui/libraries/`; Votes→`/ui/me/votes/`; Keys→`/ui/keys/` | `test_stat_card_links_to_buffered_filter` |
| M4 | Count is 0 | Stat card is **still clickable** (href present) | Code review of `render_stat_cards` |
| M5 | "Recent contributions" | list-group; links to `/ui/records/{id}/` or a deleted placeholder | Manual / follow-up test |

---

## 3. Account `/ui/me/settings/` (S series)

| ID | Condition | Expectation | Automation |
|----|------|------|--------|
| S1 | GET settings | Display name is **read-only**; no `name="display_name"` input | `test_me_settings_shows_readonly_display_name_and_principal_id` |
| S2 | Principal ID | Shown read-only in `.id-block`; **no** copy button | Same as above |
| S3 | subnav | **Settings** active | Manual / extend nav tests |

---

## 4. Record list `/ui/me/writes/` (W series — **key focus**)

Design: [IA §3.4](../../04-frontend/information-architecture.md)

### 4.1 List shell

| ID | Condition | Expectation | Automation |
|----|------|------|--------|
| W1 | GET default | 200; contains `filter-pills`, `table.data`, `list-footer`; h1 is "Records" | `test_writes_page_has_filter_sort_and_footer` |
| W2 | Filter pills | All / Published / Pending publish / Deleted; active state matches query | Same as above + `test_writes_status_filter_buffered` |
| W3 | `per_page` | 10 / 25 / 50 / 100; default 50 | list-footer link present |
| W4 | Pagination | `page` preserves sort/filter/status | Code review of `_writes_list_query` |

### 4.2 Sortable headers (**R1 sub-item**)

| ID | Condition | Expectation | Automation |
|----|------|------|--------|
| W5 | GET any writes list | Columns **time, status, library, type** headers are `<a href="...sort=...">` | `test_writes_sort_headers_are_links` |
| W6 | Click sort (or GET `sort=library_name&dir=asc`) | 200; ↑/↓ arrow appears on the current sort column | Manual / GET assertion |
| W7 | Invalid `sort=` | Falls back to `created_at` | Unit / follow-up |

### 4.3 Row content and status

| ID | Condition | Expectation | Automation |
|----|------|------|--------|
| W8 | active record | "Record" column is a **link** → `/ui/records/{id}/`; problem summary visible | Indirectly via batch tests |
| W9 | buffered + owner | Status badge "Pending publish"; row **has** a leading checkbox | `test_writes_status_filter_buffered` |
| W10 | non-owner / non-buffered | **No** checkbox | Code review |
| W11 | **Deleted** (`status=deleted` or tombstone) | "Record" column text: **"Record content fully deleted, cannot be displayed"** (`.card-muted`); must **not** show the original problem text; must **not** use the badge alone as record content | `test_writes_deleted_filter_shows_redacted_label` |
| W12 | Deleted | Status column can still show a "Deleted" badge | Same as above |

### 4.4 Batch actions (**R3 sub-item**)

| ID | Condition | Expectation | Automation |
|----|------|------|--------|
| W13 | Header | When the page has batch-eligible rows, show a **select-all-on-page** checkbox (`#writes-select-all`) | `test_writes_page_has_select_all_and_batch_script` |
| W14 | Select all | Checking the header → all `record_ids` checkboxes on the page sync | JS + manual L4 |
| W15 | Clicking "batch publish/delete" with **no rows selected** | Form **does not submit**, or POST → **303 back to the list** + inline warning "please select at least one record"; **a JSON 400 is forbidden** | `test_writes_batch_empty_selection_redirects_with_message` |
| W16 | Select buffered rows → batch publish | 303; record → `active` | `test_writes_batch_publish` |
| W17 | Batch POST | same-origin; preserves `status/sort/dir/page/per_page` query | Code review of hidden fields |
| W18 | Batch delete | Owner + buffered only; behaves the same as a single delete | Follow-up test |

### 4.5 Write-buffer cross-checks

| ID | Condition | Expectation | Automation |
|----|------|------|--------|
| W19 | Library buffer>0, new write | Visible under the "Pending publish" filter in the list; overview "Pending publish" count +1 | write-buffer acceptance + portal |
| W20 | After publish | Disappears from the buffered filter; appears under "Published" | Indirect |

---

## 5. Votes list `/ui/me/votes/` (V series)

| ID | Condition | Expectation | Automation |
|----|------|------|--------|
| V1 | GET | filter-pills (All/Upvoted/Downvoted), list-footer; **no** checkbox, **no** batch bar | `test_votes_page_has_filter_and_footer` |
| V2 | After voting | List contains a link to the record's problem | `test_votes_after_feedback` |
| V3 | Sortable headers | **R1**: time/vote/library are clickable links | `test_votes_sort_headers_are_links` |
| V4 | No subnav | Same as W series | Same as above |

---

## 6. Libraries `/ui/libraries/` (L series)

| ID | Condition | Expectation | Automation |
|----|------|------|--------|
| L1 | Logged-in GET list | 200; table columns: library name / visibility / permission / role | portal tests |
| L2 | GET detail | **Stats only** — no record enumeration table | `test_anonymous_public_library_stats`, etc. |
| L3 | Anonymous GET public library | 200 stats; minimal header | Same as above |
| L4 | Non-public library | Requires login | `test_private_library_requires_login` |

---

## 7. Record detail `/ui/records/{id}/` (D series)

| ID | Condition | Expectation | Automation |
|----|------|------|--------|
| D1 | active + entitlement | 200; voting form available | portal / feedback tests |
| D2 | buffered + owner | Shows publish/edit/delete action area | write-buffer acceptance |
| D3 | buffered + non-owner | **404** (existence oracle) | integration |
| D4 | No entitlement | 404 | portal tests |

---

## 8. API Keys `/ui/keys/` (K series — summary)

Full detail in [v1-api-key-lifecycle.md](v1-api-key-lifecycle.md).

| ID | Condition | Expectation | Automation |
|----|------|------|--------|
| K1 | Not logged in, GET | 302 login | onboarding tests |
| K2 | List | Copy + Delete (not "Revoke") | `test_self_service_onboarding.py` |
| K3 | POST delete | 303 back to list; key immediately 401 | Same as above |

---

## 9. Mapping to historical P1–P19

| Historical | New ID |
|------|-------|
| P1 | N1, N6 |
| P2 | M1–M5 |
| P3 | W1–W4, V1–V4 |
| P4–P7 | L*, D* |
| P8–P11 | N7, boot-time validation |
| P12 | Visual tokens (code review) |
| P13 | M3 |
| P14 | W5–W6, R1 |
| P15 | W13–W18, R3 |
| P16 | onboarding unit |
| P17 | W3–W4 |
| P18 | V1–V4 |
| P19 | N3–N5 |

**New (2026-07-06)**: R1–R5, W11–W15, W13 (select-all)

---

## 10. Release-gate command

```bash
cd code/server
.venv/bin/pytest \
  tests/integration/test_user_portal.py \
  tests/integration/test_user_portal_nav.py \
  tests/integration/test_user_portal_writes.py \
  tests/integration/test_user_portal_votes.py \
  tests/integration/test_portal_html_regression.py \
  tests/integration/test_display_name_registration.py \
  -q --tb=short
```

After deploying to 202, additionally run:

```bash
bash deploy/common/verify_ma3.sh
# Optional: run e2e_authing_ui.py when AUTHING_TEST_USER/PASS are set
```

---

## 11. Owner visual checklist (L4 — 5-minute spot-check per release)

- [ ] `/ui/me/writes/?status=buffered`: header "Time ↓" is **clickable**, not plain text
- [ ] Deselect all → batch publish: inline yellow warning, **not** a JSON page
- [ ] Header select-all: checks/unchecks buffered rows on this page
- [ ] `/ui/me/writes/?status=deleted`: Record column shows "Record content fully deleted, cannot be displayed"
- [ ] Top bar's five items are peers; Records/Votes pages have **no** account subnav
- [ ] `/ui/me/settings/`: Principal ID is read-only, no copy button

---

## 12. Known non-blocking nits

1. Batch action bar still shows with zero rows — acceptable for v1.
2. The "Record" column does not support DB-level sorting — deferred per design/19.
3. TestClient does not exercise a real Authing browser flow — covered by `e2e_authing_ui.py`.
