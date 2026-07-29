# 15 — User Portal

> Chinese version: [portal-permissions.zh.md](portal-permissions.zh.md)

> **Status**: Finalized (2026-07-04, product decision ratified)  
> **IA / layout source of truth**: [22-user-portal-ui-layout.md](information-architecture.md) (top bar, list shell, stat links)  
> **Visual source of truth**: [15-user-portal-visual.md](visual-design-system.md)  
> **Technical constraint**: SSR HTML (`ui_theme.py`), no SPA

---

## 0. One-Sentence Conclusion

The default landing page after login changes from `/ui/observatory/` to **`/ui/me/`** (personal home). Observatory keeps its original route but is downgraded to **product-administrator-only** (`is_admin` gated; non-admin → **403**). Regular users see "my library entitlements, records I've written, votes I've cast, API keys" — a **principal-centric** view.

---

## 1. Ratified Product Decisions

| # | Topic | **Decision** |
|---|------|----------|
| 1 | Non-admin accessing Observatory | **403 Forbidden** (not 302) |
| 2 | Authing enabled with an empty admin allowlist | **Refuse to boot**; LAN `authing_enabled=False` is not restricted |
| 3 | Library content visibility | Read entitlement → **Stats only**; cannot enumerate/modify/export; enumerate/modify/export → library admin or product admin |
| 4 | Anonymous visitors | **Stats for public libraries only** (`lib_default`); no record detail, no voting |
| 5 | `principal_id` | **v1: shown read-only at `/ui/me/settings/`** (no copy); not shown on the overview page |
| 6 | Display name | **Set once at `/ui/me/setup/`**; read-only in settings ([17](display-name-registration.md)) |
| 7 | Top bar IA | Home · **Libraries · Records · Votes · API Keys** (peer level) |
| 8 | Account subnav | `/ui/me/*` only: **Overview · Settings** |
| 9 | List page copy | h1 / stats: **Records, Votes** (not "My contributions / My votes") |
| 10 | Stat cards | 5 fully-clickable cards: Records, Pending, Accessible libraries, Votes, API Keys |
| 11 | Personal library name | `{display_name}'s personal library` |

---

## 2. Roles

| Role | Identity Determination | Core Needs |
|------|----------|----------|
| **Regular user (contributor)** | Authing session + principal | Library access, writes, voting, self-service keys |
| **Library admin** | `library_grants` maintainer/admin, or personal owner, or org admin | Manage library grants, review drafts (v1.1 UI) |
| **Org admin** | `org_members.role == admin` | Manage members, create org libraries (v1.1) |
| **Product admin** | `SessionUser.is_admin` | Global health overview (Observatory) |

Roles **stack**: a product admin is also a regular user; Observatory is just an extra nav item.

---

## 3. Route Tree

```text
/ui/me/                      Personal home ★ default landing
/ui/me/settings/             Account (read-only display name, Principal ID)
/ui/me/setup/                First-time display name (one-time, design/17)

/ui/me/writes/               Records list (top bar "Records")
/ui/me/votes/                Votes list (top bar "Votes")
/ui/records/{record_id}/     Single record detail + voting + buffer action area

/ui/libraries/               Libraries I have read entitlement for
/ui/libraries/{lib_id}/      Library detail — Stats only (non-admin)
/ui/libraries/{id}/settings/ Library buffer settings (owner)

/ui/keys/                    API key management (design/14)
/ui/keys/{key_id}            Key detail

/ui/observatory/             Product-admin only

[v1.1] /ui/orgs/*, /ui/libraries/{id}/records/, /ui/libraries/{id}/grants
```

- Record detail canonical URL: `/ui/records/{id}`; the old Observatory path 301-redirects
- Logo → `/ui/me/`; Authing callback without `next` → `/ui/me/`

---

## 4. Three Tiers of Library Content Capability (Stats / Enumerate / Mutate)

| Capability | Regular user (read entitlement) | Library admin | Product admin |
|------|------------------------------|----------|------------|
| **Stats** — aggregate numbers | ✅ | ✅ (their libraries) | ✅ globally (Observatory) |
| **Enumerate** — record/case listing, browse, search UI | ❌ | ✅ within their library | ✅ globally |
| **Mutate / Export** | ❌ | ✅ within their library | ✅ globally; Export v1.1+ |

