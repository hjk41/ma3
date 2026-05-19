# ma3 v3 — Multi-Library Access Control (Detailed Design)

Status: draft 2026-05-19
Companion to `auth-multi-library-overall-design.md`.
Target reader: the engineer (or codex-openai agent) who will implement and
deploy this change. Every section should be actionable; no hand-waving.

## 0. Implementation outline

1. Add new tables (`principals`, `api_keys`, `library_acl`, `auth_audit_log`)
   and their indexes via additive `CREATE TABLE IF NOT EXISTS` in
   `app/storage/db.py`. Do not touch the existing `tokens` / `libraries` /
   `invite_codes` tables.
2. Add `app/core/auth.py` with the new `ResolvedPrincipal`, the unified
   resolver (`resolve_principal`), the JWT verifier, and the FastAPI
   dependencies that replace `require_write_library_id` /
   `resolve_optional_token` / `require_admin_role` / `require_library_admin`.
3. Add `app/services/auth_service.py` with all principal/key/ACL business
   logic. Wire `app/storage/repositories.py` with
   `PrincipalRepository`, `ApiKeyRepository`, `LibraryAclRepository`,
   `AuthAuditRepository`.
4. Update every existing dependency call site to use the v3 helpers; keep
   the v3 helpers' return value shapes a superset of the v2 ones so
   service-layer code does not change semantics.
5. Add `app/api/routes_v3_auth.py` for `/v3/auth/*` and
   `/v3/libraries/{id}/acl/*`. Mount under `/`. Legacy `/libraries/*`
   stays in place and routes through the same back-end objects.
6. Add `server/scripts/migrate_v2_tokens_to_v3.py` (idempotent) and the
   admin-only bulk xyz-key issuance script.
7. UI: extend `routes_ui.py` with `/ui/me`, `/ui/libs`, `/ui/admin/keys`.
   Pages are server-rendered (same HTML helper layer as `/ui/overview`).
8. Tests: unit tests under `tests/unit/test_auth_*.py`, e2e under
   `tests/e2e/test_v3_auth_*.py`. The legacy auth test suite must
   continue to pass unmodified.
9. Cutover follows the standard `AGENTS.md` playbook plus a new
   pre-flip migration step. Traffic flip is gated on user confirmation.

## 1. Configuration

New env vars (read in `app/core/config.py`):

| name | default | meaning |
|---|---|---|
| `MA3_AUTH_JWT_SECRET` | unset → JWT disabled | HS256 secret shared with `auth.zhilicon.com`. Must be present in prod. |
| `MA3_AUTH_JWT_ISSUER` | `auth.zhilicon.com` | claim `iss` we accept (if claim present). |
| `MA3_AUTH_JWT_COOKIE` | `gateway_token` | cookie name. |
| `MA3_AUTH_JWT_LEEWAY_SECONDS` | `60` | clock skew tolerance. |
| `MA3_AUTH_KNOWN_LEAKED_SECRETS` | empty | comma-separated SHA-256 prefixes of secrets we refuse to use, mirroring the inferhub pattern. |
| `MA3_AUTH_ADMIN_USERS` | empty | comma-separated SSO usernames that are allowed to receive `admin_bypass` from the SSO cookie. The JWT `admin=true` claim alone is NOT sufficient; the username must also appear here. |

Existing `MA3_API_KEY` continues to be the admin break-glass. Behavior
unchanged.

`Settings.__post_init__` validates: if `MA3_AUTH_JWT_SECRET` is set, its
SHA-256 must not be in `MA3_AUTH_KNOWN_LEAKED_SECRETS`, and it must be ≥ 32
bytes. On dev SQLite, JWT secret can stay unset and SSO routes will reply
`503 sso_disabled`.

## 2. Database schema

All additions are `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT
EXISTS` so they are safe to re-apply on every startup (matching the
existing pattern in `db.py`).

### 2.1 `principals`

