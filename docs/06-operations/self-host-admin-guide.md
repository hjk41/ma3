# Self-Hosting Administrator Guide

> Chinese version: [self-host-admin-guide.zh.md](self-host-admin-guide.zh.md)

For **instance administrators**: from Compose deployment, through first-time initialization (Web / Agent), to inviting colleagues into an org and connecting via MCP.

**Related documents**

| Document | Purpose |
|------|------|
| [self-hosting.md](self-hosting.md) | Compose parameters, security, OIDC, troubleshooting details |
| [self-host-first-run-guide.md](self-host-first-run-guide.md) | first-run state machine and design notes |
| [api-overview.md](../03-backend/api-overview.md) | full MCP vs REST route table |
| `GET {BASE}/client/agent-onboarding.md` on the instance | onboarding instructions for regular Agents |

**Support**: community best-effort, no SLA.

---

## 0. The Outcome You Are Aiming For

```text
Deploy instance
  → create admin account + API Key
  → create team org (+ optional libraries)
  → send invite links to colleagues (org-internal alias can be preset)
  → colleagues register, auto-join the org, mint their own Keys, configure MCP
  → (recommended) close open registration
```

Principle: **the knowledge loop goes over MCP** (`ma3_context` / `ma3_report` / `ma3_feedback`); **accounts / orgs / invites go over REST or the Web**.

---

## 1. Deployment

### 1.1 Requirements

- Docker + Docker Compose
- Access to the image registry; if embedding models need downloading, the container must reach Hugging Face (or configure `HTTP_PROXY` / `HTTPS_PROXY`)
- For LAN access, set `MA3_PUBLIC_BASE_URL` in `.env` to an address colleagues can open (e.g. `http://192.168.x.x:8010`)

### 1.2 One-Command Startup

```bash
git clone https://github.com/hjk41/ma3.git
cd ma3/deploy/self-host
cp .env.example .env
```

Edit `.env` and change at least:

| Variable | Description |
|------|------|
| `POSTGRES_PASSWORD` | database password |
| `MA3_API_KEY_ENCRYPTION_SECRET` | long random string used to encrypt portal API Keys |
| `MA3_PUBLIC_BASE_URL` | externally reachable root URL (used by invite links) |
| `MA3_PORT` | host-mapped port (default `8000`) |

Then:

```bash
./up.sh
./verify.sh
# Health check
curl -fsS "http://127.0.0.1:${MA3_PORT:-8000}/healthz"
```

Once `./up.sh` succeeds, open `MA3_PUBLIC_BASE_URL` in a browser; if no account exists yet, you enter first-time setup.

### 1.3 Two Things to Know Right After Deployment

1. **Bootstrap API Key** (file inside the container) — can only be used for **MCP knowledge tools**; it **cannot** manage users / complete setup / create orgs:

   ```bash
   docker compose exec ma3 cat /data/bootstrap_api_key.txt
   ```

2. **Local account system** (enabled by default) — when OIDC is not configured, `MA3_LOCAL_AUTH=1`: the first registered user becomes the **instance administrator**.

> Do not treat the bootstrap key as a distribution account; the admin should register a local account and mint their own API Key.

### 1.4 Common Ops Commands

```bash
cd ma3/deploy/self-host
docker compose ps
docker compose logs -f ma3
docker compose restart ma3
# Dangerous: deletes data volumes
# docker compose down -v
```

Volumes to back up: `ma3_pgdata` (database), `ma3_data` (bootstrap key, HF cache).

---

## 2. Initialization: Web UI

Suitable for finishing first-time configuration with a few clicks.

### 2.1 Create the Admin

1. Open `MA3_PUBLIC_BASE_URL` (or `/ui/setup/`).
2. **Create the admin account** (username + password + display name). The first local account automatically becomes admin.
3. After logging in, follow the setup checklist:
   - Go to `/ui/keys/` to **issue an API Key** (for your own Agent)
   - Decide whether to keep open registration (recommended: close it later on a LAN)
   - Click **Complete setup**

### 2.2 Create Orgs and Libraries