Regular users **cannot** browse the record list within a library in the UI; they can only see Stats, and open a single record detail via the "Records / Votes" lists or a known record ID deep link.

**v1 read entitlement heuristic**: `union of personal library ∪ lib_default ∪ active key grants`; v1.1 will replace this with an entitlement resolver, **the API signature stays the same**.

---

## 5. Page Overview

For detailed wireframes and query contracts, see [22-user-portal-ui-layout.md](information-architecture.md).

| Page | Key points |
|------|------|
| `/ui/me/` | avatar + display name; 5 clickable stats; my libraries table; recent contributions |
| `/ui/me/settings/` | read-only display name + Principal ID (no copy) |
| `/ui/me/writes/` | sort/filter/per_page/batch (buffered); h1 "Records" |
| `/ui/me/votes/` | sort/filter/per_page; changing a vote only from record detail |
| `/ui/libraries/{id}/` | Stats cards + my access; **no** record table |
| `/ui/records/{id}/` | requires login + read entitlement; buffered, non-author → 404 |
| `/ui/observatory/` | non-admin → 403 HTML + "Back to my home" |

**Anonymous** access to `lib_default`: Stats cards + CTA "Sign in to contribute and vote"; no record detail.

---

## 6. Role Visibility Matrix

| Page / Entry | Regular user | Library admin | Product admin |
|---|---|---|---|
| `/ui/me/*` | ✅ | ✅ | ✅ |
| `/ui/keys/*` | ✅ | ✅ | ✅ |
| `/ui/records/{id}` | ✅ single record | ✅ | ✅ |
| `/ui/libraries/{id}/` Stats | ✅ | ✅ | ✅ |
| `/ui/libraries/{id}/records/` enumerate | ❌ | ✅ | ✅* |
| `/ui/libraries/lib_default/` anonymous Stats | ✅ | — | — |
| `/ui/observatory/` | ❌ **403** | ❌ **403** | ✅ |

\* Product admin (`is_admin`) does **not** automatically get org/library business management permissions; global observability and business management are separate.

**Direct URL access without entitlement** → 404 (does not leak resource existence).

---

## 7. v1 vs v1.1

### v1 (existing tables are sufficient)

- `/ui/me/` + writes + votes + settings
- `/ui/libraries/` + Stats-only detail + anonymous public Stats
- Refuse to boot with an empty admin allowlist
- Observatory 403 + record URL migration
- Write buffer UI (design/16)
- Display name setup (design/17)

**Not in v1**: record/case enumeration UI (non-admin); export; orgs; grants management page; community browse/search UI.

### v1.1

- `/ui/orgs/*`, `/ui/libraries/{id}/grants`, `/ui/libraries/{id}/records/`
- Entitlement resolver replaces the heuristic
- URL cleanup: `/ui/records/`, `/ui/votes/`
- Settings page Principal ID copy (optional)

---

## 8. Data Dependencies

### Already exists

`list_write_audit_for_principal`, `get_feedback_summaries`, `list_api_keys_for_principal`, `get_record`, `SessionUser.is_admin`.

### New v1 helpers

| Helper | Description |
|--------|------|
| `count_write_audit_for_principal` | Stat cards + pagination |
| `list_feedback_for_principal` | Votes list |
| `count_feedback_for_principal` | Stat cards |
| `list_entitled_libraries_for_principal` | v1 heuristic union |
| `get_library_stats(library_id)` | Stats-only page |
| `assert_admin_configured()` | Authing on and admin allowlist non-empty |

### Routes

- `routes_portal.py`: `/ui/me/*`, `/ui/libraries/*`, `/ui/records/*`
- Reuses `routes_keys.py`'s session gating and `_assert_same_origin`

---

## 9. Five Implementation Rules

1. After login, all entry points converge to `/ui/me/`.
2. Parameterizing `render_page`'s navigation is the first PR.
3. Records move to `/ui/records/{id}`, old paths 301, feedback POST migrates along with it.
4. Admin capability and `is_library_admin` / org role are determined by a **single source of truth**; UI and routes share it.
5. v1 does not render org UI; `list_entitled_libraries_for_principal`'s signature is locked, v1.1 only swaps the implementation.

---

## 10. Acceptance

See [acceptance-criteria.md](../08-quality/acceptance-criteria.md) (`v1-user-portal` P1–P19 to be migrated in).
