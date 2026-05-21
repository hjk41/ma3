> 2026-05-21 update: the routing portions of this document are superseded by `root-ui-polish-design.md`: the browser UI is served at `/` and known root deep links only; `/ui` and `/ui/*` are intentionally not retained. MCP stays at `/mcp`.

# ma3 v3.1 — Login + UI + RBAC Implementation Spec

Status: implementation spec 2026-05-20
Companion to `docs/v3.1/login-ui-rbac-overall-design.md`.
Target: codex-openai with reasoning_effort=medium. The instructions
below are concrete enough that "follow the spec, don't invent" is the
right policy.

## 0. Repo state when you start

- Branch: cut **`v3.1-ui-rbac`** off `origin/v3-auth` (HEAD `35f724b`).
- 223 pytest passing. Don't regress.
- `~/code/agent_exchange/src/web` is the look-and-feel reference. Copy
  `components/ui.tsx` verbatim. Mirror the sidebar/page layout pattern.
  Do NOT depend on agent_exchange code at runtime — duplicate what you
  need into ma3.

## 1. File-by-file plan

### Backend (Python / FastAPI)

| file | action | what |
|---|---|---|
| `app/core/auth.py` | edit | (a) cookie domain helper (§3); (b) `has_permission()` + `require_permission()`; (c) `Permission` enum + role bundles; (d) bypass for system_admin assignment + `MA3_AUTH_ADMIN_USERS`. |
| `app/api/routes_auth.py` | NEW | `/auth/login` (302), `/auth/callback` (cookie set + 302), `/auth/logout`. |
| `app/api/routes_v3_auth.py` | edit | add `GET /v3/roles`, `GET /v3/auth/permissions/me`; whoami response gains `roles[]`. |
| `app/api/routes_ui.py` | rewrite | replace string-HTML routes with explicit root SPA routes: `GET /`, `/me`, `/libs`, `/libs/{id}`, `/keys`, `/admin`, `/observatory` serve `app/web/dist/index.html`. |
| `app/api/routes_libraries.py` / `routes_v3_auth.py` ACL endpoints | edit | switch reads/writes from `library_acl` to `role_assignments`. Keep `library_acl` as a fall-back read for one release. |
| `app/main.py` | edit | mount `StaticFiles(directory="app/web/dist", html=True)` at `/ui`. Register `routes_auth`. Pass through CORS for `/auth/*`. |
| `app/storage/db.py` | edit | add `roles` and `role_assignments` tables (sqlite + postgres branches). Insert built-in roles on first boot. |
| `app/storage/repositories.py` | edit | add `RoleRepository` + `RoleAssignmentRepository`. |
| `app/services/auth_service.py` | edit | grant/revoke now operate on `role_assignments`; `effective_libraries` reads from `role_assignments`. |
| `app/models/auth.py` | edit | add `Permission` enum, `Role`, `RoleAssignment` Pydantic models. |
| `server/scripts/migrate_v3_to_v3_1_rbac.py` | NEW | idempotent backfill from `library_acl` → `role_assignments`; insert built-in roles; backfill `system_admin` for `MA3_AUTH_ADMIN_USERS`. |
| `deploy/ltp/bootstrap_ma3_ltp.sh` | edit | (a) install `nodejs npm`; (b) `cd app/web && npm ci && npm run build` if `dist/index.html` is older than any source under `src/`; (c) run RBAC migration script after the v2→v3 one. |

### Frontend (React / Vite / TS / Tailwind)

Create `server/app/web/`:

```
server/app/web/
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── index.html
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── index.css                  # @tailwind base/components/utilities
│   ├── api/
│   │   └── client.ts
│   ├── auth/
│   │   └── loginUrl.ts            # builds /auth/login?next=…
│   ├── components/
│   │   ├── ui.tsx                 # COPY VERBATIM from agent_exchange
│   │   └── Sidebar.tsx
│   ├── contexts/
│   │   └── UserContext.tsx
│   └── pages/
│       ├── Dashboard.tsx
│       ├── MePage.tsx
│       ├── LibrariesPage.tsx
│       ├── LibraryDetail.tsx
│       ├── KeysPage.tsx
│       ├── AdminConsole.tsx
│       ├── ObservatoryPage.tsx
│       └── NotFound.tsx
└── __tests__/
    ├── App.test.tsx
    ├── Dashboard.test.tsx
    ├── MePage.test.tsx
    ├── LibrariesPage.test.tsx
    └── KeysPage.test.tsx
```

`package.json` deps mirror agent_exchange's web subset:

