# ADR-015 — Pluggable OIDC + self-host bootstrap keys

- **Status**: Accepted
- **Date**: 2026-07-20
- **Deciders**: product owner

## Context

Self-hosting users need human login against **their own IdP**, without depending on Authing. Many lab deployments also need MCP to work **with no IdP at all**.

## Decision

1. **OIDC is the human login protocol.** Prefer env prefix `MA3_OIDC_*` (`ISSUER`, `CLIENT_ID`, `CLIENT_SECRET`, redirect URIs). Discovery uses standard `/.well-known/openid-configuration`.
2. **`MA3_AUTHING_*` remains a compatibility alias** that maps onto the same settings. Authing issuers still get optional `/oidc` path normalization (`oidc_authing_path_compat`).
3. **When OIDC is not configured**:
   - Default **`MA3_BOOTSTRAP_SELFHOST=1`**: on startup, create (idempotently) a personal-library writer API key and write plaintext to `MA3_BOOTSTRAP_KEY_FILE` (default `./data/bootstrap_api_key.txt`) for MCP agents.
   - Default **`MA3_LOCAL_AUTH=1`**: username/password portal accounts (`local_accounts` table, argon2 hashes, signed `ma3_session` cookie). First registered user is admin; admins manage users at `/ui/observatory/local-users/`. Open registration can be closed with `MA3_LOCAL_AUTH_OPEN_REGISTRATION=0`.
   - Set `MA3_LOCAL_AUTH=0` to keep the older bootstrap-only path (portal `/ui/me/` unavailable).
4. **When OIDC is configured**, local auth is **off** (OIDC is the only portal login). Bootstrap auto-create is skipped.
5. **`MA3_DEV_AUTH` stays a break-glass** for developers; it must stay **off** in self-host Compose defaults and must not replace bootstrap for production-like self-host.

## Consequences

- Authing is documented as one OIDC provider example, not the only code path.
- Self-host Compose can ship “MCP-ready in minutes” without registering an IdP, **and** operators can use a simple local portal without Authing.
- Operators must protect the bootstrap key file (mode 0600; volume secret) and treat the first local admin like a root account.
- Full multi-IdP claim mapping quirks are validated opportunistically (P1 compatibility matrix).

## Amendment (2026-07-28)

Local portal auth (`MA3_LOCAL_AUTH`) was added so self-host no longer requires OIDC for `/ui/me/` and `/ui/keys/`. ADR decision (3) above supersedes the earlier “portal unavailable until OIDC” wording.

## References

- [self-hosting.md](../../06-operations/self-hosting.md)
- [self-hosting-mvp-checklist.md](../../06-operations/self-hosting-mvp-checklist.md)
- ADR-010 (Authing) — partially superseded for “Authing-only” framing; Authing still supported
