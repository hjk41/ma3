# ma3 v3 — Multi-Library Access Control (Overall Design)

Status: draft 2026-05-19
Author: chuntao.hong (with Claude)
Scope: replace v2 `token ↔ 1 library` model with `principal → many libraries` ACL,
integrated with the company-wide SSO at `auth.zhilicon.com`. Preserve every
existing v2 token at startup so cutover does not break any running agent.

## 1. Why

v2 ties every API key to exactly one library:

- `tokens.library_id` is a single FK column;
- `ResolvedToken.library_id` is read everywhere in services/routes;
- `accessible_library_ids(token)` = `public ∪ {token.library_id}`;
- the global admin key is the only credential that can read more than one
  private library.

Three concrete failures fall out of this:

1. **One person needs to write to several libraries** (their personal lib +
   a team lib + the shared `xyz` engineering lib). Today they must juggle
   distinct API keys per library, which leaks into agent configuration.
2. **There is no way to give Bob read-only access to Alice's library**
   without minting a token *in* Alice's library and handing the raw secret
   over — losing audit identity (every action shows up as "Alice's token").
3. **Onboarding a new employee** requires admin to hand over the shared
   `xyz` library token, which then cannot be rotated without breaking
   everybody who memorised it. The token has no human-identity attached.

v3 fixes the model: one credential proves *who you are*; library access is
a separate ACL keyed on that identity.

## 2. Goals

- **One key, many libraries.** A credential resolves to a `principal` whose
  effective access is the union of ACL grants on libraries.
- **Identity is grounded in SSO.** `auth.zhilicon.com` issues the JWT that
  proves "I am chuntao.hong". ma3 trusts the JWT (HS256 with a shared
  secret already used by `web_portal` and `inferhub`) and lazily creates a
  `principal` row on first sight of a user.
- **Admin retains a single break-glass credential.** `MA3_API_KEY` still
  bypasses ACL — this is the "root" key, only the operator holds it.
- **Compatible cutover.** Every v2 token still works on day 1 with the
  same library access it had before; agents do not have to be re-keyed
  on cutover day. Legacy tokens are migrated into the new model as
  `legacy:<token_id>` principals with a single ACL grant.
- **Self-service for users.** A signed-in user can: create personal API
  keys, create new libraries (becoming their admin), and grant access on
  libraries they admin to any other ma3 principal.
- **Per-employee xyz-library key**, admin-managed. Admin can issue (and
  rotate) a personal xyz-library key for each SSO user; the historical
  single shared key continues to work as a "service" principal until
  retired.

## 3. Non-goals

- No reinvention of identity. ma3 does not store passwords, MFA state, or
  group membership — `auth.zhilicon.com` is canonical.
- No federation with non-SSO users (contractors, external auditors) in v3.
  If needed later, model them as service principals owned by admin.
- No row-level ACL inside a library. Access is per-library; a record's
  visibility is its library's visibility.
- No live re-issuing of SSO sessions. The SSO cookie still expires in 24h;
  API keys are the long-lived primitive for agents.
- No async event bus or change-data-capture for ACL changes; routes read
  ACL inline from Postgres on each request (the existing v2 access path
  already issues one extra query — same cost class).

## 4. Concepts

```text
auth.zhilicon.com            ma3 server
  (SSO JWT issuer)              ────────────────────────────────
                                principal       library
                                  │              │
                                  │   library_acl(principal_id, library_id, role)
                                  │              │
                                api_key ─── owned_by ─── principal
```

### 4.1 Principal

A `principal` is the durable identity that owns API keys and accumulates
ACL grants. Four flavors:

| kind     | how created                                           | example id                | who manages it     |
|----------|-------------------------------------------------------|---------------------------|--------------------|
| `user`   | first SSO login or first key creation for that `user` | `user:chuntao.hong`       | the user + admin   |
| `service`| explicitly by admin (CI bots, shared `xyz` key)       | `service:xyz-legacy`      | admin only         |
| `legacy` | auto-migrated from each pre-v3 token at startup       | `legacy:tok_a1b2`         | admin only         |
| `admin`  | synthetic; never persisted; matches `MA3_API_KEY`     | `admin:root`              | n/a (env)          |

