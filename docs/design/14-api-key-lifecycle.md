# 14 — API Key Lifecycle Management

> **ADR**: [ADR-011](../adr/011-kb-access-and-org-isolation.md)  
> **前置**: 13-self-service-onboarding, 10-write-audit-and-delete  
> **状态**: Product design draft for v1 self-service UI/API (2026-07-04)

---

## 1. Goals & Non-Goals

### Goals

| Goal | v1 decision |
|------|-------------|
| Make key management self-service | Personal developers manage their own keys at `/ui/keys/` after Authing login. |
| Replace revoke with delete | UI and REST expose **删除 / Delete**. From the user's perspective the key is gone immediately and cannot be used again. |
| Keep grants understandable | Creation keeps the existing per-library grant picker: personal library + Community Library, each `reader`/`writer`/`none`, with free-tier Community writer locked. |
| Preserve copy convenience | List continues to show the full key when `key_ciphertext` is available, with a copy button. |
| Keep security boundaries simple | Mutating routes require an Authing session and same-origin check; MCP/API-key auth cannot create, edit, or delete keys. |
| Make implementation small | Reuse `api_keys`, `api_key_grants`, encrypted plaintext storage, quota checks, and existing SSR route structure. |

### Non-Goals

| Non-goal | Reason |
|----------|--------|
| Organization admin key management | v1 is for the personal developer persona; org maintainers and team audit workflows are v1.1+. |
| Key rotation workflow | Rotation needs two active keys, migration guidance, and optional delayed delete. For v1, users create a replacement key and delete the old key manually. |
| Expiration policy UI | `expires_at` exists in storage but is not exposed until ma3 has a clearer default rotation policy. |
| Fine-grained scopes beyond libraries | ADR-011 grants are per-library `reader`/`writer`; no extra MCP-tool scopes in v1. |
| Recovery after delete | Delete is irreversible for active authentication material. Users can create a new key within quota. |

---

## 2. Operations Catalog

| Operation | v1? | UI | REST | Justification |
|-----------|-----|----|------|---------------|
| Create | Yes | Form on `/ui/keys/` with label and grant picker | `POST /api/keys` | Required for self-service onboarding. Uses Authing session, quota, personal library provisioning, hash + encrypted plaintext storage. |
| View/List | Yes | Table on `/ui/keys/` | `GET /api/keys` | Lets a developer understand which keys exist, what each can access, and when each was created/last used. |
| Copy | Yes | Minimal JS `navigator.clipboard.writeText(...)`; input remains selectable | Included via `plaintext_key` in list response when re-display is available | Matches current ma3 product choice: stored Fernet ciphertext allows repeated owner re-display. |
| Delete | Yes | `删除` button per key, confirm text in button/form copy | `DELETE /api/keys/{key_id}` plus HTML form fallback `POST /ui/keys/{key_id}/delete` | Replaces revoke vocabulary. User intent is "remove this key", not "suspend it". |
| Rename/Edit label | Recommend Yes | Inline single-key form or simple secondary page | `PATCH /api/keys/{key_id}` with `{"label": "..."}` | Low-risk usability improvement. Labels are metadata only and do not affect auth. Useful when users create `agent-key` then later identify the machine/project. |
| Edit grants | Recommend No for v1 | Not exposed after creation | Not exposed | Changing grants on a live key can surprise running agents. v1 users should create a new key with desired grants, update local config, then delete the old key. |
| Rotate | Recommend No for v1 | Not exposed | Not exposed | Rotation is a guided create-copy-test-delete journey. The primitive operations are enough for v1. |
| Expire | Recommend No for v1 UI/API | Not exposed | Not exposed | Storage can continue to honor `expires_at` for admin/seeded keys, but self-service should avoid half-designed lifecycle policy. |

### GitHub PAT Comparison

GitHub personal access tokens use scopes, optional expiration, and a **Delete** action in the UI. Once deleted, the token stops working and is not recoverable. ma3 v1 should mirror the user-facing model: keys have grants instead of GitHub scopes, and the action is Delete, not Revoke. The difference is that ma3 v1 intentionally supports owner re-display of plaintext keys via encrypted storage, while GitHub PATs are one-time-display.

