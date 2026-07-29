# Authentication

> Chinese version: [authentication.zh.md](authentication.zh.md)

> Session is used for the **Web UI**; for the MCP data path see [authorization-and-libraries.md](authorization-and-libraries.md).

## Two authentication tracks

| Track | Credential | Purpose |
|----|------|------|
| **Human (browser)** | Authing OIDC → session cookie | Portal, `/ui/keys/*`, Observatory |
| **Agent (MCP)** | `X-API-Key` header | All MCP tools |

A bearer token does **not** grant MCP data access.

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
