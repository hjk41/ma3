# Self-Service Onboarding

> Chinese version: [getting-started.zh.md](getting-started.zh.md)

> **ADR**: [ADR-011](../02-architecture/decisions/011-kb-access-and-org-isolation.md) (personal-dev slice)  
> **Prerequisites**: [authorization-and-libraries.md](../03-backend/authorization-and-libraries.md), [writes-audit-and-deletion.md](../03-backend/writes-audit-and-deletion.md)  
> **Status**: design finalized (2026-07-04); key lifecycle in [api-keys-ui-and-api.md](../04-frontend/api-keys-ui-and-api.md)  
> **Acceptance**: [acceptance-criteria.md](../08-quality/acceptance-criteria.md) (`v1-self-service-onboarding` to be migrated in)

---

## 1. Goals

| Goal | Description |
|------|------|
| **Zero-admin registration** | A new individual developer goes from "discovering ma3" to "holding a usable API key" fully self-service |
| **Auto-create library on first login** | First Authing login creates a personal library (`kind=personal`), idempotently |
| **Self-service key issuance** | `/ui/keys/` create/list/**delete** keys; default grants = personal writer + `lib_default` writer |
| **Re-displayable plaintext** | Plaintext key stored encrypted (`key_ciphertext`); the owner can copy it repeatedly from list/detail (see design/14) |
| **Minimal diff** | Reuse `ensure_library` / `insert_api_key` / `resolve_api_key`; v1 does not introduce a full entitlement service |

**v1 slice / v1.1 split**:

- **v1**: auto library on first login + `/api/keys` REST + `/ui/keys/` UI + friction #2/#3 quick fixes + docs/deployment updates
- **v1.1**: `ma3_create_key`/`ma3_list_keys` MCP tools, custom grants picker UI, org member path, entitlement read-only coupling, Stripe

---

## 2. Decisions

### D1 — First-login hook lives in the Authing callback; idempotency via owner lookup

`ensure_personal_library(principal_id, display_name)` is called in `auth_callback` right after `ensure_user_principal`.

- **Idempotency key**: `(kind='personal', owner_principal_id)` — `find_personal_library` first; return on hit
- New library_id: `lib_personal_{sha256(principal_id).hexdigest()[:12]}`
- Concurrent first logins hitting a PK conflict → except, then re-find
- Fallback: `GET /ui/keys/` and `POST /api/keys` each also call it once (lazy backfill)

### D2 — v1 key creation only via Observatory (Bearer session); MCP issuance deferred to v1.1

Rationale: Bearer is UI-only; the MCP data path only accepts `X-API-Key`; the bootstrap scenario requires a human in the UI anyway; the privilege-persistence attack surface of a leaked key needs entitlement checks (Phase 3).

### D3 — v1 grants: personal-dev template + grant picker (design/14 evolution)

Default grants on key creation:

```python
[
    {"library_id": personal_lib_id, "role": "writer"},
    {"library_id": settings.default_library_id, "role": "writer"},
]
```

Free tier: **Community Library writer is locked**; paid principals may customize Community down to reader. Custom org library grants in v1.1.

### D4 — Plaintext key storage and display (design/14 revision)

- On creation, generate plaintext; store `key_hash` + Fernet `key_ciphertext`
- **List/detail can repeatedly display** plaintext (when decryption succeeds) + copy button
- Legacy rows without ciphertext: show prefix only, guide to "create a new key and delete the old one"
- `GET /api/keys` contains no hash/ciphertext fields

### D5 — Delete = hard row delete (design/14 supersedes the earlier "revoke" design)

- User-facing wording is uniformly **delete**, not "revoke/revoked"
- `DELETE /api/keys/{key_id}` + `POST /ui/keys/{key_id}/delete` (SSR form)
- Delete `api_key_grants` first, then the `api_keys` row; `write_audit_log` does **not** cascade
- Legacy `revoked_at` rows: filtered from lists (`revoked_at IS NULL`), excluded from quota, can no longer authenticate
- **No** 410 bridge on revoke routes (not publicly launched)

### D6 — friction #2/#3 quick fixes

- Missing `confirmation` → defaults to `agent_judged`, no longer 400; schema description explicitly says "do not ask the user for it"
- `ma3_report` response echoes `library_selection_reason`

---

## 3. User Journey

```mermaid
flowchart TD
  A[Visit ma3] --> B[/ui/keys/ or top-bar API Keys]
  B -->|no session| C[302 /auth/login?next=/ui/keys/]
  C --> D[Authing sign-up/login]
  D --> E[/auth/callback: ensure_user_principal + ensure_personal_library]
  E --> F{display_name_locked?}
  F -->|no| G[/ui/me/setup/ set display name]
  F -->|yes| H[/ui/keys/ list]
  G --> H
  H --> I[Create key → copy plaintext]
  I --> J[Configure MCP X-API-Key]
  J --> K[ma3_whoami + ma3_report]
```

---

## 4. Data Model Changes

**Additive columns**:

```sql
ALTER TABLE api_keys ADD COLUMN key_prefix TEXT;
ALTER TABLE api_keys ADD COLUMN key_ciphertext TEXT;
```

**db.py helpers**:

| Function | Description |
|------|------|
| `find_personal_library(owner_principal_id)` | look up personal library by owner |
| `list_api_keys_for_principal(principal_id)` | includes grants; **`AND revoked_at IS NULL`**; excludes hash |
| `delete_api_key(key_id, *, principal_id)` | hard-delete grants + key row |
| `update_api_key_label(...)` | label only |
| `count_active_api_keys(principal_id)` | quota (`revoked_at IS NULL`) |

Config: `MA3_MAX_KEYS_PER_PRINCIPAL`, default **10**.

---

## 5. REST API

Auth: Authing session (`_require_session`); mutating routes same-origin; **X-API-Key not accepted**.

| Method/Path | Description |
|-----------|------|
| `GET /api/keys` | list; includes `plaintext_key` (when decryption succeeds) |
| `POST /api/keys` | create; response includes `plaintext_key` |
| `PATCH /api/keys/{key_id}` | change label; JSON over 120 chars → **422** (SSR form still truncates) |
| `DELETE /api/keys/{key_id}` | hard delete; not owner → 404 |
| `POST /ui/keys/create` | SSR create → 303 `/ui/keys/` |
| `POST /ui/keys/{key_id}/edit` | SSR change label + grants (unified form on detail page) |
| `POST /ui/keys/{key_id}/delete` | SSR delete → **always** 303 `/ui/keys/` (regardless of rowcount) |

---

## 6. MCP Changes (v1)

**No new MCP issuance tools** (D2). Existing tools enhanced:

- `ma3_report`: `library_selection_reason` + confirmation defaulting
- `ma3_whoami`: naturally returns dual-library capabilities

**Reserved for v1.1**: `ma3_create_key` (grants ⊆ caller key grants; dev bypass disabled), `ma3_list_keys`.

---

## 7. Errors and Edge Cases

| Scenario | Behavior |
|------|------|
| Authing not configured | `/ui/keys/`, `/api/keys` → **503**; dev uses `MA3_DEV_AUTH=1` |
| Personal lib already exists (seed-created) | reused by owner, not renamed |
| Over quota | 400: `active key limit reached; delete an old key first` |
| MCP after deletion | `resolve_api_key` → None → 401 / -32001 |
| Callback library creation fails | **does not block login**; log error; `/ui/keys/` lazy fallback |
| **No** `ma3_ui_session` anonymous-cookie key signing | onboarding security constraint |

---

## 8. Docs and Deployment

The "API Key" section of `code/client/agent-onboarding.md` is rewritten as the self-service flow (browser `/ui/keys/` → Authing → copy key → MCP config).

The deploy bundle **must include** `server/scripts/seed_personal_library_key.py` (admin fallback when Authing is unavailable).

---

## 9. Related Documents

| Document | Relation |
|------|------|
| [api-keys-ui-and-api.md](../04-frontend/api-keys-ui-and-api.md) | source of truth for key delete/rename/layout |
| [display-name-registration.md](../04-frontend/display-name-registration.md) | first-login setup gate |
| [authorization-and-libraries.md](../03-backend/authorization-and-libraries.md) | full ACL picture |
| [writes-audit-and-deletion.md](../03-backend/writes-audit-and-deletion.md) | confirmation semantics |