```json
{
  "name": "ma3-web",
  "private": true,
  "type": "module",
  "scripts": {
    "build": "tsc -b && vite build",
    "dev":   "vite",
    "test":  "vitest run"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.22.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "@vitejs/plugin-react": "^4.2.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.3.0",
    "vite": "^5.0.0",
    "vitest": "^1.0.0",
    "@testing-library/react": "^14.0.0",
    "@testing-library/jest-dom": "^6.1.0",
    "happy-dom": "^13.0.0"
  }
}
```

`vite.config.ts`: base `/`, build outDir `dist`, dev server proxies
`/v3`, `/v2`, `/libraries`, `/auth`, `/healthz` to
`http://127.0.0.1:18196` for local dev.

`tailwind.config.js`: scan `./index.html` and `./src/**/*.{ts,tsx}`; no
custom colors — use Tailwind defaults exactly like agent_exchange.

## 2. Login routes (concrete)

`app/api/routes_auth.py`:

```python
from urllib.parse import urlencode, urlparse, urlunparse
from fastapi import APIRouter, Request, Cookie, Response
from fastapi.responses import RedirectResponse, JSONResponse
from app.core.auth import verify_sso_cookie, _cookie_domain_for_host
from app.core.config import settings

router = APIRouter()

def _safe_next(req_host: str, raw: str | None) -> str:
    if not raw or not raw.startswith("/"):
        return "/"
    if raw.startswith("//"):
        return "/"
    return raw

@router.get("/auth/login")
async def auth_login(request: Request, next: str = "/"):
    if not settings.auth_verify_url:
        return JSONResponse({"error": "sso_disabled"}, status_code=503)
    callback = f"{request.url.scheme}://{request.url.netloc}/auth/callback"
    return_to = _safe_next(request.url.netloc, next)
    qs = urlencode({"next": f"{callback}?return_to={return_to}"})
    return RedirectResponse(f"https://auth.zhilicon.com/login?{qs}", status_code=302)

@router.get("/auth/callback")
async def auth_callback(request: Request, gateway_token: str | None = None,
                        return_to: str = "/"):
    if not gateway_token:
        return RedirectResponse(_safe_next(request.url.netloc, return_to), 302)
    verified = verify_sso_cookie(gateway_token)
    if verified is None:
        # gateway said this token is invalid; loop back to login
        return RedirectResponse("/auth/login", 302)
    resp = RedirectResponse(_safe_next(request.url.netloc, return_to), 302)
    domain = _cookie_domain_for_host(request.url.netloc)
    resp.set_cookie(
        key="gateway_token",
        value=gateway_token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        max_age=86400,
        domain=domain,        # may be None — that's fine
        path="/",
    )
    return resp

@router.get("/auth/logout")
async def auth_logout(request: Request):
    resp = RedirectResponse("/", 302)
    resp.delete_cookie("gateway_token", domain=_cookie_domain_for_host(request.url.netloc), path="/")
    return resp
```

Notes for codex:

- The `next` parameter must be sanitized — only allow paths starting
  with `/`, never absolute URLs to other hosts. Tests must cover this.
- `_cookie_domain_for_host(host)` returns `.zhilicon.com` for
  `*.zhilicon.com`, otherwise None. Tests must cover localhost,
  IP-only, and prod.
- Don't use the literal string `https://auth.zhilicon.com/login` —
  read from `settings.auth_verify_url` and strip the trailing
  `/verify` to derive the gateway base, OR add a new
  `MA3_AUTH_LOGIN_URL` env var that defaults to
  `https://auth.zhilicon.com/login`.

## 3. Permission model

`app/models/auth.py` add:

```python
from enum import Enum

class Permission(str, Enum):
    RECORD_READ          = "record:read"
    RECORD_WRITE         = "record:write"
    RECORD_DELETE        = "record:delete"
    CASE_READ            = "case:read"
    CASE_WRITE           = "case:write"
    RELATION_READ        = "relation:read"
    RELATION_WRITE       = "relation:write"
    FEEDBACK_READ        = "feedback:read"
    FEEDBACK_WRITE       = "feedback:write"
    LIBRARY_MANAGE_ACL   = "library:manage_acl"
    LIBRARY_DELETE       = "library:delete"
    KEY_SCOPE_TO_LIBRARY = "key:scope_to_library"
    SYSTEM_ADMIN         = "system:admin"

BUILTIN_ROLES = {
  "library_reader": ["record:read","case:read","relation:read","feedback:read"],
  "library_writer": [
      "record:read","record:write","case:read","case:write",
      "relation:read","relation:write","feedback:read","feedback:write",
  ],
  "library_admin": [
      *BUILTIN_ROLES_LIBRARY_WRITER,                # placeholder, fill explicitly
      "library:manage_acl","library:delete","key:scope_to_library",
  ],
  "system_admin": ["*"],   # special; resolver short-circuits
}
```

