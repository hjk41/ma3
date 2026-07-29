# 22 — User Portal UI Features and Layout

> Chinese version: [information-architecture.zh.md](information-architecture.zh.md)

> **Status**: **Delivered** (2026-07-05)  
> **Acceptance**: [acceptance/v1-user-portal-ui.md](../08-quality/acceptance/v1-user-portal-ui.md) (R/W/V series + pytest gate)
> **Permission baseline**: [15-user-portal.md](portal-permissions.md)  
> **Visual**: [15-user-portal-visual.md](visual-design-system.md)

---

## 0. One-Sentence Conclusion

After logging in, ma3's UI is split into **two layers of navigation**:

1. **Top bar (resource management)** — Home · **Libraries · Records · Votes · API Keys** (peer-level items)
2. **Account subnav (`/ui/me/*` only)** — **Overview · Settings**

List-type pages (records, votes) share a **standard list shell**: filter pills → sortable table → batch action bar (records only) → `list-footer` (total N + items per page + pagination). Overview stat cards are fully clickable, acting as shortcuts into the top bar's sections.

**Technical constraint**: SSR HTML (`ui_theme.py`), no SPA.

---

## 1. Sitemap

```text
/ui/me/                      Overview dashboard ★ default landing
/ui/me/settings/             Account (read-only display name, Principal ID)
/ui/me/setup/                First-time display name (design/17, one-time)

/ui/libraries/               Library list
/ui/libraries/{id}/          Library detail (Stats only)
/ui/libraries/{id}/settings/ Library buffer settings (owner)

/ui/me/writes/               Records list (top bar "Records")
/ui/me/votes/                Votes list (top bar "Votes")
/ui/records/{id}/            Single record detail + voting + buffer action area

/ui/keys/                    API Keys list (design/14)
/ui/keys/{id}                Key detail

/ui/observatory/             Product admin (admin)
```

Reserved for v1.1: `/ui/orgs/*`, `/ui/libraries/{id}/records/`, URL cleanup for `/ui/records/` and `/ui/votes/`.

---

## 2. Global Shell (Page Shell)

### 2.1 Top bar `.topbar`

```
┌─ #24292f ──────────────────────────────────────────────────────────────┐
│ [ma3→/ui/me/]  Home | Libraries | Records | Votes | API Keys | Observatory* │
│                                              display name · account · sign out       │
└────────────────────────────────────────────────────────────────────────┘
* Observatory: is_admin only, class nav-admin
```

| key | label | href | active condition |
|-----|------|------|-------------|
| me | Home | `/ui/me/` | overview, setup |
| libraries | Libraries | `/ui/libraries/` | library list/detail/settings |
| records | Records | `/ui/me/writes/` | writes and query variants |
| votes | Votes | `/ui/me/votes/` | votes and query variants |
| keys | API Keys | `/ui/keys/` | keys list/detail |
| observatory | Observatory | `/ui/observatory/` | admin |

**Copy**: the Chinese label uses the character meaning "library" instead of the English loanword `Libraries`; `API Keys` stays in English.

### 2.2 Account subnav `.subnav-links`

Rendered **only** on `/ui/me/` and `/ui/me/settings/`:

| tab | href |
|-----|------|
| Overview | `/ui/me/` |
| Settings | `/ui/me/settings/` |

**Not** rendered on records/votes/libraries/keys pages.

### 2.3 Content Area

```
.page-narrow (max 1012px)
  .page-header: h1.page-title + .page-subtitle | .actions
  [filter-pills]          ← list pages
  .card > table.data      ← list/detail
  .list-footer            ← list page footer
  .footer
```

---

## 3. Page Specifications

### 3.1 `/ui/me/` — Overview (dashboard)

**subnav**: Overview active · **top bar**: Home active

| Section | Content |
|------|------|
| `.profile-header` | avatar + display name (no Principal ID, no edit link) |
| `.grid.stats` ×5 | **clickable** stat cards |
| card "My libraries" | ≤5 rows + "View all →" `/ui/libraries/` |
| card "Recent contributions" | ≤5 items + "View all →" `/ui/me/writes/` |

**Stat cards (5 total, each a full-card `<a class="stat-card-link">`)**:

| Label | href |
|------|------|
| Records | `/ui/me/writes/` |
| Pending | `/ui/me/writes/?status=buffered` |
| Accessible libraries | `/ui/libraries/` |
| Votes | `/ui/me/votes/` |
| API Keys | `/ui/keys/` |