1. Open `/ui/orgs/` → **New organization** (requires instance admin or a paid plan that allows it; the first local admin generally can).
2. Enter the org → you can create an **org library** (private by default).
3. Open the **Members** page: add people manually, or generate an invite (see §4).

### 2.3 Common Admin Entry Points

| Page | Purpose |
|------|------|
| `/ui/setup/` | first-run setup |
| `/ui/keys/` | your own API Keys |
| `/ui/orgs/` | orgs / libraries / members / invites |
| `/ui/observatory/` | Observatory (product admins) |
| `/ui/observatory/local-users/` | local accounts, open/close registration |

---

## 3. Initialization: Agent / REST (no browser)

Suitable for bringing the instance to an "invitable" state via Cursor / scripts. Assumes:

```bash
BASE=http://192.168.x.x:8010   # change to your MA3_PUBLIC_BASE_URL
```

### 3.1 Register the Admin and Get a Key

```bash
curl -fsS "$BASE/api/setup/status" | jq

REGISTER=$(curl -fsS -X POST "$BASE/api/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{
    "username":"admin",
    "password":"change-me-long-password",
    "display_name":"Instance Admin",
    "api_key":{"label":"admin-agent"}
  }')
ADMIN_KEY=$(jq -r '.api_key.plaintext_key' <<<"$REGISTER")
echo "ADMIN_KEY=$ADMIN_KEY"
```

### 3.2 Complete Setup

```bash
# If you temporarily rely on open registration to bring people in, set open:true first;
# invite links are preferred (§4) — then close registration
curl -fsS -X PATCH "$BASE/api/setup/registration" \
  -H "X-API-Key: $ADMIN_KEY" -H 'Content-Type: application/json' \
  -d '{"open":false}' | jq

curl -fsS -X POST "$BASE/api/setup/complete" \
  -H "X-API-Key: $ADMIN_KEY" | jq
```

### 3.3 Create Org and Library

```bash
ORG=$(curl -fsS -X POST "$BASE/api/orgs" \
  -H "X-API-Key: $ADMIN_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"Acme Team"}')
ORG_ID=$(jq -r '.id' <<<"$ORG")

LIB=$(curl -fsS -X POST "$BASE/api/orgs/$ORG_ID/libraries" \
  -H "X-API-Key: $ADMIN_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"Eng Notes","visibility":"private"}')
LIB_ID=$(jq -r '.library_id' <<<"$LIB")
echo "ORG_ID=$ORG_ID LIB_ID=$LIB_ID"
```

### 3.4 Hand the Key to the Admin's Own Agent

Configure MCP (example):

- `MA3_BASE_URL=$BASE`
- `X-API-Key=$ADMIN_KEY`

Verify: `ma3_whoami` → `ma3_context` (an empty query is fine) → `ma3_report` when needed.

Detailed tool conventions: `GET $BASE/client/agent-onboarding.md` on the instance.

---

## 4. Onboarding Other Members (recommended: invite links)

**Recommended path**: invite codes/links (work even with open registration closed) + optional **org-internal alias**.

### 4.1 Web: Generate an Invite

1. Open `/ui/orgs/{org}/members/`
2. In the **Invite link** card, fill in:
   - **Org-internal alias** (optional, e.g. "Xiao Ming" — shown in the member list once they join)
   - Role, usage count (default 1), validity period (default 168 hours)
3. **Generate invite**, copy the URL from the page, and send it to your colleague (the plaintext token is **shown only once**).

The colleague opens:

`{MA3_PUBLIC_BASE_URL}/auth/register?invite=ma3inv_…`

After successful registration they automatically join the org; if an alias was set, it appears on the members page immediately.

### 4.2 Agent / REST: Generate an Invite

```bash
INV=$(curl -fsS -X POST "$BASE/api/orgs/$ORG_ID/invites" \
  -H "X-API-Key: $ADMIN_KEY" -H 'Content-Type: application/json' \
  -d '{
    "role":"member",
    "max_uses":1,
    "expires_in_hours":168,
    "member_alias":"Xiao Ming"
  }')
jq '{invite_url, token, member_alias, expires_at}' <<<"$INV"
```

Send `invite_url` to the colleague.