```sql
CREATE TABLE IF NOT EXISTS principals (
    principal_id TEXT PRIMARY KEY,        -- 'user:<name>' | 'service:<name>' | 'legacy:<token_id>'
    kind         TEXT NOT NULL,           -- 'user' | 'service' | 'legacy'
    display_name TEXT NOT NULL,
    sso_user     TEXT,                    -- nullable; for kind='user' equals JWT.user
    created_at   TEXT NOT NULL,
    is_admin     BOOLEAN NOT NULL DEFAULT FALSE,  -- mirrors JWT.admin at upsert time; never used for bypass
    metadata_json JSONB NOT NULL DEFAULT '{}'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_principals_sso_user
    ON principals(sso_user) WHERE sso_user IS NOT NULL;
```

`is_admin` is informational only — bypass authority comes from `MA3_API_KEY`
or the JWT `admin=true` claim at request-time, never from this column.

### 2.2 `api_keys`

```sql
CREATE TABLE IF NOT EXISTS api_keys (
    key_id        TEXT PRIMARY KEY,            -- 'akey_<base32>'
    key_hash      TEXT NOT NULL UNIQUE,        -- sha256 of raw secret
    principal_id  TEXT NOT NULL REFERENCES principals(principal_id),
    label         TEXT NOT NULL,
    scope_libraries JSONB,                     -- NULL = inherit principal's libs; otherwise JSON array of lib_ids
    created_at    TEXT NOT NULL,
    created_by    TEXT NOT NULL REFERENCES principals(principal_id),
    last_used_at  TEXT,
    expires_at    TEXT,
    revoked_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_api_keys_principal ON api_keys(principal_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_active
    ON api_keys(revoked_at) WHERE revoked_at IS NULL;
```

Key-format note: raw key = `ma3v3_<26 chars base32>`; the `ma3v3_` prefix
lets the resolver detect malformed legacy strings early.

`last_used_at` is opportunistically updated — at most once per minute per
key (compare-and-set so concurrent requests do not thrash the row).

### 2.3 `library_acl`

```sql
CREATE TABLE IF NOT EXISTS library_acl (
    library_id   TEXT NOT NULL REFERENCES libraries(library_id) ON DELETE CASCADE,
    principal_id TEXT NOT NULL REFERENCES principals(principal_id) ON DELETE CASCADE,
    role         TEXT NOT NULL CHECK (role IN ('reader','writer','admin')),
    granted_at   TEXT NOT NULL,
    granted_by   TEXT NOT NULL REFERENCES principals(principal_id),
    PRIMARY KEY (library_id, principal_id)
);
CREATE INDEX IF NOT EXISTS idx_acl_principal ON library_acl(principal_id);
```

### 2.4 `auth_audit_log`

```sql
CREATE TABLE IF NOT EXISTS auth_audit_log (
    audit_id     TEXT PRIMARY KEY,
    actor_principal_id  TEXT NOT NULL,
    action       TEXT NOT NULL,    -- 'key.issue' | 'key.revoke' | 'acl.grant' | 'acl.revoke' | 'principal.create' | 'principal.assume_admin'
    target_principal_id TEXT,
    library_id   TEXT,
    payload_json JSONB NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON auth_audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_actor       ON auth_audit_log(actor_principal_id);
```

SQLite mirror tables use `INTEGER` for booleans (matching the existing
`libraries.is_public` pattern) and store JSON as `TEXT`.

### 2.5 What we do NOT add

- No new column on `libraries` — visibility flags stay where they are.
- No FK from `records.library_id` to `library_acl` — visibility filter
  continues to be computed at query time.
- No changes to `tokens` / `invite_codes`.

## 3. Resolver: `app/core/auth.py`

Replaces the helpers in `app/core/security.py`. The latter remains as a
re-export shim for one release so external imports do not break.

```python
@dataclass(frozen=True, slots=True)
class ResolvedPrincipal:
    principal_id: str
    kind: str                                  # 'user' | 'service' | 'legacy' | 'admin' | 'anonymous'
    display_name: str
    via: str                                   # 'api_key' | 'sso_cookie' | 'admin_key' | 'anonymous'
    is_admin_bypass: bool
    api_key_id: str | None = None
    api_key_scope: frozenset[str] | None = None  # None => no scope narrowing

def resolve_principal(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
    cookie_token: str | None = Cookie(default=None, alias=settings.auth_jwt_cookie),
) -> ResolvedPrincipal: ...
```

