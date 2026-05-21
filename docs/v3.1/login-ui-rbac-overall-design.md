> 2026-05-21 update: the routing portions of this document are superseded by `root-ui-polish-design.md`: the browser UI is served at `/` and known root deep links only; `/ui` and `/ui/*` are intentionally not retained. MCP stays at `/mcp`.

# ma3 v3.1 — Login fix + Web UI redesign + RBAC overall design

Status: design 2026-05-20
Author: chuntao.hong (with Claude)
Scope: three coupled improvements that each unblock the next.

## 1. Why now

Three problems surfaced from real usage of the v3 candidate:

1. **You cannot log in.** `MA3_AUTH_VERIFY_URL` is wired up, but the
   server exposes no `/auth/callback`, no "Login" link, and no
   redirect-to-gateway flow. The UI just returns `kind=anonymous` and
   there is literally nothing to click. On top of that, when a cookie
   does get set (manually) the current resolver was designed for
   `domain=.zhilicon.com` cookies, which a browser refuses to accept on
   `http://localhost:18196` (the standard tunnel-to-LTP test setup).
2. **The UI is ugly.** The old candidate's `/ui/overview`, `/ui/me`, `/ui/libs`,
   `/ui/admin/keys` pages were bare server-rendered HTML strings concatenated in
   `routes_ui.py`. No layout system, no design tokens, no nav, no
   responsive behavior. Every screen looks like a 1998 admin tool. The
   sibling project `~/code/agent_exchange` ships a clean React + Tailwind
   SPA with a sidebar tree, a small `components/ui.tsx` primitives kit,
   and a working SSO handshake — we can borrow its structure.
3. **Access control is one-row-per-pair.** `library_acl(library_id,
   principal_id, role)` works, but the role is a free-form string
   (`reader|writer|admin`) and permission checks are scattered across
   route handlers. Adding a new role (e.g. `reviewer`, `auditor`) means
   editing every site that hard-codes the three values. There is no
   first-class concept of "permission" — just role-name string compares.
   For an internal service this was fine in v3. For a multi-team future
   it is the next real bottleneck.

We fix all three on the same branch because they touch the same files
(routes_ui.py, routes_v3_auth.py, core/auth.py) and would conflict if
done serially.

## 2. Goals

1. **Login works in three places**: prod (`https://ma3.zhilicon.com`),
   any `*.zhilicon.com` hostname, and a localhost tunnel. The user can
   click a Login link, get bounced to `auth.zhilicon.com/login`, come
   back with a `gateway_token`, and stay logged in.
2. **Web UI is a single-page React app** built with Vite, styled with
   Tailwind, served by FastAPI as static assets. Sidebar nav, card-based
   pages, modal dialogs, the `agent_exchange` look. No more
   string-concatenated HTML.
3. **RBAC is first-class**:
   - Roles are named entries in a `roles` table.
   - Each role has a set of permissions (in code, an enum/set, not a DB
     table — permissions are bound to code, not data).
   - `library_acl` becomes `role_assignments(scope_type, scope_id,
     principal_id, role_name)` — same row count as today (≤1 per
     principal per library), but the `role_name` references the roles
     table.
   - Routes declare a permission they need (`@require_perm("record:write",
     library_param="library_id")`); the framework resolves it from the
     principal's effective role bundle.
   - Migration is a one-shot rename + insert: existing
     `library_acl(role='reader|writer|admin')` rows become
     `role_assignments(role_name='library_reader|library_writer|library_admin')`.

## 3. Non-goals

- No ABAC (attribute-based). Permissions are enumerated at code-write
  time. Want runtime policy? out of scope.
- No row-level ACL inside a library.
- No new external IdPs. SSO stays `auth.zhilicon.com`.
- No realtime UI updates (websockets, SSE) in v3.1. Plain
  fetch-on-mount + manual refresh is enough at this scale.

## 4. Login flow (fix #1)

End-to-end:

