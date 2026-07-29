# ADR-010 — Authing B2C social login (Observatory)

> Chinese version: [010-authing-social-login.zh.md](010-authing-social-login.zh.md)

## Status

Accepted (2026-07-01)

## Context

v1 needs a "friendly for regular people" login method (WeChat, SMS verification code), while agents continue to use API keys. ADR-001 already settled SaaS as the primary form factor; ADR-005 settled that Observatory uses an OIDC session.

After evaluation, **Authing's public cloud B2C free tier (8000 MAU)** was selected as the initial human login gateway; LAN host 202 continues to use `MA3_DEV_AUTH` and is not required to use Authing.

## Decision

1. **Observatory / human maintainer UI** logs in via **Authing OIDC authorization code flow**.
2. **MCP / agents** continue to use `X-API-Key` / library keys, and **do not go through Authing**.
3. On successful login, ma3 **upserts `principals`** (`kind=user`), with `sso_user` = the Authing `sub`.
4. Session: an **HttpOnly cookie** stores `access_token`; requests are validated against Authing's **userinfo** endpoint with a short in-memory cache.
5. Enable condition: `MA3_AUTHING_ENABLED=1` with `MA3_AUTHING_ISSUER`, `MA3_AUTHING_APP_ID`, `MA3_AUTHING_APP_SECRET` configured.
6. **Admins**: `MA3_AUTH_ADMIN_USERS` (comma-separated sub / phone / email / username) → shows an admin badge in Observatory; library ACL still goes through `library_access` (to be completed in v1.1).

## Environment variables

| Variable | Required | Description |
|------|------|------|
| `MA3_AUTHING_ENABLED` | `1` to enable | Turns on the Observatory login gate |
| `MA3_AUTHING_ISSUER` | ✅ | e.g. `https://<pool>.authing.cn/oidc` |
| `MA3_AUTHING_APP_ID` | ✅ | Authing application ID |
| `MA3_AUTHING_APP_SECRET` | ✅ | Application secret (server-side only) |
| `MA3_PUBLIC_BASE_URL` | Recommended | Used to generate the callback URL, e.g. `https://ma3.example.com` |
| `MA3_AUTHING_REDIRECT_URI` | Optional | Defaults to `{PUBLIC_BASE_URL}/auth/callback` |
| `MA3_AUTH_SESSION_COOKIE` | Optional | Defaults to `ma3_session` |
| `MA3_AUTH_ADMIN_USERS` | Optional | List of admin identifiers |
| `MA3_DEV_AUTH` | LAN | When `1`, the MCP dev key still works; can coexist with Authing |

## Authing console configuration

1. Create a **B2C user pool** + a **self-built application** (Web).
2. Authorization mode: enable **authorization_code**, response type **code**.
3. Login callback URL: `{MA3_PUBLIC_BASE_URL}/auth/callback`
4. Logout callback URL: `{MA3_PUBLIC_BASE_URL}/ui/observatory/`
5. Login methods: enable **WeChat** and **phone number verification code** (configure SMS per console instructions).
6. Scope: `openid profile phone email` (as needed).

## ma3 routes

| Route | Description |
|------|------|
| `GET /auth/login` | Redirects to the Authing authorization page |
| `GET /auth/callback` | Exchanges the authorization code for a token, sets the cookie, redirects to `next` |
| `POST /auth/logout` | Clears the cookie, redirects to Authing logout (optional) |
| `GET /auth/whoami` | JSON for the currently logged-in user |

Observatory: when `MA3_AUTHING_ENABLED=1`, unauthenticated access to `/ui/observatory/*` → 302 to `/auth/login`.

## Consequences

### Positive

- Users only see WeChat/SMS buttons (Authing-hosted login page)
- The free tier can support early MAU
- Zero changes to the agent path

### Negative

- Depends on Authing's availability; SMS/WeChat open platform must be configured separately
- Overseas social logins (Google/Apple) can be added later via an Authing connector or a second issuer (v1.1)

### Related

- ADR-001, 005, 008
- [deployment-authing.md](../../06-operations/deployment-authing.md)
