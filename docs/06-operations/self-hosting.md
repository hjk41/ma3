# Self-hosting ma3

Run your own ma3 instance (private knowledge libraries + MCP).  
**Support: community best-effort, no SLA.**

Official SaaS / our internal SSH deploy scripts are separate; this page is for **Compose self-host**.

**First-run UX:** after `./up.sh`, open **`/ui/setup/`** (browser) **or** use the **JSON setup APIs** below (agents).

**Administrator walkthrough (deploy → init → invite members):** **[self-host-admin-guide.md](self-host-admin-guide.md)** (中文操作手册).

Details / design: **[self-host-first-run-guide.md](self-host-first-run-guide.md)**.

## Quick start (bootstrap API key, no OIDC)

### Local portal accounts (no Authing)

When OIDC is not configured, **local username/password auth is on by default** (`MA3_LOCAL_AUTH=1`):

1. Open **`/ui/setup/`** (or `/` / `/ui/home/` when no accounts exist) — create the **admin** account (first user is admin).
2. On the setup checklist: mint an API key at `/ui/keys/`, optionally close open registration, then finish setup.
3. Sign in at `/auth/login` → use `/ui/me/` and `/ui/keys/` like SaaS.
4. Admins manage accounts and the **registration toggle** at `/ui/observatory/local-users/` (DB override; no restart).
5. Bootstrap API key still works for MCP **knowledge** tools (parallel path; `/mcp/info` stays public in state A). It does **not** manage local users.

### Agent surface: MCP + REST

| Channel | Scope |
|---------|--------|
| **MCP** | Knowledge only: `ma3_context` / `ma3_report` / `ma3_feedback` (+ locate/case/writes/drafts/…) |
| **REST** `/api/*` | Everything else agents need after Compose is up: setup, users, keys, orgs, members, libraries, grants, admin |
| **Shell** | `./up.sh`, secrets, bootstrap file rotation — host ops, not HTTP |

Full route tables: [api-overview.md](../03-backend/api-overview.md).

### Agent / REST day-0 → org → MCP (no browser)

Cookie not required when you mint an API key at register/login time.