```
[user opens] http://<host>/<any-page>
    │
    ▼
SPA mounts → calls GET /v3/auth/whoami
    │
    ├── 200 with kind=user → already logged in, render normally
    └── 200 with kind=anonymous → render "Login" button in sidebar
                                 + intercept /v3/* mutations with
                                 401 → redirect to login

[user clicks Login] → window.location = /auth/login?next=<current-href>
    │
    ▼
GET /auth/login (NEW server route) →
    302 to https://auth.zhilicon.com/login?next=<our-callback>
                                            ?return_to=<original href>

[gateway authenticates] → 302 to /<our-callback>?gateway_token=<jwt>&return_to=…

[NEW server route] GET /auth/callback?gateway_token=…&return_to=…
    │  validates gateway_token via $MA3_AUTH_VERIFY_URL
    │  set cookie gateway_token=<jwt>; HttpOnly; SameSite=Lax;
    │    domain set per §4.1 below; max_age=min(jwt.exp-now, 86400)
    └── 302 to safeReturnTo(return_to)   # only same-origin, else "/"

[follow-up requests] carry the cookie; resolve_principal verifies via
    /verify (cached up to 60s) and returns kind=user.
```

### 4.1 Cookie scoping for localhost compatibility

The cookie's `Domain` attribute must satisfy the browser's host-match
rule. Today the cookie is hard-coded to `.zhilicon.com`, which fails on
localhost. The fix:

```python
def _cookie_domain(request_host: str) -> str | None:
    h = request_host.split(":")[0]
    if h.endswith(".zhilicon.com"):
        return ".zhilicon.com"   # share across subdomains in prod
    return None                   # localhost / unknown — scope to current host
```

This keeps prod SSO working across `auth.zhilicon.com` ↔ `ma3.zhilicon.com`
↔ `inferhub2.zhilicon.com`, and quietly works on the tunnel.

### 4.2 Logout

`GET /auth/logout` clears the cookie (with the same Domain scope) and
302s to `/` so the user is now anonymous. No redirect to the gateway —
just local clear is enough; if they want to log in as someone else they
click Login again.

### 4.3 What about the API key path?

Untouched. `X-API-Key` and `Authorization: Bearer` keep working exactly
as today. SSO is purely additive — humans use it, agents don't.

## 5. Web UI (fix #2)

### 5.1 Tech stack

| layer | choice | why |
|---|---|---|
| Build | Vite 5 | matches `agent_exchange` |
| Framework | React 18 | matches |
| Routing | react-router-dom 6 | matches |
| Styling | Tailwind CSS 3 | matches |
| State | local `useState` + `UserContext` | matches; SSR not needed |
| HTTP | fetch + small `apiClient` | matches |

Source lives in `server/app/web/` (new). Built assets land in
`server/app/web/dist/` and are mounted by FastAPI as static files at
`/assets/*`. The HTML entry is served from the known root UI routes
(`/`, `/me`, `/libs`, `/libs/:id`, `/keys`, `/admin`, `/observatory`).

The legacy `routes_ui.py` HTML strings are **deleted**. Nobody is
running the v2 prod off them anymore — we have only the candidate
running, and it's the one we're rebuilding.

### 5.2 Pages

Modeled directly on `agent_exchange/src/web/src/pages/` shapes:

| route | page | purpose |
|---|---|---|
| `/` | `Dashboard` | Welcome, your effective libraries, and quick links to keys, observatory, and admin. |
| `/me` | `MePage` | Identity card (principal, kind, via, admin_bypass). Your effective libraries with role badges. Your API keys list with Create/Revoke. |
| `/libs` | `LibrariesPage` | List of effective libraries. "Create library" button (modal). Per-row link to Detail. |
| `/libs/:id` | `LibraryDetail` | Library header (name, description, public flag). Knowledge preview first, then ACL table for admins. |
| `/keys` | `KeysPage` | All your keys (label, scope, last-used, expires). Create+Revoke flows. |
| `/admin` | `AdminConsole` | Admin-only landing: principals (search), audit log feed, doctor.backup live block, "Issue per-user xyz key" bulk form. |
| `/observatory` | `ObservatoryPage` | Knowledge stats (records, cases, status distribution) filtered by effective visibility. |
| `*` (404) | `NotFound` | small 404 page. |

### 5.3 Layout

`App.tsx` shell: collapsible sidebar (Dashboard / Me / Libraries / Keys /
Observatory / Admin if admin) + main content area + top-right user menu
(Login / Logout / username). Same Tailwind classes as agent_exchange's
`Sidebar` (`bg-slate-900 text-slate-300`).

