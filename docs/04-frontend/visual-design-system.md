# 15 — User Portal Visual Design (GitHub Light Style)

> Chinese version: [visual-design-system.zh.md](visual-design-system.zh.md)

> **Status**: Finalized (2026-07-04)  
> **Navigation/subnav source of truth is [22-user-portal-ui-layout.md](information-architecture.md)**  
> **Implementation source of truth**: `code/server/app/api/ui_theme.py` (`MA3_CSS` + `render_page`)  
> **Permission model**: [15-user-portal.md](portal-permissions.md)

Modeled on the **light** interface of GitHub.com / GitHub Settings / Personal Access Tokens: dark top bar, white content area, 6px border radius, thin-bordered tables, blue primary button.

---

## 1. Design Tokens (`:root` extension)

```css
--header-bg: #24292f;
--header-text: #f0f6fc;
--header-muted: #c9d1d9;
--canvas-default: #ffffff;
--canvas-subtle: #f6f8fa;
--border-default: #d0d7de;
--accent-fg: #0969da;
--danger-fg: #cf222e;
--page-max: 1012px;
--sidebar-width: 220px;
```

**Not doing**: dark mode, icon fonts, external CSS/JS frameworks.

---

## 2. Page Shell

```
┌─ .topbar (#24292f) ─────────────────────────────────────────────┐
│ [brand→/ui/me/]  .topnav  Home | Libraries | Records | Votes | API Keys | Observatory* │
│                                    * .nav-admin de-emphasized color, is_admin only      │
│                              .topbar-meta  display name · account · sign out          │
└────────────────────────────────────────────────────────────────┘
┌─ .page (max-width 1280; inner .page-narrow max 1012 on portal pages) ──────┐
│ .breadcrumb (second level and below)                                          │
│ .page-header: .page-title + .page-subtitle | .actions            │
│ body                                                             │
│ .footer                                                          │
└──────────────────────────────────────────────────────────────────┘
```

- **Observatory** nav item class `nav-admin`: `opacity:0.75; font-weight:400`
- Logo `href` fixed to `/ui/me/`

---

## 3. Layout Patterns

### 3.1 Default Single Column (List / Detail)

`.page-narrow` wraps the main content; `.card`s stack, 16px spacing.

### 3.2 Account Subnav (`/ui/me/*` only)

```html
<nav class="subnav-links">
  <a class="active" href="/ui/me/">Overview</a>
  <a href="/ui/me/settings/">Settings</a>
</nav>
```

CSS: `border-bottom:1px solid var(--border-default)`; active item `border-bottom:2px solid #fd8c73; font-weight:600`.

**Not used in v1**: two-column sidebar layout (the "My contributions / My votes" subnav has been retired).

---

## 4. Component Catalog → CSS Class

| Component | Class | Description |
|------|-------|------|
| Profile header | `.profile-header` | avatar + display_name (no Principal ID on overview page) |
| Principal ID | `.id-block` | **settings only**, read-only; mono; no copy |
| Clickable stat | `a.stat-card-link` | design/22; 5 stat cards |
| List item (activity feed) | `.list-group` > `.list-item` | title link on the left + meta time on the right |
| Table | `table.data` in `.table-wrap` | existing |
| Filter | `.filter-pills` | list page status/vote filter |
| List footer | `.list-footer` | total N items + per_page + pagination |
| Empty state | `.empty` + `.empty-icon` + `.empty-cta` | CTA uses `.btn.primary` |
| 403 | `.page-403` | centered; link `.btn` |
| Pagination | `.pagination` | flex; `.pagination .current` |
| Badge | `.badge.*` | existing |
| Danger | `.danger-zone` | keys detail delete area |
| Copy | `.copy-src` + `.btn.sm` | keys list/detail; offscreen input |

### `.profile-header` (overview / settings)

```html
<div class="profile-header">
  <div class="profile-avatar" aria-hidden="true">{initial}</div>
  <div class="profile-body">
    <h2 class="profile-name">{display_name}</h2>
  </div>
</div>
```

**The overview page does not include** `profile-meta`, Principal ID, `ma3CopyFrom`, or an edit display name link.

---

## 5. Per-Page Wireframes and Class Mapping

### `/ui/me/`

- `.profile-header` (avatar + display name only)
- `.subnav-links` (Overview active)
- `.grid.stats` ×5 (`a.stat-card-link`)
- `.card` "My libraries" → `table.data` (≤5 rows)
- `.card` "Recent contributions" → `.list-group` or compact table

### `/ui/me/writes/` `/ui/me/votes/`

- **No subnav** (top bar highlighted instead)
- `.filter-pills` + `.card` + `table.data` + `.list-footer`

### `/ui/libraries/{id}/`

- `.breadcrumb`
- `.grid.stats` (Cases / Records / Active / Draft / Invalid)
- `.card` "My access" `.kv` (logged-in user)
- Anonymous: `.alert.info` CTA "Sign in to contribute and vote"

### `/ui/records/{id}`

- `.breadcrumb`: `Home / Record vk_…`
- Buffer action `.card` (owner + buffered)
- `.split` two cards (record + feedback)

### `/ui/keys/*`

- design/14 layout; `active_nav=keys`

### Observatory 403

```html
<div class="page-403">
  <h1>403</h1>
  <p>Observatory is accessible only to product administrators.</p>
  <a class="btn" href="/ui/me/">Back to my home</a>
</div>
```

---

## 6. Navigation Parameterization

```python
def portal_nav_items(base: str, *, is_admin: bool) -> list[tuple[str, str, str, bool]]:
    items = [
        ("me", "Home", f"{base}/ui/me/", False),
        ("libraries", "Libraries", f"{base}/ui/libraries/", False),
        ("records", "Records", f"{base}/ui/me/writes/", False),
        ("votes", "Votes", f"{base}/ui/me/votes/", False),
        ("keys", "API Keys", f"{base}/ui/keys/", False),
    ]
    if is_admin:
        items.append(("observatory", "Observatory", f"{base}/ui/observatory/", True))
    return items
```

`render_page(..., is_admin=False, active_nav="me")`

---

## 7. Responsive Design

- `@media (max-width: 768px)`: `.topnav` hides some labels; `.split` → single column; `.grid.stats` minmax 120px
- v1 **does not implement** a hamburger / kebab menu; `table-wrap` falls back to horizontal scroll

---

## 8. Explicitly Not Doing (v1)

- Dark mode, animations, toast, modal JS
- Client-side routing / hydration
- Library record enumeration list UI (non-admin)
- Org sidebar
- Overview page Principal ID / edit display name

---

## 9. CSS Increment Budget

Roughly **120 lines** or fewer of new CSS: `.profile-*`, `.subnav-links`, `.list-group`, `.list-item`, `.page-403`, `.pagination`, `.page-narrow`, `.nav-admin`, `.empty-cta`, `.stat-card-link`, `.filter-pills`, `.list-footer`, `.id-block`, `.copy-src`, `.btn.sm`, `.cell-actions`, `.form-footer`, `.danger-zone`.
