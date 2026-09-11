# Authentication

> Chinese version: [authentication.zh.md](authentication.zh.md)

> Session is used for the **Web UI**; MCP data credentials are API keys or ma3-issued MCP OAuth tokens — see [authorization-and-libraries.md](authorization-and-libraries.md) and [ADR-016](../02-architecture/decisions/016-mcp-oauth-plus-api-keys.md).

## Authentication tracks

| Track | Credential | Purpose |
|----|------|------|
| **Human (browser)** | Authing OIDC / local auth → session cookie | Portal, `/ui/keys/*`, Observatory; also completes MCP OAuth authorize |
| **Interactive MCP client** (Cursor, etc.) | MCP Authorization Spec OAuth → **ma3 MCP access token** | MCP tools with Layer-1 entitlement projection |
| **Agent / CI (MCP)** | `X-API-Key` (or Bearer-as-key) | MCP tools with Layer-2 `api_key_grants` |

**Bare Authing / OIDC access tokens do not grant MCP data access.** Only ma3-issued `ma3mcp_…` tokens (resource-bound) or API keys do.

## MCP OAuth (spec login)

```text
POST /mcp (no credential)
  → 401 + WWW-Authenticate: Bearer resource_metadata="…/.well-known/oauth-protected-resource"
GET /.well-known/oauth-protected-resource
  → resource, authorization_servers
GET /oauth/authorize (PKCE S256) → /auth/login if needed → redirect with code
POST /oauth/token → ma3 access_token (audience = {PUBLIC_BASE_URL}/mcp)
POST /mcp Authorization: Bearer ma3mcp_…
```

**Public base URL (required for production / reverse proxies):** set `MA3_PUBLIC_BASE_URL` to the external origin clients use (e.g. `https://ma3.io`). PRM, `WWW-Authenticate`, authorize/token `resource`, and portal paste-to-agent blocks prefer this value. If unset, ma3 falls back to the request `Host` (handy for LAN/dev) — do **not** expose that mode on the public internet without a trusted proxy / Host allowlist; spoofed `Host` can poison OAuth metadata.

Env knobs: `MA3_MCP_OAUTH_ACCESS_TOKEN_TTL_SEC` (default 3600), `MA3_MCP_OAUTH_AUTH_CODE_TTL_SEC`, `MA3_MCP_OAUTH_REDIRECT_URI_ALLOWLIST` (localhost / `cursor://` always allowed).

## Authing login flow

```text
GET /ui/me/ (no session)
  → 302 /auth/login?next=...
  → 302 Authing authorize
  → GET /auth/callback?code=...
  → ensure_user_principal + ensure_personal_library
  → if display_name_locked=0 → 302 /ui/me/setup/
  → otherwise 302 next (default /ui/me/)
```

See [../06-operations/deployment-authing.md](../06-operations/deployment-authing.md) for configuration.

## Session user model

```python
SessionUser:
  principal_id: str      # user:{authing_sub}
  display_name: str
  is_admin: bool         # matched against MA3_AUTH_ADMIN_USERS
```

## Startup validation

When `settings.authing_configured and not settings.auth_admin_users`:

- **Refuses to start** (same severity as a misconfigured DB)
- `ma3_doctor` reports a failure
- LAN `authing_enabled=False` is **not restricted**

## Dev break-glass

| Variable | Purpose |
|------|------|
| `MA3_DEV_AUTH=1` | Skip OIDC on LAN |
| `MA3_DEV_API_KEY` | Single-key admin bypass (MCP) |

## Display name gating

Before completing [display-name-registration](../04-frontend/display-name-registration.md):

- Portal routes → 302 `/ui/me/setup/`
- `GET /api/keys` → 403

## TODO

- [ ] Session cookie name, TTL, security flags
- [ ] Authing user attribute → principal field mapping table
- [ ] Logout / session invalidation behavior
- [ ] Optional refresh tokens / Dynamic Client Registration