A count of 0 remains clickable.

### 3.2 `/ui/me/settings/` — Account

**subnav**: Settings active

| card | content |
|------|------|
| Display name | read-only; set during setup at registration, cannot be changed |
| Principal ID | `.id-block` read-only, **no copy** |

### 3.3 `/ui/libraries/` — Libraries

**top bar**: Libraries active · **h1**: Libraries

Table: `Library name (link) | Visibility | Permission | Role` (Stats-only policy unchanged).

### 3.4 `/ui/me/writes/` — Records (standard list page)

**top bar**: Records active · **h1**: Records · **no subnav**

**Query contract**:

| Parameter | Default | Description |
|------|------|------|
| `page` | 1 | Page number |
| `per_page` | 50 | 10 / 25 / 50 / 100 |
| `sort` | `created_at` | Time, record, status, library, kind, key |
| `dir` | `desc` | asc / desc |
| `status` | all | all / active / buffered / deleted |

**Filter pills**: All · Published · Pending · Deleted

**Table columns**: □ (header **select all on this page** `#writes-select-all`, only buffered+owner rows have a checkbox) | Time | Record (link or deleted placeholder) | Status | Library | Kind | Key

**Deleted rows**: the "Record" column shows the fixed text **The record content has been fully deleted and cannot be shown** (`.card-muted`); the original problem text is not shown.

**Batch action bar**: Publish selected · Delete selected → `POST /ui/me/writes/batch`

- If no row is selected: an inline warning "Select at least one record first", or a 303 redirect back to the list with `error`; **must not** return a JSON `{"detail":...}`
- POST preserves the current `status/sort/dir/page/per_page` (hidden fields)

**list-footer**: total N items · per-page pill · previous/next page

### 3.5 `/ui/me/votes/` — Votes (standard list page)

**top bar**: Votes active · **h1**: Votes · **no subnav**

**Query**: `page`, `per_page`, `sort`, `dir`, `vote` (all/up/down)

**Filter pills**: All · 👍 Upvote · 👎 Downvote

**No checkboxes, no batch actions**; changing a vote only via `/ui/records/{id}/`

**list-footer**: same as the records page.

### 3.6 `/ui/records/{id}/` — Record detail

| Section | Condition |
|------|------|
| Buffer action card | status=buffered and owner: publish/edit/delete |
| Knowledge entry + Feedback | active can be voted on; non-author buffered → 404 |

### 3.7 `/ui/keys/` — API Keys

**top bar**: API Keys active

Layout source of truth: [14-api-key-lifecycle.md](api-keys-ui-and-api.md) §5 (list Actions copy/delete; detail unified save form + danger-zone).

---

## 4. Shared Components (`ui_theme.py`)

| Component | class / helper | Purpose |
|------|----------------|------|
| Clickable stat | `a.stat-card-link` | `render_stat_cards((label, value, href))` |
| Filter | `.filter-pills` | `render_filter_pills(items, base, query)` |
| Sortable table header | `th` + `<a>` | `render_sort_link` → `render_table` does **not** double-escape header HTML |
| List footer | `.list-footer` | `render_list_footer(page, total, per_page, query)` |
| Pagination | `.pagination` | preserves sort/filter/per_page query |

**Principle**: list UI is not hand-rolled in multiple places in `routes_portal.py`; the query allowlist restricts sortable columns to prevent SQL injection.

---

## 5. Data and Copy

| Item | Rule |
|----|------|
| Personal library name | `{display_name}'s personal library`; `ensure_personal_library` auto-syncs |
| Display name | design/17: set once during setup, read-only in settings |
| Library list subtitle | may keep "Shows statistics only; record enumeration is not available" |

---

## 6. Explicitly Not Doing (v1)

- SPA / client-side routing
- Non-admin **library record enumeration** UI
- Batch export
- Org management UI
- URL cleanup for `/ui/records/`, `/ui/votes/`
- Top bar hamburger / dedicated responsive work (v1 accepts flex wrapping)
- **Batch vote change** in the votes list
- Observatory localization
- Overview page Principal ID / edit display name
- subnav "My contributions / My votes"
- community browse/search UI

---

## 7. Reserved for v1.1

- `/ui/orgs/*`, entitlement resolver replaces the heuristic
- `/ui/libraries/{id}/records/` library-admin enumeration
- `/ui/libraries/{id}/grants`
- Export, URL cleanup, settings page Principal ID copy (optional)