---

## 3. Revoke vs Delete Decision

### Recommendation

Use **hard delete for v1 UI and REST**:

1. `DELETE /api/keys/{key_id}` removes the row from `api_keys`.
2. The delete helper also removes rows from `api_key_grants`.
3. `POST /ui/keys/{key_id}/delete` is the SSR HTML form endpoint and redirects back to `/ui/keys/`.
4. The list no longer shows deleted keys; the status badge becomes unnecessary for normal rows.

This is the simplest match for user intent. A personal developer who clicks 删除 expects the key to disappear, stop authenticating, and stop counting toward quota. Keeping a soft-deleted row named "revoked" creates UI confusion without adding v1 user value.

### Audit Logs

Do **not** cascade or rewrite `write_audit_log`.

`write_audit_log.api_key_id` remains a historical string. If the referenced `api_keys` row has been deleted, audit views should render:

| Field | Display |
|-------|---------|
| `api_key_id` | Original historical id, for example `key_ab12cd34ef56` |
| Key label/prefix | `Deleted key` or `已删除 key` when the row no longer exists |
| Principal | Preserved from `write_audit_log.principal_id` |

This keeps audit evidence durable while removing reusable authentication material and encrypted plaintext.

### Application Logs

Log deletion as an operational event:

```text
api_key_deleted principal_id=user:... key_id=key_... key_prefix=ma3k_...
```

Do not log the full plaintext key, hash, or `key_ciphertext`.

---

## 4. User Journeys

### Journey 1: First Key for a Personal Developer

1. Developer opens `/ui/keys/`.
2. If not logged in, ma3 redirects to `/auth/login?next=/ui/keys/`.
3. Authing callback ensures the principal and personal library exist.
4. `/ui/keys/` shows a create form:
   - label defaults to `my-laptop-agent`
   - Community Library grant defaults to writer and is locked for free-tier users
   - personal library grant defaults to writer
5. Developer submits the form.
6. Server creates `api_keys` row, encrypted `key_ciphertext`, and `api_key_grants`.
7. UI redirects back to the list, where the full key is visible and copyable.
8. Developer pastes the key into MCP config as `X-API-Key`.
9. `ma3_whoami` confirms writable libraries.

REST equivalent:

1. Browser session calls `POST /api/keys` with label and optional grants.
2. Response includes `plaintext_key`, `key_id`, `key_prefix`, label, grants, and personal library.
3. Client uses the plaintext as an MCP `X-API-Key`.

### Journey 2: Copy an Existing Key

1. Developer opens `/ui/keys/`.
2. Table shows each non-deleted key with full key value when `key_ciphertext` can be decrypted.
3. Developer clicks `复制`.
4. If clipboard JS fails, developer can select the readonly input manually.

REST equivalent:

1. Browser session calls `GET /api/keys`.
2. Response includes `plaintext_key` for keys with decryptable ciphertext.
3. Legacy keys without ciphertext return `plaintext_key: null` and should be recreated if the user needs the value.

### Journey 3: Delete a Leaked or Old Key

1. Developer opens `/ui/keys/`.
2. Developer identifies the key by label, prefix/full key, grants, and last-used timestamp.
3. Developer clicks `删除`.
4. ma3 performs a same-origin check, verifies ownership, deletes `api_key_grants`, then deletes `api_keys`.
5. ma3 redirects to `/ui/keys/` with the key gone.
6. Any subsequent MCP request with that key fails with the existing unauthenticated error.

REST equivalent:

1. Browser session calls `DELETE /api/keys/{key_id}` with `Origin` or `Referer`.
2. Server returns `{"deleted": true, "key_id": "..."}`.
3. `GET /api/keys` no longer includes that key.

### Journey 4: Rename a Key

1. Developer notices `agent-key` is too generic.
2. Developer changes the label to `workstation-wsl-agent`.
3. ma3 updates only `api_keys.label`.
4. The key string, grants, audit history, and last-used timestamp are unchanged.

REST equivalent:

1. Browser session calls `PATCH /api/keys/{key_id}` with `{"label": "workstation-wsl-agent"}`.
2. Server returns the public key payload for that key.

---

## 5. API Contract Changes