Preview (public):

```bash
curl -fsS "$BASE/api/invites/preview?token=ma3inv_…" | jq
```

Revoke:

```bash
curl -fsS -X DELETE "$BASE/api/orgs/$ORG_ID/invites/{invite_id}" \
  -H "X-API-Key: $ADMIN_KEY"
```

### 4.3 What the Colleague Needs to Do

1. Open the invite link → register an account (with open registration closed, **only a valid invite** allows registration).
2. After logging in, go to `/ui/keys/` and **create their own API Key** (or include `api_key` in the REST registration call).
3. Configure `MA3_BASE_URL` + their own Key into MCP.
4. To write to a specific **private org library**, the admin must also grant library permissions (see below).

Existing accounts can also redeem an invite (no new account created):

```bash
curl -fsS -X POST "$BASE/api/invites/redeem" \
  -H "X-API-Key: $USER_KEY" -H 'Content-Type: application/json' \
  -d '{"token":"ma3inv_…"}'
```

### 4.4 Org-Internal Aliases

| Operation | Method |
|------|------|
| Preset at invite time | `member_alias` / "Org-internal alias" field on the invite form |
| Change later | `PATCH /api/orgs/{id}/members/{principal_id}` `{"alias":"…"}` |
| View | `GET /api/orgs/{id}/members` or the members page table |

An alias is only displayed **within that org**, independent of the global display name; aliases must be unique within an org.

### 4.5 Granting Access to Org Libraries (optional)

Joining an org ≠ automatic write access to every private library. When needed:

**Web**: library detail → Grants.

**REST**:

```bash
curl -fsS -X POST "$BASE/api/libraries/$LIB_ID/grants" \
  -H "X-API-Key: $ADMIN_KEY" -H 'Content-Type: application/json' \
  -d '{"username":"alice","role":"writer"}'
```

### 4.6 Alternative: Open Registration + Manual Adds

Not recommended as the default (on a LAN, anyone can register), but usable:

1. `PATCH /api/setup/registration` `{"open":true}` or open registration in the Observatory.
2. Colleagues self-register via `/auth/register`.
3. The admin adds them on the members page, or `POST /api/orgs/{id}/members` (can include `alias`).
4. Once everyone is in, **close registration**.

---

## 5. Division of Roles Quick Reference (avoid using the wrong Key)

| Credential | Can do | Cannot do |
|------|----------|------------|
| Bootstrap key | MCP knowledge reads/writes (if grants allow) | manage users, complete setup, create orgs, send invites |
| Admin user API Key | setup, local users, orgs, invites, library grants, own keys | — |
| Regular user API Key | own keys, MCP (per its grants), redeem invites | manage others / send org invites (unless org admin) |

---

## 6. Recommended Security Checklist

- [ ] Passwords and encryption secrets in `.env` changed to strong random values  
- [ ] `MA3_PUBLIC_BASE_URL` points to a genuinely reachable address (so invite links are correct)  
- [ ] Admin has minted a **non-bootstrap** API Key  
- [ ] People are onboarded primarily via **invite links**; **close open registration** once everyone is in  
- [ ] Not exposed bare on the public internet: use a TLS reverse proxy for public exposure (see `deploy/self-host/Caddyfile.example`)  
- [ ] Do **not** enable `MA3_DEV_AUTH` on the public internet  
- [ ] Regularly back up `ma3_pgdata` / `ma3_data`

---

## 7. Troubleshooting Quick Reference

| Symptom | Check |
|------|------|
| `/healthz` unreachable | `docker compose ps` / `logs`; port and firewall |
| Registration 403 | open registration closed and no valid invite |
| Invite 410 | expired, used up, or revoked; regenerate |
| Invite link has wrong domain | fix `MA3_PUBLIC_BASE_URL`, then regenerate the invite |
| Bootstrap key calling admin API 403 | switch to an admin user Key |
| Library not visible over MCP after joining org | check library grants / key grants |
| Embedding stuck | proxy, `MA3_DISABLE_EMBEDDINGS=1` (weak machines) |

For more detailed Compose / OIDC notes see [self-hosting.md](self-hosting.md).