```bash
BASE=http://127.0.0.1:8000   # or your LAN URL / published port

# 1) First admin + API key
curl -fsS "$BASE/api/setup/status" | jq
REGISTER=$(curl -fsS -X POST "$BASE/api/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{
    "username":"admin",
    "password":"change-me-long-password",
    "display_name":"Instance Admin",
    "api_key":{"label":"first-admin-agent"}
  }')
ADMIN_KEY=$(jq -r '.api_key.plaintext_key' <<<"$REGISTER")

# 2) Harden + finish setup (optional: leave registration open to onboard teammates)
curl -fsS -X PATCH "$BASE/api/setup/registration" \
  -H "X-API-Key: $ADMIN_KEY" -H 'Content-Type: application/json' \
  -d '{"open":true}' | jq
curl -fsS -X POST "$BASE/api/setup/complete" \
  -H "X-API-Key: $ADMIN_KEY" | jq

# 3) Create team org + library
ORG=$(curl -fsS -X POST "$BASE/api/orgs" \
  -H "X-API-Key: $ADMIN_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"Acme Team"}')
ORG_ID=$(jq -r '.id' <<<"$ORG")
LIB=$(curl -fsS -X POST "$BASE/api/orgs/$ORG_ID/libraries" \
  -H "X-API-Key: $ADMIN_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"Eng Notes","visibility":"private"}')
LIB_ID=$(jq -r '.library_id' <<<"$LIB")

# 4) Invite teammate (recommended) — works even when registration is closed
INV=$(curl -fsS -X POST "$BASE/api/orgs/$ORG_ID/invites" \
  -H "X-API-Key: $ADMIN_KEY" -H 'Content-Type: application/json' \
  -d '{"role":"member","max_uses":1,"expires_in_hours":168,"member_alias":"小张"}')
echo "$INV" | jq '{invite_url, token, member_alias, expires_at}'
# Share invite_url with teammate. They open it (or POST /api/auth/register with "invite")
# and join the org automatically with the preset org alias.

# Optional: grant library access after they join
# curl ... POST /api/libraries/$LIB_ID/grants {"username":"alice","role":"writer"}

# Legacy alternative: open registration + manual add member (no invite)
# curl -X PATCH "$BASE/api/setup/registration" -d '{"open":true}' ...
```

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/api/setup/status` | public | Setup state + checklist |
| `POST` | `/api/auth/register` | public* | Create account (*first user always; then only if registration open). Optional `api_key` mint |
| `POST` | `/api/auth/login` | public | Password → mint API key (`api_key.label` required) |
| `PATCH` | `/api/setup/registration` | local admin | Open/close registration |
| `POST` | `/api/setup/registration/ack` | local admin | Keep registration open (checklist C4) |
| `POST` | `/api/setup/complete` | local admin | Mark setup finished |
| `GET` | `/api/local-users` | local admin | List local accounts |
| `PATCH` | `/api/local-users/{username}` | local admin | Promote/demote admin |
| `POST` | `/api/orgs/{id}/invites` | org admin | Create invite; optional `member_alias` applied on join; returns `token` + `invite_url` once |
| `GET` | `/api/orgs/{id}/invites` | org admin | List invites (no plaintext tokens) |
| `DELETE` | `/api/orgs/{id}/invites/{invite_id}` | org admin | Revoke invite |
| `GET` | `/api/invites/preview?token=` | public | Preview org/role/alias for a token |
| `POST` | `/api/invites/redeem` | user key | Existing user joins org via invite |
| `POST` | `/api/auth/register` + `invite` | public* | Register and auto-join (*or valid invite when registration closed) |
| `GET/POST` | `/api/keys` | user key/session | List / create keys |
| `GET/POST` | `/api/orgs` | user key/session | List / create team orgs |
| `POST` | `/api/orgs/{id}/members` | org admin | Add member (optional `alias`) |
| `PATCH` | `/api/orgs/{id}/members/{principal_id}` | org admin | Change `role` and/or `alias` |
| `POST` | `/api/orgs/{id}/libraries` | org admin | Create org library |
| `POST` | `/api/libraries/{id}/grants` | library maintainer | Grant library access |

Browser: org **Members** page can also generate an invite link. Share `{BASE}/auth/register?invite=…`.

Admin auth for mutating routes: **session cookie** (browser, same-origin) **or** **`X-API-Key`** for the acting principal. The self-host **bootstrap** key can call MCP / public setup **status** but **cannot** manage users, orgs, keys, or finish setup.

Set `MA3_LOCAL_AUTH=0` to restore bootstrap-only portal (503 on `/ui/me/`).
`MA3_LOCAL_AUTH_OPEN_REGISTRATION` is the **initial default** for open signup. Once an admin toggles registration (UI or API), the DB value **`local_registration_open`** overrides the env until cleared.

```bash
git clone https://github.com/hjk41/ma3.git
cd ma3/deploy/self-host
cp .env.example .env   # set POSTGRES_PASSWORD and MA3_API_KEY_ENCRYPTION_SECRET
./up.sh
./verify.sh
docker compose exec ma3 cat /data/bootstrap_api_key.txt
```

Use `plaintext_key=…` as `X-API-Key` for MCP. Point agents at:

`MA3_BASE_URL=http://127.0.0.1:8000` (or your LAN IP / published port).

**Defaults**

| Item | Default |
|------|---------|
| Auth (no OIDC) | **Local portal accounts** (`MA3_LOCAL_AUTH=1`) + **bootstrap API key** for MCP |
| First local user | Becomes **admin** (Observatory + user management) |
| Embeddings | **On** (first start downloads the model into the data volume) |
| `MA3_DEV_AUTH` | **Off** |
| Reverse proxy | **Not required** for LAN + API key / local auth |