Resolution order:

1. raw bearer/api-key present →
   a. matches `settings.api_key` → `kind='admin', is_admin_bypass=True, via='admin_key'`.
   b. matches a row in `api_keys.key_hash` (and not revoked/expired) →
      load owning principal; `api_key_scope = scope_libraries`.
      If the SSO cookie *also* names a different `user:` principal,
      raise 400 `auth_conflict` (signal misconfigured client).
   c. matches a row in legacy `tokens.token_hash` → resolve via the
      legacy principal `legacy:<token_id>` (created lazily on first
      hit if migration script hasn't run yet — covers dev).
   d. otherwise → 401 `auth_invalid`.
2. no raw key, cookie present → verify JWT; load/upsert
   `principal_id = "user:" + claims.user`.
   `is_admin_bypass = bool(claims.admin) and claims.user in settings.auth_admin_users`.
   ma3 does NOT trust `admin=true` on its own — the username must be in
   the ma3-owned allowlist `MA3_AUTH_ADMIN_USERS`. `via='sso_cookie'`.
3. nothing → `ResolvedPrincipal(kind='anonymous', via='anonymous', ...)`.

JWT verifier:

- HS256 only.
- Reject `alg=none`.
- Validate `exp` with leeway; reject if `nbf > now + leeway`; if `iss`
  claim is present, it must equal `settings.auth_jwt_issuer`.
- On decode failure: log and treat as anonymous (do not 401 — many
  endpoints are public). Legacy and admin paths are unaffected.

`PrincipalRepository.upsert_user(sso_user, display_name)` is the one
write path used by JWT resolution. It is `INSERT ... ON CONFLICT DO
UPDATE SET display_name=EXCLUDED.display_name, ...` so first-login is
race-safe.

### 3.1 FastAPI dependencies

These replace v2's `require_*` helpers. They are thin wrappers around
`resolve_principal` plus an ACL check.

| dep | behavior |
|---|---|
| `current_principal` | `Depends(resolve_principal)`. |
| `require_authenticated` | 401 if `kind == 'anonymous'`. |
| `require_library_read(library_id)` | 401 if anonymous and lib not public; 403 if no `reader+` grant. Returns role. |
| `require_library_write(library_id)` | 401/403 mirroring the above; role must be `writer` or `admin`. |
| `require_library_admin(library_id)` | role must be `admin` (or `is_admin_bypass`). |
| `require_global_admin` | `is_admin_bypass` required. |
| `effective_libraries(principal, role_at_least='reader')` | helper returning `dict[lib_id, role]` after applying public-library union and key scope intersection. |

`require_write_library_id` (the v2 name) is kept as a deprecated alias
that returns the single library to write into. For routes that ingest
without specifying a library (legacy `/agent/report`, etc.), it picks
the principal's *primary* library, where:

- legacy principal → its single ACL row.
- user principal → if exactly one writable library, that one; otherwise
  400 `auth_ambiguous_target_library` with a hint listing options.
- service principal → its single ACL row (admins script these explicitly).
- admin bypass → `None` (writes into the legacy/unassigned namespace,
  preserving v2 behavior).

This is the *only* place where v3 is allowed to refuse a request that v2
would have accepted, and it only triggers for clients that already had
multi-library access (i.e. a real upgrade case, not a regression for
single-library users).

## 4. Service layer

### 4.1 `auth_service.py`

```python
def create_user_principal(sso_user: str, display_name: str) -> Principal
def create_service_principal(name: str, *, actor: ResolvedPrincipal) -> Principal
def issue_api_key(principal_id, label, scope_libraries, expires_at,
                  *, actor: ResolvedPrincipal) -> ApiKeyIssued
def revoke_api_key(key_id, *, actor) -> None
def list_api_keys(principal_id) -> list[ApiKeyInfo]
def list_principal_libraries(principal_id) -> dict[lib_id, role]
def grant_library_access(library_id, principal_id, role, *, actor) -> None
def revoke_library_access(library_id, principal_id, *, actor) -> None
def list_library_acl(library_id) -> list[AclEntry]
def search_principals(prefix, limit=20) -> list[Principal]
```

All write methods emit one `auth_audit_log` row in the same transaction.

`issue_api_key` produces `ma3v3_<base32>` via `secrets.token_urlsafe`;
hashes; persists; returns `ApiKeyIssued{ raw, info }`. The raw is
returned to the route layer exactly once and never logged.

Rules enforced here (not in routes — routes are thin):

- A principal cannot grant a role they do not themselves hold on the
  library. Admin bypass and `service:` actors are exempt (admin can do
  anything; service principals do not call these APIs from outside).
- `legacy:` principals cannot be the *actor* on grants — they have no
  human owner. Routes that authenticate as legacy and try to grant
  return 403 `legacy_cannot_grant`.
- Scope narrowing on key issue: `scope_libraries` is intersected with
  the actor's effective libraries before persisting; if the intersection
  is empty, 400 `scope_empty`.

### 4.2 Library service changes

`accessible_library_ids(token, is_admin)` is renamed/wrapped by:

```python
def effective_library_ids(principal: ResolvedPrincipal) -> set[str]:
    return set(effective_libraries(principal).keys())
```

The old function stays as a deprecated alias delegating to the new one;
its argument shape is bridged by a thin adapter that converts a
`ResolvedToken` (which the old call sites still pass in some places into
the MCP path) into a `ResolvedPrincipal` by looking up
`legacy:<token_id>`.

### 4.3 MCP path (`services/mcp_tool_service.py`)

`McpAuthContext` becomes:

```python
@dataclass(slots=True)
class McpAuthContext:
    raw_present: bool
    principal: ResolvedPrincipal
    @property
    def readable_library_ids(self) -> set[str]: ...
    @property
    def writable_library_ids(self) -> set[str]: ...
    @property
    def caller_summary(self) -> dict[str, Any]: ...  # for ma3_whoami
```

`resolve_mcp_auth(raw)` collapses to:

```python
def resolve_mcp_auth(raw: str | None) -> McpAuthContext:
    principal = _resolve_from_raw_only(raw)  # no cookie path — MCP has no cookies
    return McpAuthContext(raw_present=bool(raw), principal=principal)
```

`ma3_whoami` payload gains a `libraries: [{library_id, role}]` array and
the principal block; existing fields stay. This is an *additive* schema
change for MCP — verified by `test_mcp_schema_alignment`.

## 5. Routes

### 5.1 New: `/v3/auth/*` (in `app/api/routes_v3_auth.py`)

| method/path | auth | body | returns |
|---|---|---|---|
| `GET /v3/auth/whoami` | any | — | `{principal, via, libraries:[{library_id, role, source: 'acl'|'public'|'scope'|'admin'}], api_key?, admin_bypass}` |
| `POST /v3/auth/keys` | authenticated | `{label, scope_libraries?, expires_at?}` | `ApiKeyIssued{ raw, info }` (raw once) |
| `GET /v3/auth/keys` | authenticated | — | `list[ApiKeyInfo]` (caller's own) |
| `GET /v3/auth/keys/all` | admin | — | all keys with principal summaries |
| `DELETE /v3/auth/keys/{key_id}` | owner OR admin | — | 204 |
| `GET /v3/auth/principals?prefix=&kind=` | authenticated | — | `list[PrincipalSummary]` (no SSO emails, no key metadata) |
| `POST /v3/auth/principals/service` | admin | `{name, display_name}` | `Principal` |
| `GET /v3/auth/audit?since=&actor=&action=&limit=` | admin | — | paged `list[AuthAudit]` |

### 5.2 New: `/v3/libraries/*`

| method/path | auth | semantics |
|---|---|---|
| `POST /v3/libraries` | authenticated | create library; creator gets `admin` ACL grant; payload identical to v2 minus `parent_library_id` (deferred); response includes the grant. |
| `GET /v3/libraries/{id}/acl` | library `reader+` | list ACL entries (no raw secrets). |
| `PUT /v3/libraries/{id}/acl/{principal_id}` | library `admin` or global admin | `{role}` → upsert. |
| `DELETE /v3/libraries/{id}/acl/{principal_id}` | library `admin` or global admin | 204; cannot remove last admin (return 409). |

### 5.3 Legacy: `/libraries/*` (existing file `routes_libraries.py`)

Stays mounted. Internally rewritten:

- `whoami` returns the v2 shape *and* a `principal_id` field for
  forward-compat. The v2 contract (`type`, `token_id`, `label`, `role`,
  `library`) is preserved exactly.
- `POST /libraries` for `admin-role` tokens continues to create a child
  library; for v3 SSO callers it creates a flat library and auto-grants
  the creator admin.
- `POST /libraries/{id}/tokens` is kept as a v2 alias that creates an
  `api_key` whose owning principal is `legacy:<library_id>` (a synthesized
  legacy "library service" principal). Discouraged in docs; replaced by
  `POST /v3/auth/keys` with `scope_libraries=[id]`.
- All other v2 endpoints are unchanged.

### 5.4 Existing routes — what changes

For each of these files, replace the dep function only; service-layer
calls remain identical because the service helpers accept a
`ResolvedPrincipal` (or the deprecated `ResolvedToken` shim, kept as a
re-export so external imports do not break).

| file | dep swap |
|---|---|
| `routes_agent.py` | `require_write_library_id` → primary-library helper (`v3_write_library`). |
| `routes_knowledge.py` | same. |
| `routes_records.py` | `require_write_library_id`, `require_admin_role`, `resolve_optional_token` → v3 equivalents. |
| `routes_relations.py` | `require_write_library_id` → `v3_write_library`. |
| `routes_feedback.py` | same. |
| `routes_search.py` | `resolve_optional_token` → `current_principal`. |
| `routes_v2_agent.py` | `accessible_library_ids(token, ...)` → `effective_library_ids(principal)`. |
| `routes_v2_cases.py` | same. |
| `routes_v2_stats.py` | same. |
| `routes_libraries.py` | as section 5.3. |

The `is_ancestor_or_self` helper from `repositories.py` (used for
`require_library_admin`) is removed in v3 because `parent_library_id`
no longer implies admin authority. The function stays as a no-op alias
that returns `True` so v2 tests continue to pass; v3 callers ignore it.

## 6. UI

Three new server-rendered HTML pages in `routes_ui.py`:

- `/ui/me` — uses the SSO cookie. Lists `effective_libraries`, "your API
  keys" (label, last-used, scope), "Issue new key" form (label + optional
  lib selector). Same deploy-banner header as `/ui/overview`.
- `/ui/libs` — lists `effective_libraries`; per-row link to ACL editor
  for libs the user admins; "Create library" form.
- `/ui/admin/keys` — guarded by `require_global_admin`. Bulk-issue
  per-user xyz key (textarea of SSO usernames, one per line). Rotate
  the shared xyz key. Recent audit log.

Pages are progressive — backed by the JSON APIs above; no JavaScript
beyond a small fetch helper for form submission. Match the existing
`/ui/*` styling.

## 7. Migration

### 7.1 Script

`server/scripts/migrate_v2_tokens_to_v3.py`:

```
usage: migrate_v2_tokens_to_v3.py [--apply] [--dry-run] [--db-url URL]
```

Steps (idempotent — safe to re-run):

1. Open one DB transaction.
2. For each row in `libraries`: ensure a row in `principals` with
   `principal_id='legacy:lib:<library_id>'` exists (one synthetic
   "library service" principal per library, used as `created_by` /
   `granted_by` for v2-era rows so FKs are satisfied).
3. For each row in `tokens`:
   - upsert `principal_id='legacy:<token_id>'` (kind='legacy',
     display_name=`label`).
   - upsert `library_acl(library_id, principal_id, role)` using the
     token's `role`, granted_by = `legacy:lib:<library_id>`.
   - upsert `api_keys` row with the same `key_hash = token_hash`,
     `principal_id = legacy:<token_id>`, `scope_libraries = [library_id]`,
     `label = "v2 token: " + token.label`, `created_at` from token.
4. Insert one `auth_audit_log` row per migrated token
   (action='principal.create', payload={`migrated_from_token`: token_id}).
5. Commit.

The script must complete in under one second on prod-sized data (a few
hundred tokens). If it doesn't, batch the inserts.

### 7.2 Admin onboarding script

`server/scripts/issue_xyz_keys_for_users.py --users alice,bob,... [--apply]`:

For each SSO username, upsert `principal:user:<u>`, then call
`issue_api_key(principal_id, label='xyz default', scope_libraries=['<xyz-lib-id>'])`.
Writes the raw secrets to a `--out path` JSON file (one shot, mode 0600)
and emits the file path on stdout so admin can deliver out-of-band.

The xyz library ID is resolved from a deploy-time env var
`MA3_XYZ_LIBRARY_ID` (or the unique library named `xyz` if present).

### 7.3 The shared xyz key

Migration step 3 already handles it: the existing shared-token row
becomes an `api_key` row attached to a `legacy:<token_id>` principal.
For nicer audit, a follow-up admin one-liner re-points its principal:

```
POST /v3/auth/principals/service { name: 'xyz-legacy', display_name: 'xyz shared key' }
PATCH /v3/auth/keys/{key_id}     { principal_id: 'service:xyz-legacy' }
```

(`PATCH /v3/auth/keys/{key_id}` is admin-only and is the only mutation
allowed on an existing key beyond `revoke`. It triggers an audit row.)

## 8. Tests

### 8.1 Unit (`tests/unit/`)

- `test_auth_resolver.py`
  - admin key → admin bypass
  - api_key + sso cookie naming different user → 400 conflict
  - revoked / expired api_key → 401
  - JWT expired / `alg=none` / wrong iss → anonymous
  - lazy `legacy:` resolution covers a token row with no migration done
- `test_auth_acl.py`
  - grant requires actor to hold equal-or-higher role
  - `legacy:` actor cannot grant
  - scope narrow → empty → 400
  - public lib contributes `reader` even with no explicit grant
  - admin bypass dominates everything
- `test_auth_service.py`
  - audit row written on every mutation
  - `last_used_at` cas update (no thrash)
- `test_mcp_schema_alignment.py` — extend with `ma3_whoami` libraries array

### 8.2 E2E (`tests/e2e/`)

- `test_v3_auth_routes.py`
  - `/v3/auth/whoami` for each `via=` flavor
  - issue + use a key restricted to one library
  - grant + revoke an ACL row, observe `/v3/auth/whoami` change
- `test_v3_libraries_acl.py`
- `test_legacy_token_compat.py`
  - run the migration script in-process
  - hit `/libraries/whoami` with the old token — same v2 shape
  - hit `/v3/auth/whoami` with the old token — see `kind='legacy'`
  - confirm a v2 ingest call with the old token still works

### 8.3 Regression gate

The existing 198-test suite must still pass with zero modifications.
Any test that asserts on the exact wire shape of `/libraries/whoami` is
preserved as-is (the v2 shape is additive-extended, not changed).

## 9. Wire / schema invariants

- `tools/list` MCP schema is unchanged except `ma3_whoami` response gains
  an optional `libraries: list[{library_id, role}]` field. Verified by
  `test_mcp_schema_alignment` (extension is backwards-compatible).
- `Ma3ReportPayload`, `Ma3ContextPayload`, etc. are not touched.
- `/healthz` / `/v2/doctor` payloads gain one optional field `auth_mode`
  (`v3` vs `v2-legacy`) for operator visibility.

## 10. Observability

`metrics_service.py` gains four counters:

- `ma3_auth_resolve_total{via, kind}` — every resolve call.
- `ma3_auth_403_total{reason}` — `acl_missing`, `scope_excluded`, etc.
- `ma3_auth_keys_active` — gauge of non-revoked, non-expired keys.
- `ma3_auth_audit_total{action}` — counter of audit writes.

`/v2/doctor` adds a new `auth` section: `{ principals, api_keys_active,
acl_entries, legacy_tokens, admin_bypass_used_recent }`.

## 11. Cutover plan (gated)

Follow the existing playbook in `AGENTS.md` §"LTP cutover playbook", with
these insertions and the explicit no-flip rule the user asked for.

1. `git push origin v3-auth` with the implementation commit on a branch
   off `v2`. Do **not** merge to `main` until the candidate has been
   accepted by the user.
2. Submit a NEW LTP job (do not reuse the prod job name) following
   playbook steps 2–7 unchanged. The new job listens on a new
   `MA3_PORT`. Add env vars:
   - `MA3_AUTH_JWT_SECRET=<copied from inferhub2 production env>`
   - `MA3_XYZ_LIBRARY_ID=<resolved by inspection of prod /libraries>`
3. After candidate is `RUNNING`, SSH in and execute, inside the
   candidate's venv:
   ```
   python server/scripts/migrate_v2_tokens_to_v3.py --apply
   ```
   The script must exit 0 and print `migrated_tokens=<N>`. Note that
   migration runs *on the candidate's restored Postgres dump*, so it
   does not touch prod data.
4. Run an extended candidate verification (replaces playbook step 7
   "sanity-check the schema"):
   ```
   curl /healthz | jq .auth_mode               # expect 'v3'
   curl /v3/auth/whoami                         # expect 'anonymous'
   curl /v3/auth/whoami -H 'X-API-Key: <legacy>' # kind='legacy'
   curl /v3/auth/whoami -H 'Cookie: gateway_token=<jwt>' # kind='user'
   curl /libraries/whoami -H 'X-API-Key: <legacy>'        # v2 shape preserved
   pytest -x -q tests/e2e/test_legacy_token_compat.py   # against candidate
   ```
5. **STOP. Report results to the user. Do NOT PATCH dns-manager.**
   Provide the candidate's IP:port, the auth verification output, and
   a one-line proposed dns-manager PATCH command. Wait for explicit
   "go" before flipping traffic.
6. On user "go", continue with steps 8–13 of the standard playbook
   (data sync, dns-manager PATCH via query string, external HTTPS
   verification, stop old job).
7. Post-cutover:
   - merge `v3-auth` → `main` via PR with the standard review.
   - Schedule rotation of the shared xyz key once the per-user xyz keys
     have been distributed (no automated retirement in v3).
   - Update `AGENTS.md` cutover playbook with the new migration step.

## 12. Rollback

Identical to existing playbook step 10/11: PATCH dns-manager back to
the old IP:port. The old job has not received any v3 mutations because
all writes during candidate verification happen on the candidate's own
Postgres. The new tables and audit rows are left behind on the candidate
job — harmless and ignored by v2 code.

If we need to fully back out: drop tables `principals`, `api_keys`,
`library_acl`, `auth_audit_log`. Schema is additive so this is a clean
operation. The legacy `tokens` table is untouched throughout.

## 13. Open questions handed back to the user before merge

1. Initial bulk xyz-key issuance: do we want a *grace period* where both
   the per-user keys and the shared key are valid (recommended: yes,
   indefinite — admin retires the shared key manually later) — or do
   we want a hard switch a week post-cutover?
2. JWT `admin=true` claim trust: **decided 2026-05-19** — ma3 does NOT
   trust the gateway's `admin` flag on its own. Global admin bypass
   requires both `claims.admin=true` AND `claims.user ∈ MA3_AUTH_ADMIN_USERS`.
   Initial allowlist for prod: `chuntao.hong`. Adjust via env var rollout.
3. Audit log retention: cron to truncate after N days, or keep forever?
   Recommend keep forever — volume is small.

(Items above do not block landing; they affect behavior tuning, not the
schema or wire surface.)