The `user` kind is the only one that can grow ACL grants via self-service.

### 4.2 API Key

A row in `api_keys`. Carries a salted SHA-256 of the raw secret, the
owning `principal_id`, a human `label`, and an optional **scope** — a
subset of the owner's libraries this specific key may use (default: all
of them, i.e. `scope_libraries = NULL`). Has `created_at`, `last_used_at`,
optional `expires_at`, and a `revoked_at`.

Key model is **bearer**: anyone with the raw secret acts as the principal,
limited by the key's scope intersected with the principal's current ACL.

### 4.3 Library ACL

A row in `library_acl` is `(library_id, principal_id, role)` where role is
one of `reader`, `writer`, `admin` (same vocabulary v2 already uses on
tokens — exact semantics preserved). One principal can have at most one
row per library; updating role overwrites the old grant.

In addition, `libraries.is_public = true` continues to mean "everyone
reads", implemented as an implicit `(library, "*", "reader")` grant
applied at query time.

### 4.4 Effective access

For a resolved request:

```
effective_libs(principal, api_key) =
    (admin_bypass)                     if principal.kind = "admin"
    explicit_acl(principal)
      ∪ public_libraries                 if not admin_bypass
      ∩ api_key.scope_libraries          if scope_libraries is not NULL
```

The role per library is the strongest one inherited from the explicit ACL
(reader < writer < admin). Public libraries contribute `reader` only.

This collapses to v2 behavior when each principal has exactly one ACL
grant — which is exactly how legacy tokens are migrated.

## 5. Authentication channels

ma3 accepts identity through three transports; the resolver normalizes them
into the same `ResolvedPrincipal` value:

1. **`X-API-Key: <raw>`** or **`Authorization: Bearer <raw>`** — primary
   path for agents, MCP, CLI. Hash, look up in `api_keys`, walk to its
   `principal`. Update `last_used_at` opportunistically.
2. **`Cookie: gateway_token=<jwt>`** — primary path for the Web UI.
   Verify HS256 with `MA3_AUTH_JWT_SECRET`, read `user` and `admin`
   claims, upsert `principal:user:<user>`. If `admin=true`, the principal
   also gets the `admin_bypass` flag for this request (treat as global
   admin without holding `MA3_API_KEY`).
3. **`Authorization: Bearer <admin-key>`** — break-glass; matches
   `settings.api_key`. Returns the synthetic admin principal.

Order: API key first (explicit > cookie), then cookie, then anonymous
(public-libraries-only). Admin key wins over both; admin can still scope
itself to a single library by passing a key instead.

`auth.zhilicon.com` itself is never called at request-time — verification
is offline JWT validation. Logout and login UI live on the auth gateway;
ma3 just trusts the cookie.

## 6. UI / management surface

Three new (or expanded) UI pages, all behind the SSO cookie:

- `/ui/me` — "Your access": list of libraries you can read/write/admin,
  your API keys, scopes, last-used timestamps. Self-revoke. Create new key.
- `/ui/libs` — list of libraries you can see; "Create library"; for libs
  you admin, manage ACL (add/remove/change role per principal).
- `/ui/admin/keys` — admin-only: issue per-user xyz key, rotate the
  shared xyz key, list/revoke any key, view audit log of recent grants.

All three are backed by JSON APIs (next section) so agents/scripts can do
the same things headlessly.

## 7. HTTP surface (high level)

New under `/v3/auth/*`:

- `GET /v3/auth/whoami` — replaces the legacy `/libraries/whoami`; returns
  principal, effective libraries with role, key metadata, `via=`
  `api_key | sso | admin_key | anonymous`.
- `POST /v3/auth/keys` — issue a new key owned by the calling principal,
  optionally scoped to a subset of libraries.
- `GET /v3/auth/keys` — list your keys (no raw secrets).
- `DELETE /v3/auth/keys/{key_id}` — revoke.
- `POST /v3/libraries` — create lib; caller becomes `admin` on it (or admin
  may set owner).
- `GET /v3/libraries/{lib}/acl` / `PUT /v3/libraries/{lib}/acl/{principal}`
  / `DELETE` — manage library ACL (caller must be `admin` on the lib).