All `/api/keys` routes require:

- Authing session cookie, resolved by `resolve_session_user`.
- Authing configured; otherwise return `503`.
- Same-origin validation for mutating routes using `Origin` or `Referer`.
- Owner-only access; unknown and other-user `key_id` both return `404`.
- No `X-API-Key` authorization for lifecycle operations.

### `GET /api/keys`

Response `200`:

```json
{
  "keys": [
    {
      "key_id": "key_4f9c1d20ab30",
      "key_prefix": "ma3k_9f8e7",
      "label": "my-laptop-agent",
      "plaintext_key": "ma3k_9f8e7d6c5b4a3210fedcba9876543210",
      "grants": [
        {"library_id": "lib_personal_abc123", "library_name": "Alice 的个人库", "role": "writer"},
        {"library_id": "lib_default", "library_name": "Community Library", "role": "writer"}
      ],
      "created_at": "2026-07-04T09:00:00+00:00",
      "last_used_at": null,
      "expires_at": null
    }
  ]
}
```

Notes:

- Do not include `key_hash` or `key_ciphertext`.
- Do not include deleted keys.
- `plaintext_key` may be `null` for legacy rows without ciphertext or failed decrypt.

### `POST /api/keys`

Request:

```json
{
  "label": "my-laptop-agent",
  "grants": [
    {"library_id": "lib_personal_abc123", "role": "writer"},
    {"library_id": "lib_default", "role": "writer"}
  ]
}
```

Response `200`:

```json
{
  "key_id": "key_4f9c1d20ab30",
  "key_prefix": "ma3k_9f8e7",
  "label": "my-laptop-agent",
  "plaintext_key": "ma3k_9f8e7d6c5b4a3210fedcba9876543210",
  "grants": [
    {"library_id": "lib_personal_abc123", "role": "writer"},
    {"library_id": "lib_default", "role": "writer"}
  ],
  "personal_library": {
    "library_id": "lib_personal_abc123",
    "name": "Alice 的个人库",
    "visibility": "private",
    "kind": "personal",
    "owner_principal_id": "user:alice"
  }
}
```

Validation:

| Case | Status | Detail |
|------|--------|--------|
| Missing/blank label | `200` | Normalize to `agent-key`. |
| Label over 120 chars | `200` | Truncate to 120 chars, matching current behavior. |
| Unsupported library id | `400` | `unsupported library_id ...` |
| Free tier removes Community writer | `400` | `free tier requires Community Library writer grant; upgrade to customize` |
| No grants | `400` | `at least one library grant is required` |
| Quota reached | `400` | `active key limit reached; delete an old key first` |

### `PATCH /api/keys/{key_id}`

Request:

```json
{"label": "workstation-wsl-agent"}
```

Response `200`:

```json
{
  "key_id": "key_4f9c1d20ab30",
  "key_prefix": "ma3k_9f8e7",
  "label": "workstation-wsl-agent",
  "plaintext_key": "ma3k_9f8e7d6c5b4a3210fedcba9876543210",
  "grants": [
    {"library_id": "lib_personal_abc123", "library_name": "Alice 的个人库", "role": "writer"},
    {"library_id": "lib_default", "library_name": "Community Library", "role": "writer"}
  ],
  "created_at": "2026-07-04T09:00:00+00:00",
  "last_used_at": null,
  "expires_at": null
}
```

Validation:

- Same ownership behavior as delete.
- Blank label normalizes to `agent-key`.
- Overlong label truncates to 120 chars.
- Does not modify grants, plaintext, hash, expiry, or audit logs.

### `DELETE /api/keys/{key_id}`

Response `200`:

```json
{"deleted": true, "key_id": "key_4f9c1d20ab30"}
```

Behavior:

1. Verify Authing session and same-origin headers.
2. Find `api_keys` row by `key_id` and `principal_id`.
3. Delete grants.
4. Delete key row.
5. Log `api_key_deleted`.
6. Return `404` if not found or not owned by the session principal.

### SSR HTML Routes