Components reused from agent_exchange, copied verbatim into
`web/src/components/ui.tsx`: `Card`, `Modal`, `Badge`, `Spinner`,
`Empty`, `ErrorMessage`, `Button`. No new design system invented —
borrow.

### 5.4 API client

Single `web/src/api/client.ts`:
- methods for every endpoint we expose (whoami, libraries CRUD, ACL
  CRUD, keys CRUD, principals search, audit log, doctor)
- 401 → redirect to `/auth/login?next=<current>`
- 403 → throw a typed `ForbiddenError` so pages can show a permission
  message
- transparent JSON parsing

### 5.5 Build wiring

- `server/app/web/package.json`, `vite.config.ts`, `tsconfig.json`
  parallel agent_exchange's structure.
- `npm install && npm run build` runs in CI (and from the LTP bootstrap)
  to produce `dist/` before uvicorn starts.
- FastAPI uses `app.mount("/ui", StaticFiles(directory="app/web/dist",
  html=True))` — `html=True` makes it serve `index.html` for unknown
  paths, which is what react-router needs.
- bootstrap_ma3_ltp.sh installs `nodejs npm` once via apt, then runs
  `npm ci && npm run build` in `app/web/` if `dist/index.html` is older
  than the source. Cached builds survive container restart since
  `dist/` lives in the repo workdir on CephFS.

## 6. RBAC (fix #3)

### 6.1 Concepts

- **Permission**: a string token describing one capability, e.g.
  `record:read`, `record:write`, `library:manage_acl`. Defined as a
  Python `Enum` (`app.models.auth.Permission`). Code-side, not data-side.
- **Role**: a named bundle of permissions, scoped to a "kind". Built-ins
  shipped at v3.1:

  | role_name | scope_type | permissions |
  |---|---|---|
  | `library_reader`  | library | `record:read, case:read, relation:read, feedback:read` |
  | `library_writer`  | library | reader + `record:write, case:write, relation:write, feedback:write` |
  | `library_admin`   | library | writer + `library:manage_acl, library:delete, key:scope_to_library` |
  | `system_admin`    | system  | every permission, including the admin-bypass equivalent |

- **role_assignments(scope_type, scope_id, principal_id, role_name)**:
  the actual ACL row. `scope_type='library'` + `scope_id=<library_id>` is
  the v3.0 case; `scope_type='system'` + `scope_id=NULL` covers the
  global-admin case.

### 6.2 Schema

```sql
CREATE TABLE IF NOT EXISTS roles (
    role_name      TEXT PRIMARY KEY,             -- 'library_reader' etc.
    scope_type     TEXT NOT NULL,                -- 'library' | 'system'
    permissions    JSONB NOT NULL,               -- ["record:read", ...]
    description    TEXT,
    is_builtin     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS role_assignments (
    scope_type     TEXT NOT NULL,                -- 'library' | 'system'
    scope_id       TEXT,                         -- library_id; NULL when system
    principal_id   TEXT NOT NULL REFERENCES principals(principal_id) ON DELETE CASCADE,
    role_name      TEXT NOT NULL REFERENCES roles(role_name),
    granted_at     TEXT NOT NULL,
    granted_by     TEXT NOT NULL REFERENCES principals(principal_id),
    PRIMARY KEY (scope_type, scope_id, principal_id, role_name)
);
CREATE INDEX IF NOT EXISTS idx_assign_principal ON role_assignments(principal_id);
CREATE INDEX IF NOT EXISTS idx_assign_scope     ON role_assignments(scope_type, scope_id);
```

`library_acl` is **deprecated but kept** for one release for read-only
backward-compat. Resolver reads from `role_assignments` first, falls
back to `library_acl` on miss. New writes go only to
`role_assignments`. A migration script copies every existing
`library_acl` row over.

### 6.3 Permission checks

Resolver gains:

```python
def has_permission(
    principal: ResolvedPrincipal,
    perm: Permission,
    *,
    library_id: str | None = None,
) -> bool: ...
```

Routes adopt a small decorator:

