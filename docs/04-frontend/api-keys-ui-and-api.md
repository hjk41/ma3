# 14 — API Key Lifecycle Management

> Chinese version: [api-keys-ui-and-api.zh.md](api-keys-ui-and-api.zh.md)

> **ADR**: [ADR-011](../02-architecture/decisions/011-kb-access-and-org-isolation.md)  
> **Prerequisite**: [13-self-service-onboarding.md](../05-agent/getting-started.md)  
> **Status**: Finalized (2026-07-04); acceptance see [acceptance-criteria.md](../08-quality/acceptance-criteria.md) (`v1-api-key-lifecycle` to be migrated in)

---

## 1. Goals and Non-Goals

### Goals

| Goal | v1 decision |
|------|---------|
| Self-service management | Manage your own keys at `/ui/keys/` after signing in with Authing |
| **Delete** replaces revoke | UI/REST unify on **delete**; from the user's perspective the key stops working immediately and cannot be recovered |
| Understandable grants | A grant picker at creation time: personal + Community, each `reader`/`writer`/`none`; the free tier locks Community writer |
| Convenient copying | List/detail show the full key (`key_ciphertext` when decryption succeeds) + a copy button |
| Security boundary | Mutations: session must be same-origin; **a user's `X-API-Key` can manage that user's own keys** (cannot delete the key currently in use); a bootstrap key cannot manage keys |
| Small diff | Reuse existing table structure + SSR route pattern |

### Non-Goals (v1)

- Org-admin key management (v1.1+)
- Key rotation workflow (v1: create a new key → update config → delete the old key)
- Expiration policy UI (`expires_at` column exists but not exposed in the UI)
- Editing grants after creation (v1: create a new key, then delete the old one)
- Recovery after deletion

---

## 2. Operation Catalog

| Operation | v1 | UI | REST |
|------|-----|-----|------|
| Create | ✅ | `/ui/keys/` form + grant picker | `POST /api/keys` |
| View/List | ✅ | table | `GET /api/keys` |
| Copy | ✅ | `ma3CopyFrom` + hidden/offscreen input | list response `plaintext_key` |
| **Delete** | ✅ | inline `Delete` + confirm | `DELETE /api/keys/{key_id}` + `POST /ui/keys/{id}/delete` |
| Rename | ✅ | unified detail-page form | `PATCH /api/keys/{key_id}` |
| Edit grants | ✅ (creation time + unified save on detail page) | detail-page grant picker | detail `POST /ui/keys/{id}/edit` |
| Rotate / Expire | ❌ | — | — |

---

## 3. Delete vs Revoke (finalized)

**v1 uses hard delete**:

1. `DELETE /api/keys/{key_id}` deletes the `api_keys` row
2. Deletes `api_key_grants` in the same transaction
3. No longer shown in the list; no "revoked" status badge
4. **Does not** cascade to or rewrite `write_audit_log` (`api_key_id` is kept as a historical string)
5. **Removes** revoke routes such as `POST /api/keys/{id}/revoke` (no 410 bridge)

The `api_keys.revoked_at` column is retained for legacy/admin rows; the self-service UI **does not write** to this column. List SQL: `AND revoked_at IS NULL`.

Application log:

```text
api_key_deleted principal_id=user:... key_id=key_... key_prefix=ma3k_...
```

---

## 4. API Contract

