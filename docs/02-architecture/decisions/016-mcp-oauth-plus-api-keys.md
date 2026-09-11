# ADR-016 — MCP Authorization Spec OAuth + API Key dual-auth

> Chinese version: [016-mcp-oauth-plus-api-keys.zh.md](016-mcp-oauth-plus-api-keys.zh.md)

## Status

Accepted (2026-09-11)

## Context

MCP clients such as Cursor can perform interactive OAuth (RFC 9728 Protected Resource Metadata + OAuth 2.1 + PKCE + RFC 8707 `resource`). Agents and CI still need non-interactive credentials.

Prior ADRs split human UI (Authing/OIDC session) from agent MCP (`X-API-Key`). Code also accepted a narrow **bare Authing access token** as Bearer for MCP, mapping only to `lib_default`, which:

- lacks MCP resource/`aud` binding
- diverges from portal Layer-1 entitlements
- conflicts with ADR-011 (“Bearer is not an MCP data credential”)

## Decision

1. **Protocol**: ma3 is both the MCP resource server and a lightweight authorization server implementing the MCP Authorization Spec (PRM, AS metadata, authorize with PKCE S256, token endpoint).
2. **IdP**: Authing/OIDC (or local auth) remains the **human login** path only. Authorize reuses existing `/auth/*` session establishment.
3. **MCP access tokens**: **ma3-issued opaque tokens** stored as SHA-256 hashes in `mcp_oauth_tokens`, bound to `resource` (= public MCP URL). Short TTL; revocable by deleting the row.
4. **OAuth permissions (option A)**: project the signed-in principal’s **Layer-1 entitlements** into `grant_readable` / `grant_writable` / `grant_maintainer` (same shape as API key grants). No new key is required for interactive clients.
5. **API keys unchanged**: `X-API-Key: ma3k_…` / `Authorization: Bearer ma3k_…` continue as the Agent/CI path via `api_key_grants` (Layer 2). Credential resolution order: **DB API key** (including Bearer-as-key) → env/dev keys → **ma3 MCP OAuth token**. Bare Authing access tokens **no longer** grant MCP data tools. OAuth permissions are **strict Layer-1** (no API key grant projection).
6. **401 challenge**: authenticated MCP failures include `WWW-Authenticate: Bearer resource_metadata="…"`, alongside JSON-RPC `-32001`. Public base for PRM/challenge/resource prefers `MA3_PUBLIC_BASE_URL`, else the request Host (localhost aliases accepted).

## Consequences

### Positive

- Cursor-style popup login without minting a key first
- MCP OAuth permissions match portal-visible libraries
- Agents/CI keep the existing key path
- Audience/resource binding closes the bare-Authing Bearer bypass

### Negative

- OAuth token ≈ session capability; must stay short-lived, HTTPS-only, and revocable
- Self-host without portal auth: OAuth path unavailable; keys/bootstrap remain
- Client CIMD/DCR quirks need real-client validation (redirect allowlist first)

### Related

- Supersedes ADR-010 agent wording “MCP does not go through Authing” for the **interactive OAuth** path (Authing is still only the human IdP; ma3 issues MCP tokens)
- Revises ADR-011: bare Authing Bearer stays out of MCP; **ma3 MCP OAuth tokens may enter**
- ADR-015: self-host without OIDC uses local auth for authorize when available
- Specs: [authentication.md](../../03-backend/authentication.md), [authorization-and-libraries.md](../../03-backend/authorization-and-libraries.md)