```python
@router.post("/v3/libraries/{library_id}/acl/{principal_id}")
def grant_acl(
    library_id: str, principal_id: str, body: AclGrantBody,
    actor: ResolvedPrincipal = Depends(current_principal),
):
    require_permission(actor, Permission.LIBRARY_MANAGE_ACL, library_id=library_id)
    ...
```

The previous one-row-per-pair invariant on `library_acl` is preserved by
constraining the UI/API to assign exactly one library role per
principal-library pair (the `role_assignments` PK includes role_name, so
strictly the table allows multiple, but the API enforces "one library
role per principal" — admin can replace it).

### 6.4 Migration

`server/scripts/migrate_v3_to_v3_1_rbac.py`:

1. Read all `library_acl` rows.
2. For each, INSERT INTO `role_assignments` with
   `role_name='library_' + role`, `scope_type='library'`, and the same
   `principal_id`/`granted_by`.
3. INSERT INTO `roles` the four built-in rows if not present.
4. Print `migrated_assignments=<N>`.

Idempotent (uses `ON CONFLICT DO NOTHING`). Script invoked from
bootstrap right after the v2→v3 token migration.

### 6.5 What admin bypass means now

`is_admin_bypass` keeps working for `MA3_API_KEY` and `MA3_AUTH_ADMIN_USERS`
SSO admins. Internally it short-circuits `has_permission` to always
return True. Equivalent to: admin holds an implicit
`role_assignments(scope='system', role='system_admin')`.

The migration also writes one **explicit** row for each
`MA3_AUTH_ADMIN_USERS` member as `system_admin` so the UI can show
"system admin" badges without re-reading env vars.

## 7. API surface deltas

New routes:

- `GET  /auth/login?next=…`  → 302 to gateway (login fix).
- `GET  /auth/callback?gateway_token=…&return_to=…` → set cookie + 302 (login fix).
- `GET  /auth/logout` → clear cookie + 302 (login fix).
- `GET  /v3/roles` — list roles + their permissions (so the UI can render
  role pickers without hard-coding strings).
- `GET  /v3/auth/permissions/me` — return the principal's full effective
  permission set, for the UI to gray out impossible buttons.

Existing v3 routes:

- ACL endpoints (`/v3/libraries/{id}/acl/*`) keep their wire shape but
  now read/write `role_assignments` under the hood.
- `/v3/auth/whoami` response gets a `roles[]` field listing each
  assignment.

Legacy v2 routes: untouched.

## 8. Tests

| layer | adds |
|---|---|
| Unit | `test_rbac_permissions.py` (built-in role bundles, has_permission edges), `test_login_callback.py` (cookie domain logic, return_to safety, /verify integration via mock). |
| E2E | `test_login_flow.py` (anonymous → /auth/login → mock gateway → /auth/callback → cookie set → whoami=user). `test_role_assignments.py` (grant/revoke via new API, observe whoami change). |
| UI | `web/__tests__/` Vitest cases for Dashboard / Me / Libraries / Keys, identical pattern to agent_exchange's tests. |
| Regression | All 223 existing tests stay green. |

## 9. Rollout

1. New branch `v3.1-ui-rbac` cut from `v3-auth`.
2. codex-openai (gpt-5.5 medium) implements per the implementation spec.
3. PR cleanup; pytest must show ≥223 passed and the new tests on top.
4. Submit a 4th LTP candidate (`ma3-v3.1-cand-…`) reusing the existing
   PITR bootstrap; the candidate replaces the v3.0 candidate for visual
   review.
5. Iterate based on user feedback (UI polish, RBAC nuance) until the
   user signs off. Then merge, then plan cutover (still gated on
   explicit user "go" — same rule as before).

## 10. Risks

| risk | mitigation |
|---|---|
| Cookie scoping breaks an existing browser session | additive change; old `.zhilicon.com` cookies remain valid; resolver reads either. |
| React build adds ~30s to bootstrap | cache `dist/` on CephFS; rebuild only when source changed. |
| RBAC migration drift between `library_acl` and `role_assignments` | resolver reads both during the transition; integrity test asserts no row in `library_acl` lacks a corresponding `role_assignments`. |
| codex misreads the spec | the implementation doc is exhaustive; verification is gated by the user; iteration is expected. |