The Compose image installs **CPU-only** PyTorch (no CUDA/NCCL). That is enough for the default MiniLM embedding model. Disable embeddings on weak machines: `MA3_DISABLE_EMBEDDINGS=1` in `.env`.

HF cache lives under the `ma3_data` volume (`/data/hf`, including `hub/`). After the first successful download you may set `HF_HUB_OFFLINE=1`.

If the container cannot reach Hugging Face (e.g. Docker IPv6 / no WAN), set `HTTP_PROXY` / `HTTPS_PROXY` in `.env` (and keep `db` in `NO_PROXY`).

## Optional: your own OIDC

Set in `.env` (preferred):

```bash
MA3_OIDC_ENABLED=1
MA3_OIDC_ISSUER=https://your-idp.example.com/realms/ma3
MA3_OIDC_CLIENT_ID=...
MA3_OIDC_CLIENT_SECRET=...
MA3_OIDC_REDIRECT_URI=https://ma3.example.com/auth/callback
MA3_AUTH_ADMIN_USERS=you@example.com
MA3_PUBLIC_BASE_URL=https://ma3.example.com
```

Legacy Authing variables (`MA3_AUTHING_*`) still work and enable Authing-style `/oidc` issuer normalization. For Authing via `MA3_OIDC_*`, set `MA3_OIDC_AUTHING_PATH_COMPAT=1` if your issuer URL omits `/oidc`.

With OIDC enabled, portal login at `/ui/keys/` can mint keys; **local auth is disabled** (OIDC takes over) and bootstrap auto-create is skipped.

Without OIDC (default self-host path):

- **Browser portal**: register/sign in via `/auth/register` and `/auth/login` (`MA3_LOCAL_AUTH=1`).
- **MCP agents**: still use the bootstrap API key (`docker compose exec ma3 cat /data/bootstrap_api_key.txt`).
- Set `MA3_LOCAL_AUTH=0` if you want bootstrap-only (no portal login; `/ui/me/` returns 503).

Open `/ui/home/` for instance info and `/mcp/info` for endpoint details.

## When do you need a reverse proxy?

Not for LAN + bootstrap key. Prefer Caddy/nginx when:

- You enable **OIDC** (HTTPS callback URLs), or
- You expose the instance on the **public internet** (TLS).

See `Caddyfile.example` in this directory.

## Community library semantics

Each self-hosted instance has its own `lib_default`. It is **not** synchronized with `https://ma3.io`. Agents only see the instance configured in `MA3_BASE_URL`.

## Data volumes

| Volume | Contents |
|--------|----------|
| `ma3_pgdata` | PostgreSQL + pgvector |
| `ma3_data` | bootstrap key file, HF cache |

Back up both. Do not `docker compose down -v` unless you intend to wipe data.

Postgres init runs `CREATE EXTENSION vector` as the image superuser (the app role cannot create extensions).

## Verify

```bash
./verify.sh
# Live deploy verification (healthz, MCP, client bundle, bootstrap UI):
bash ./verify_integration.sh
# or manually:
curl -sS "$MA3_BASE_URL/healthz"
# MCP tools/list with X-API-Key
```

Manual bootstrap / rotate:

```bash
docker compose exec ma3 python scripts/bootstrap_selfhost.py --force
```

## Security notes

- Change all secrets in `.env` before any shared or public deployment.
- Treat `/data/bootstrap_api_key.txt` as a root credential.
- Never set `MA3_DEV_AUTH=1` on a public URL.
- Report vulnerabilities: see repo root `SECURITY.md`.

## Related

- **Admin handbook (中文):** [self-host-admin-guide.md](self-host-admin-guide.md)
- Checklist: [self-hosting-mvp-checklist.md](self-hosting-mvp-checklist.md)
- ADR-015: [015-oidc-pluggable-selfhost-bootstrap.md](../02-architecture/decisions/015-oidc-pluggable-selfhost-bootstrap.md)
- Agent onboarding: `GET {MA3_BASE_URL}/client/agent-onboarding.md`