- `GET /v3/principals?prefix=…` — search by `user:`/`service:` prefix, so
  the UI can autocomplete grant targets.

Legacy `/libraries/*` endpoints remain mounted, but they delegate into the
new repositories (a token → its `legacy:` principal). New behavior is
strictly additive.

The MCP wire surface is unchanged. `ma3_validate`, `ma3_context`,
`ma3_report` etc. all continue to dispatch on the resolved principal's
effective library set — agents see no schema change, only the freedom
to write to more than one library by passing a key whose principal has
broader ACL.

## 8. Backwards compatibility

Hard requirement: on day 1 of cutover, **every previously-issued raw
token continues to work with exactly the same access it had before**.

Mechanism:

- One-time idempotent migration (run inside the candidate before traffic
  flip): for each row in `tokens`, create a `legacy:<token_id>` principal,
  copy `(library_id, role)` into `library_acl`, leave the original
  `tokens` row in place. The auth resolver checks `api_keys` first;
  on miss it falls back to `tokens` and resolves via the legacy
  principal. This dual-read window stays open indefinitely — there is no
  forced cutover for clients.
- The shared `xyz` key becomes the api_key row owned by
  `service:xyz-legacy`, ACL = `{xyz: writer}`. Admin can rotate at will
  without changing principal identity.
- `MA3_API_KEY` is untouched.
- `accessible_library_ids(...)` is replaced by a `resolve_libraries(...)`
  helper that returns `{lib_id: role}`. Old callers receive the
  `lib_id` set; new callers can ask for the role.

The cutover playbook in `AGENTS.md` gains one extra step before the DNS
flip: run `python server/scripts/migrate_v2_tokens_to_v3.py --apply`. The
candidate health check now also asserts that `/v3/auth/whoami` returns
a non-empty `libraries` array when called with a known legacy token.

## 9. Audit

Every ACL grant change, key issue, and key revoke writes one row to
`auth_audit_log(actor_principal_id, action, target_principal_id?, library_id?, payload_json, created_at)`.
Read access is admin-only via `GET /v3/auth/audit?since=…`.

Key *use* is not audited per request (too much volume); aggregate
`api_keys.last_used_at` is enough for hygiene.

## 10. Open / deferred

- **Group membership / RBAC.** v3 grants are per-principal. A "@all-users"
  pseudo-principal could land in v3.1 once we know if real teams want it.
- **Org-scoped roles.** If the company grows to multi-team, library ACL
  may grow a `team` dimension. Out of scope here.
- **External SSO providers / SCIM.** ma3 does not provision users; it
  reacts to whatever `auth.zhilicon.com` proves. If that gateway grows
  SCIM, ma3 can later subscribe.
- **Personal key expiry default.** v3 ships with `expires_at = NULL`
  default. We can flip this to "90 days" once we have telemetry on
  unused keys.

## 11. Risks

| risk | mitigation |
|---|---|
| auth.zhilicon.com cookie verification regressions break web UI | API key path is independent of cookies; UI fall-back is "log in again". MCP/agents untouched. |
| dual-read (`api_keys` + legacy `tokens`) lets the same raw secret resolve to two principals after manual editing | resolver returns the *first* hit; legacy table is read-only after migration script runs; integrity test enforces no overlap. |
| Bulk per-user xyz key issuance leaks raw secrets | secrets are shown once in the admin UI, otherwise stored only as hash; admin UI logs every issue + recipient. |
| ACL change races with in-flight requests | each route resolves ACL fresh per request; revocation is effective on the next request. |
| `MA3_AUTH_JWT_SECRET` rotation | identical procedure to `inferhub` (rolling re-deploy, known-leaked-list check); doc inherits inferhub runbook. |

## 12. Success criteria

- A single SSO-user-owned API key can read+write the user's personal
  library, the company `xyz` library, and any library the user has been
  granted access to, in one process, without holding the admin key.
- Admin can rotate the shared `xyz` legacy key without breaking
  per-employee xyz keys.
- Every v2 token issued before cutover still works, with the same access,
  with no client-side change.
- `/v3/auth/whoami` is the one place that explains "who am I and what
  can I do" — discoverable by every agent.