All `/api/keys` routes require: portal auth is enabled (OIDC or `MA3_LOCAL_AUTH`, otherwise 503); **session cookie or user `X-API-Key`**; session write operations must be same-origin; owner-only (someone else's/nonexistent → 404); **cannot delete the API key currently being used for the request**; bootstrap keys are forbidden.

### `GET /api/keys`

```json
{
  "keys": [
    {
      "key_id": "key_4f9c1d20ab30",
      "key_prefix": "ma3k_9f8e7",
      "label": "my-laptop-agent",
      "plaintext_key": "ma3k_9f8e7d6c5b4a3210fedcba9876543210",
      "grants": [
        {"library_id": "lib_personal_abc123", "library_name": "Alice's personal library", "role": "writer"},
        {"library_id": "lib_default", "library_name": "Community Library", "role": "writer"}
      ],
      "created_at": "2026-07-04T09:00:00+00:00",
      "last_used_at": null,
      "expires_at": null
    }
  ]
}
```

- Does not include `key_hash` / `key_ciphertext` / deleted keys
- `plaintext_key` may be `null` (legacy key with no ciphertext, or decryption failed)

### `POST /api/keys`

Request: `{"label": "...", "grants": [...]}` (grants optional, defaults to personal+Community writer)

| Case | Status | Detail |
|------|--------|--------|
| Missing/blank label | 200 | normalized to `agent-key` |
| Label over 120 chars (**JSON API**) | **422** | Pydantic `max_length=120` |
| Label over 120 chars (SSR form) | 200 | truncated |
| Free tier removes Community writer | 400 | `free tier requires Community Library writer grant` |
| Quota reached | 400 | `active key limit reached; delete an old key first` |

### `PATCH /api/keys/{key_id}`

Only changes `label`; blank → `agent-key`; JSON over 120 chars → 422.

### `DELETE /api/keys/{key_id}`

Response: `{"deleted": true, "key_id": "..."}`; non-owner → 404.

### SSR Routes

| Route | Method | Behavior |
|------|------|------|
| `/ui/keys/` | GET | list + create form |
| `/ui/keys/create` | POST | create → 303 `/ui/keys/` |
| `/ui/keys/{key_id}` | GET | detail |
| `/ui/keys/{key_id}/edit` | POST | unified save of label + grants → 303 to detail or list |
| `/ui/keys/{key_id}/delete` | POST | delete → **always** 303 `/ui/keys/` |

---

## 5. UI Layout

### 5.1 List page `/ui/keys/`

```
┌─ Key management ──────────────────────────────────────────────────────────┐
│ Name          Prefix      Grants           Last used   Actions      │
│ my-laptop     ma3_ab12…   Personal(rw),…   2026-07-03   [Copy] [Delete] │
│ ─────────────────────────────────────────────────────────────────── │
│ Label [my-laptop-agent      ] [Create new key]                          │
│ (grant picker: Community + personal)                                │
└─────────────────────────────────────────────────────────────────────┘
```

- **Actions column**: Copy (a hidden/offscreen `.copy-src` input placed **immediately before** the button, matching `ma3CopyFrom`'s `previousElementSibling` lookup) + Delete (inline form + `confirm`)
- Legacy keys with no plaintext: the copy button is **not rendered** (not just disabled)
- Delete copy: `Delete`; title: `Once deleted, this key stops working immediately and cannot be recovered.`

### 5.2 Detail page `/ui/keys/{key_id}`

```
API Keys / my-laptop                        ← breadcrumb

┌─ my-laptop ─────────────────────────────────────────────┐
│ Key  [ma3_xxxxxxxx...        ] [Copy]                    │  ← read-only, outside the form
│ Prefix / Created / Last used                             │
│ ─────────────────────────────────────────────────────── │
│ <form POST .../edit>                                     │
│   Label [my-laptop              ]                        │
│   Library permissions (grant picker)                     │
│   [← Back to list]                      [Save]           │  ← .form-footer
│ </form>                                                  │
│ ─────────────────────────────────────────────────────── │
│ ┌─ Danger zone ────────────────────────────────┐             │
│ │ Deleting this key disables it immediately.  [Delete key]  │  ← separate form │
│ └───────────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────┘
```

- **A single `<form>`** saves label + grants; delete is a separate `danger-zone` form (no nesting)
- The old `/label` and `/grants` endpoints have been merged into `/edit`

### 5.3 CSS Increments

`.btn.sm`, `.cell-actions`, `.copy-src` (offscreen), `.form-footer`, `.danger-zone`

---

## 6. DB Helper

```python
def delete_api_key(key_id: str, *, principal_id: str) -> bool:
    with connect() as conn:
        cur = _execute(
            conn,
            "DELETE FROM api_keys WHERE key_id = ? AND principal_id = ? AND revoked_at IS NULL",
            (key_id, principal_id),
        )
        if not getattr(cur, "rowcount", 0):
            return False
        _execute(conn, "DELETE FROM api_key_grants WHERE key_id = ?", (key_id,))
    return True
```

Quota:

```sql
SELECT COUNT(*) FROM api_keys WHERE principal_id = ? AND revoked_at IS NULL;
```

---

## 7. Errors and Edge Cases

| State | UI | API |
|------|-----|-----|
| Authing not configured | 503 explanation page | 503 JSON |
| No session | 302 login | 401 |
| Missing Origin/Referer (mutation) | error message | 403 |
| Delete someone else's key | 303 back to list (no difference shown) | 404 |
| Legacy revoked row | does not appear in list | does not appear in GET |
| Decryption failed | prefix + re-create guidance | `plaintext_key: null` |

---

## 8. Acceptance Points

- A1: new user self-service create → copy → `ma3_whoami` shows both libraries
- A2: UI has no `revoke`/`revoked`; the action is `delete`
- A3–A5: hard delete row + MCP immediate 401 + list excludes deleted keys
- A6: `write_audit_log` rows keep the original `api_key_id`
- A7: deletion frees up quota
- A8: someone else's key → 404
- A9: mutation with missing/incorrect Origin → 403
- A10: free tier locks Community writer
- A11: rename only changes the label
- A13: legacy `revoked_at` rows not in the list, not counted toward quota

---

## 9. Related Documents

- [13-self-service-onboarding.md](../05-agent/getting-started.md) — first-login library creation + self-service issuance slice
- [08-kb-access-and-org-isolation.md](../03-backend/authorization-and-libraries.md) — grants model
- [22-user-portal-ui-layout.md](information-architecture.md) §3.7 — top bar API Keys entry point