(Replace placeholder lines with the explicit lists when implementing.)

`app/core/auth.py` add:

```python
def effective_permissions(p: ResolvedPrincipal, library_id: str | None = None) -> set[str]:
    if p.is_admin_bypass:
        return {"*"}
    perms = set()
    for assign in role_assignments_for(p.principal_id):
        if assign.scope_type == "system":
            perms.update(BUILTIN_ROLES.get(assign.role_name, []))
        elif assign.scope_type == "library" and assign.scope_id == library_id:
            perms.update(BUILTIN_ROLES.get(assign.role_name, []))
    return perms

def has_permission(p, perm, *, library_id=None) -> bool:
    s = effective_permissions(p, library_id)
    return "*" in s or perm in s

def require_permission(p, perm, *, library_id=None):
    if not has_permission(p, perm, library_id=library_id):
        raise HTTPException(status_code=403, detail={
            "error": "permission_denied",
            "missing": perm,
            "library": library_id,
        })
```

## 4. Migration script

`server/scripts/migrate_v3_to_v3_1_rbac.py`:

```
usage: migrate_v3_to_v3_1_rbac.py [--apply] [--dry-run]
```

Steps (idempotent):

1. Insert built-in roles into `roles` if missing.
2. For each `library_acl` row: INSERT INTO `role_assignments` with
   `scope_type='library'`, `scope_id=library_id`,
   `role_name='library_'+role`, `granted_by` carried over.
3. For each user listed in `MA3_AUTH_ADMIN_USERS`: ensure
   `principals(kind='user', principal_id='user:'+name)` exists, then
   INSERT INTO `role_assignments` `('system', NULL, 'user:'+name,
   'system_admin')`.
4. Print `migrated_assignments=<N> created_admins=<M>`.
5. Use `INSERT … ON CONFLICT DO NOTHING` everywhere.

Bootstrap calls it with `--apply` after the v2→v3 token migration.

## 5. UI behaviors

### Dashboard (`/`)
- if anonymous: show big "Login with auth.zhilicon.com" button + a
  short "what is ma3" copy; nothing else.
- if logged in: list effective libraries (badges showing role per lib),
  recent op_logs (call `GET /v2/stats/overview` filtered by their libs),
  link to admin console if `is_admin_bypass`.

### MePage (`/me`)
- Identity card: principal_id, kind, via, admin_bypass.
- Effective libraries table: name, role (badge), source (acl/public/scope).
- Roles list (from new `whoami.roles[]`).
- API keys section: list with label/scope/last-used/expires; "Create
  key" modal (label, optional scope_libraries multi-select);
  "Revoke" buttons.

### LibrariesPage (`/libs`)
- Card grid of effective libraries.
- "Create library" button (modal: name, description, public flag).
- Click into LibraryDetail.

### LibraryDetail (`/libs/:id`)
- Library header.
- ACL table: rows are role_assignments for this library. Admin can
  add/remove/change role (via `GET /v3/roles` to populate role picker).
  Non-admin sees read-only.
- Records preview: first 5 active records via
  `/records?library_id=<id>&limit=5&status=active`.

### KeysPage (`/keys`)
- Same content as MePage's keys section but full-width and includes
  "All my keys" — duplicated for navigation convenience.

### AdminConsole (`/admin`)
- 403 if not admin.
- Three tabs:
  - **Principals**: search by prefix, view details, see their
    assignments.
  - **Audit**: paged feed of `auth_audit_log`.
  - **Backup**: render `/v2/doctor.backup` block live (poll every 10s).
  - **Bulk xyz keys**: textarea of usernames; calls
    `issue_xyz_keys_for_users.py` analogue route (NEW: `POST /v3/admin/issue_xyz_keys`
    body `{users: [...]}`).

### ObservatoryPage (`/observatory`)
- Content of old `/ui/overview`, `/ui/topics`, `/ui/cases` rolled into
  one tabbed page. Reuse v2 stats endpoints; pages are read-only.

## 6. Test plan

### Python unit (`server/tests/unit/`)

- `test_login_callback.py`:
  - `_cookie_domain_for_host`: 'ma3.zhilicon.com' → '.zhilicon.com';
    'localhost' → None; '127.0.0.1' → None; 'auth.zhilicon.com' → '.zhilicon.com'.
  - `_safe_next`: '/me' → '/me'; 'http://evil/' → '/';
    '//evil' → '/'.
  - `auth_callback` w/ valid gateway_token (mock verify) → cookie set
    with right domain, redirect to safe return_to.
  - `auth_callback` w/ invalid gateway_token → 302 to /auth/login.
  - `auth_login` w/o `MA3_AUTH_VERIFY_URL` set → 503.