| Route | Method | Behavior |
|-------|--------|----------|
| `/ui/keys/` | `GET` | List keys, create form, optional label edit controls, delete buttons. |
| `/ui/keys/create` | `POST` | Create key from form fields; redirect `303` to `/ui/keys/`. |
| `/ui/keys/{key_id}/label` | `POST` | Form fallback for rename; redirect `303` to `/ui/keys/`. |
| `/ui/keys/{key_id}/delete` | `POST` | HTML form fallback for delete; redirect `303` to `/ui/keys/`. |

Deprecation compatibility:

- Replace current `POST /api/keys/{key_id}/revoke` with `DELETE /api/keys/{key_id}` in v1.
- Replace current `POST /ui/keys/{key_id}/revoke` with `POST /ui/keys/{key_id}/delete`.
- No long-term alias is needed before public v1 launch. If existing tests or deployed UI need a short bridge, keep revoke routes returning `410 Gone` with detail `use DELETE /api/keys/{key_id}` for one release only.

---

## 6. DB Schema Changes If Any

No table is required. Change helper behavior from soft revoke to hard delete.

### Keep Existing Columns

`api_keys.revoked_at` can remain for backward compatibility with legacy/admin-created rows and existing resolver logic. New self-service UI/API should not write it.

Current table remains:

```sql
CREATE TABLE IF NOT EXISTS api_keys (
  key_id TEXT PRIMARY KEY,
  key_hash TEXT NOT NULL UNIQUE,
  principal_id TEXT NOT NULL,
  label TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  created_by TEXT,
  last_used_at TEXT,
  expires_at TEXT,
  revoked_at TEXT,
  key_prefix TEXT,
  key_ciphertext TEXT
);

CREATE TABLE IF NOT EXISTS api_key_grants (
  key_id TEXT NOT NULL,
  library_id TEXT NOT NULL,
  role TEXT NOT NULL,
  PRIMARY KEY (key_id, library_id)
);
```

### New DB Helpers

| Helper | Signature | Notes |
|--------|-----------|-------|
| `delete_api_key` | `(key_id: str, *, principal_id: str) -> bool` | Deletes `api_key_grants` first, then `api_keys`; returns false if not owned/found. |
| `update_api_key_label` | `(key_id: str, *, principal_id: str, label: str) -> dict \| None` | Updates only label and returns public row or `None`. |

Implementation sketch:

```python
def delete_api_key(key_id: str, *, principal_id: str) -> bool:
    with connect() as conn:
        row = _fetchone(
            conn,
            "SELECT key_id FROM api_keys WHERE key_id = ? AND principal_id = ?",
            (key_id, principal_id),
        )
        if not row:
            return False
        _execute(conn, "DELETE FROM api_key_grants WHERE key_id = ?", (key_id,))
        cur = _execute(conn, "DELETE FROM api_keys WHERE key_id = ? AND principal_id = ?", (key_id, principal_id))
    return bool(getattr(cur, "rowcount", 0))
```

### Quota Semantics

For v1 self-service quota, count rows that still exist and are not legacy-revoked:

```sql
SELECT COUNT(*) AS c
FROM api_keys
WHERE principal_id = ? AND revoked_at IS NULL;
```

Hard-deleted keys naturally stop counting.

---

## 7. UI Wireframes

### `/ui/keys/`

