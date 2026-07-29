# 17 — Display Name Registration Setup (display name registration)

> Chinese version: [display-name-registration.zh.md](display-name-registration.zh.md)

> **Status**: Implemented (2026-07-05)  
> **Implementation**: `principal_service.py`, `routes_auth.py`, `routes_portal.py`, `db.py`  
> **Acceptance**: [acceptance-criteria.md](../08-quality/acceptance-criteria.md) (`v1-display-name-registration` to be migrated in)

After a user registers/logs in with Authing for the first time, they must choose a **display name** (the portal-visible nickname) once at **`/ui/me/setup/`**. The display name is distinct from the Authing account nickname and the Principal ID.

---

## 1. Product Constraints

| ID | Constraint | Description |
|----|------|------|
| **C1** | **Prompted at registration** | After Authing's `/auth/callback` completes, if `display_name_locked=0`, redirect (302) to `/ui/me/setup/?next=…`; other portal pages and API Keys are unavailable until this is done |
| **C2** | **Can only be set once** | Once the user successfully submits the setup form, `display_name_locked=1`; after that, both setup POST and settings POST return 400 "Display name is already set and cannot be changed"; the settings page shows it read-only |
| **C3** | **Globally unique** | Display names for all `kind=user` principals are unique within ma3; comparison is **case-insensitive** (`lower(display_name)`); on conflict, returns "This display name is already taken, please choose another" |

### 1.1 Format Rules (setup validation)

- Length 2–32 characters (trim + collapse whitespace)
- Must not look like a uuid / Authing sub (`[0-9a-f]{20,}`)
- Must not contain control characters

### 1.2 Relationship with Principal ID

- **Principal ID** (`user:{sso_sub}`) is permanent and shown read-only on the **settings page** (no copy button)
- **Display name** is used in the top bar, personal library name (`{display_name}'s personal library`), and MCP `whoami.display_name`
- The **overview page** only shows the avatar + display name, **does not** show the Principal ID, and provides **no** edit entry point

---

## 2. User Flow

```
Authing register/login
    → /auth/callback (upsert principal, display_name=sso_sub, locked=0)
    → /ui/me/setup/ (welcome + form)
    → POST to set display name (validate uniqueness + format)
    → display_name_locked=1, rename personal library
    → next (default /ui/me/)
```

Visiting `/ui/me/`, `/ui/keys/`, etc. before completing setup → 302 to `/ui/me/setup/`.  
`GET /api/keys` → 403, with a detail message prompting to complete setup first.

---

## 3. Data and Implementation

| Item | Description |
|----|------|
| `principals.display_name` | The user-visible nickname |
| `principals.display_name_locked` | `0` = pending; `1` = locked |
| `idx_principals_user_display_name` | Partial unique index `lower(display_name) WHERE kind='user'` |
| `complete_display_name_setup()` | First-time set + lock + personal library rename |
| Startup migration | Existing users with `display_name <> sso_user` and length ≥ 2 are automatically set to `locked=1` |

Logging in again via Authing **does not** overwrite an already-locked display name; for unlocked users, upsert keeps `display_name` as the `sso_sub` placeholder.

---

## 4. Page Responsibilities

| Route | Responsibility |
|------|------|
| `/ui/me/setup/` | One-time setup after registration (form + constraint explanation) |
| `/ui/me/settings/` | Read-only display name + Principal ID (`.id-block`, mono, no copy) |
| `/ui/me/` | Overview (avatar + display name only, no edit link) |