- `test_rbac_permissions.py`:
  - Built-in role bundles match spec.
  - `library_writer` includes `library_reader`'s perms.
  - `system_admin` short-circuits to allow.
  - `is_admin_bypass=True` short-circuits to allow.
  - Library-scoped permission only granted for the matching `library_id`.

- `test_role_assignments_repo.py`:
  - Insert + read + delete role_assignment.
  - Effective libraries computed correctly across multiple roles.

### Python e2e (`server/tests/e2e/`)

- `test_login_flow.py`: end-to-end with TestClient. Mock `/verify`
  to return a known user. Hit `/auth/login`, follow the 302, hit
  `/auth/callback?gateway_token=fake&return_to=/me`, follow
  the 302, see Set-Cookie header, then call `/v3/auth/whoami` with
  the cookie → kind=user.
- `test_rbac_acl_routes.py`: mint a library, grant `library_writer` to
  a principal via `PUT /v3/libraries/{id}/acl/{pid}`, observe
  whoami.roles[] includes the new assignment, attempt a
  permission-gated action → 200; revoke; same action → 403.

### Frontend (`server/app/web/__tests__/`)

- `App.test.tsx`: renders Sidebar, Dashboard renders for anonymous user
  with Login button visible.
- `MePage.test.tsx`: with mocked whoami, renders identity card +
  libraries list + keys list.
- `KeysPage.test.tsx`: create-key modal opens, calling api.createKey
  shows the raw secret once, revoking removes the row.
- `LibrariesPage.test.tsx`: renders effective libs; "Create library"
  modal submits.

Run via `npm run test` in `server/app/web/`. Add a thin pytest wrapper
that shells out to `npm run test` if `node` is on PATH; skip-with-warn
if not. Don't gate the python suite on it.

### Regression

`pytest -x -q` must finish at **≥ 226 passed** (existing 223 + at
least 3 new from RBAC unit + login e2e). Don't reduce numbers; add to
them.

## 7. Bootstrap edits (deploy/ltp/bootstrap_ma3_ltp.sh)

- After `apt-get install … python3 …` add:
  ```
  if ! command -v node >/dev/null 2>&1; then
    apt-get install -y --no-install-recommends nodejs npm
  fi
  ```
- New step after restore + auth migrations, before uvicorn:
  ```
  if [[ -d "$MA3_REPO_DIR/server/app/web" ]]; then
    cd "$MA3_REPO_DIR/server/app/web"
    if [[ ! -f dist/index.html ]] || [[ "$(find src index.html package.json -newer dist/index.html -print -quit 2>/dev/null)" ]]; then
      log "building web SPA"
      npm ci --silent
      npm run build
    else
      log "web SPA dist is fresh; skipping build"
    fi
  fi
  ```
- New step in same block: run RBAC migration script:
  ```
  if [[ -f "$MA3_REPO_DIR/server/scripts/migrate_v3_to_v3_1_rbac.py" ]]; then
    "$MA3_VENV/bin/python3" "$MA3_REPO_DIR/server/scripts/migrate_v3_to_v3_1_rbac.py" --apply
  fi
  ```

## 8. Out of scope (do NOT do)

- Don't redesign MCP tools.
- Don't add SSE / websockets.
- Don't touch the v3 PITR backup code beyond integrating new env vars
  if needed.
- Don't add new MCP wire fields without updating the
  `test_mcp_schema_alignment` test.

## 9. Commit / push / report

- Push the branch as `v3.1-ui-rbac`.
- Atomic commits per concern (auth routes, RBAC schema, RBAC service,
  UI scaffold, UI pages, migration script, bootstrap, tests).
- Final report `/tmp/ma3-v3.1-codex-report.md` with:
  1. Branch + commit SHA pushed.
  2. `pytest -x -q` last 30 lines (must show ≥ 226 passed).
  3. `cd server/app/web && npm run test` last 20 lines.
  4. `bash -n` + `shellcheck -S warning` results for any modified shells.
  5. List of files added/modified.
  6. Any decisions you had to make beyond the spec.
- Do **not** submit any LTP candidate. The user will explicitly tell
  Claude when to do that.
- Do **not** PATCH dns-manager. Ever.

## 10. Iteration

If the user calls back with "page X looks ugly" or "the role X should
include Y", the spec is allowed to evolve in follow-up commits — do
NOT consider this version frozen. The first delivery just needs to be
correct + functional. Polish is iterative.