```text
┌─ ma3 / API Keys ─────────────────────────────────────────────────────┐
│ 管理 MCP 调用用的 API key；登录后可随时查看、复制、删除。              │
│                                                                      │
│ ┌ Key 管理 ────────────────────────────────────────────────────────┐ │
│ │ Label        Key                         Grants       Last used  │ │
│ │ my-laptop    [ma3k_9f8e7d6c...     ][复制] Community  2026-07-04 │ │
│ │                                           writer                 │ │
│ │                                           Personal writer        │ │
│ │              [label: my-laptop        ][保存]          [删除]    │ │
│ │                                                                  │ │
│ │ ─ 创建新 key ─────────────────────────────────────────────────   │ │
│ │ Label [my-laptop-agent                         ] [创建新 key]    │ │
│ │                                                                  │ │
│ │ 授权                                                             │ │
│ │ | 知识库                         | 权限                         │ │
│ │ | Community Library（公共知识库） | [读写 v]  免费账户不可取消   │ │
│ │ | Alice 的个人库                  | [读写 v]                     │ │
│ └──────────────────────────────────────────────────────────────────┘ │
│ ┌ 个人库 ──────────────────────────────────────────────────────────┐ │
│ │ lib_personal_abc123                                              │ │
│ │ Alice 的个人库                                                    │ │
│ │ private                                                          │ │
│ └──────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

### Delete Button Copy

| UI element | Copy |
|------------|------|
| Button | `删除` |
| Button title | `删除后此 key 将立即失效，无法恢复。` |
| Optional inline hint | `删除只移除 key；历史写入记录仍保留。` |

Avoid a JS confirm dialog for v1 unless the team already has a shared pattern. The button label and row context are sufficient for a personal developer tool; tests are easier with pure SSR forms.

### Empty State

```text
暂无 API key
创建第一把 key 后，把它填入 agent MCP 配置的 X-API-Key。
```

### Legacy Key Without Ciphertext

```text
ma3k_ab12… 
旧 key 无存储副本；如需复制完整 key，请创建新 key 后删除旧 key。
```

---

## 8. Error States & Edge Cases

| State | UI behavior | API behavior |
|-------|-------------|--------------|
| Authing not configured | `503` page explaining self-service key management is unavailable; mention dev break-glass/admin seed fallback. | `503` JSON detail. |
| No session | Redirect to `/auth/login?next=/ui/keys/`. | `401 {"detail": "authentication required"}`. |
| Missing `Origin` and `Referer` on mutation | Show error page or list with alert. | `403 {"detail": "origin or referer required for key management"}`. |
| Cross-origin mutation | Show generic forbidden page. | `403 {"detail": "cross-origin request rejected"}`. |
| Delete another user's key | Redirect back with no visible difference or show `not found`. | `404 {"detail": "key not found"}`. |
| Delete already-deleted key | Same as not found; idempotency is not required because the row is gone. | `404`. |
| Key used while deletion happens | Once `api_keys` row is deleted, hash lookup fails and MCP request is unauthenticated. |
| Legacy soft-revoked key exists | Do not show in `/ui/keys/` by default, or show as non-actionable only if needed for migration diagnostics. It must not authenticate. |
| Quota reached | Inline alert: `active key limit reached; delete an old key first`. | `400`. |
| `key_ciphertext` decrypt fails | Show prefix + recreate guidance; do not fail the whole page. | Return `plaintext_key: null`. |
| Label contains newlines | Normalize to spaces. | Normalize to spaces. |
| Label too long | Truncate to 120 chars. | Truncate to 120 chars. |
| Free user selects Community `reader` or `none` | Re-render form with free-tier error. | `400`. |
| Paid user selects Community `reader` or `none` | Allowed if at least one grant remains. | `200`. |
| Personal grant `none` and Community writer | Allowed for free users; useful for community-only agents. | `200`. |

---

## 9. Integration Test Matrix

| Test name | Setup | Action | Assertion |
|-----------|-------|--------|-----------|
| `test_api_keys_require_session` | Authing settings enabled, no session monkeypatch | `GET /api/keys`; `GET /ui/keys/` | API returns `401`; UI redirects to login. |
| `test_authing_disabled_returns_503` | `settings.authing_enabled = False` | `GET /api/keys`; `GET /ui/keys/` | Both return `503` with self-service unavailable copy. |
| `test_create_key_plaintext_listable` | Authing session monkeypatched; isolated DB | `POST /api/keys` with valid origin, then `GET /api/keys` | Response has `ma3k_` plaintext, `key_prefix`, no hash/ciphertext; list includes decryptable plaintext. |
| `test_create_key_requires_same_origin` | Authing session monkeypatched | `POST /api/keys` without `Origin`/`Referer`; repeat with bad origin | Both return `403`. |
| `test_create_key_with_default_grants` | Authing session, personal lib exists | `POST /api/keys` with label only | Grants include personal writer and `lib_default` writer. |
| `test_free_user_cannot_drop_community_writer` | Authing session, not paid | `POST /api/keys` with Community reader/none | Returns `400` free-tier detail. |
| `test_paid_user_can_customize_community_grant` | Authing session, principal in `paid_principal_ids` | `POST /api/keys` with Community reader | Returns `200`; stored grants reflect reader. |
| `test_update_key_label` | Create key for session user | `PATCH /api/keys/{key_id}` with new label and valid origin | Returns updated public payload; DB label changed; key still authenticates. |
| `test_update_key_label_owner_only` | Create key for user A, session user B | `PATCH /api/keys/{key_id}` | Returns `404`; label unchanged. |
| `test_delete_key_hard_deletes_row_and_grants` | Create key with two grants | `DELETE /api/keys/{key_id}` with valid origin | `api_keys` row missing; `api_key_grants` rows missing; `GET /api/keys` omits key. |
| `test_delete_key_blocks_mcp` | Create key, construct `McpClient` with plaintext | Delete key, call `ma3_whoami` | `api_key_service.resolve_api_key` returns `None`; MCP error code remains unauthenticated. |
| `test_delete_key_owner_only` | Create key for user A, session user B | `DELETE /api/keys/{key_id}` | Returns `404`; key still works for user A. |
| `test_delete_key_keeps_write_audit_history` | Create key, write record through MCP, capture `write_audit_log.api_key_id` | Delete key; query audit row | Audit row still exists with same `api_key_id` string. |
| `test_quota_frees_after_delete` | Set `max_keys_per_principal = 1`; create first key | Second create returns `400`; delete first; create second | Second post-delete create returns `200`. |
| `test_ui_create_key_form_post` | Authing session monkeypatched | Submit `/ui/keys/create` form | `303` to `/ui/keys/`; label and `ma3k_` visible. |
| `test_ui_delete_key_form_post` | Authing session; create key | `POST /ui/keys/{key_id}/delete` with `Referer` | `303`; next list omits key and button label says `删除`, not `撤销`. |
| `test_ui_rename_key_form_post` | Authing session; create key | `POST /ui/keys/{key_id}/label` | `303`; new label visible. |

### Optional Playwright E2E With `AUTHING_TEST_USER`

Extend `code/server/scripts/e2e_authing_ui.py`:

| Step | Action | Assertion |
|------|--------|-----------|
| Login | Navigate to `/ui/keys/`; authenticate via Authing test account | Land on keys page, not login. |
| Create | Fill label `e2e-authing-key`; submit create form | Label and `ma3k_` appear on list. |
| Copy affordance | Locate copy input/button | Input value starts with `ma3k_`; button exists. |
| Rename | Change label to `e2e-authing-key-renamed`; submit | Renamed label appears. |
| Delete | Click `删除` for renamed key | Row disappears; page does not contain renamed label. |
| Post-delete API check | Browser `fetch('/api/keys', {credentials:'include'})` | Deleted key id absent from JSON. |

Run this only when `AUTHING_TEST_USER` and related Authing test secrets are configured, matching the current optional E2E pattern.

---

## 10. Acceptance Criteria for Fable QA

| # | Criterion |
|---|-----------|
| A1 | A fresh Authing personal developer can open `/ui/keys/`, create a key, copy it, and use it for `ma3_whoami` without admin help. |
| A2 | The UI no longer shows `撤销` or `已撤销` for normal self-service keys; the destructive action is labeled `删除`. |
| A3 | `DELETE /api/keys/{key_id}` removes the `api_keys` row and all `api_key_grants` rows. |
| A4 | Deleted keys immediately fail MCP authentication. |
| A5 | Deleted keys do not appear in `GET /api/keys` or `/ui/keys/`. |
| A6 | Historical `write_audit_log` rows remain after key deletion and keep the original `api_key_id` string. |
| A7 | Key deletion frees quota for the principal. |
| A8 | Users cannot delete or rename another user's key; API returns `404` without leaking existence. |
| A9 | Mutating key routes reject missing or cross-origin `Origin`/`Referer`. |
| A10 | Free-tier users cannot create keys without Community Library writer; paid test principals can customize Community role. |
| A11 | Rename updates only key label; plaintext, hash, grants, and audit history are unchanged. |
| A12 | Optional Authing Playwright E2E passes when `AUTHING_TEST_USER` is configured. |

Passing A1-A12 means v1 has a complete, realistic API-key lifecycle for the personal developer persona: create, view, copy, rename, and delete.
