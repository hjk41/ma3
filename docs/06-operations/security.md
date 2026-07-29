# Security Specification

> Chinese version: [security.zh.md](security.zh.md)

> **Status**: partially finalized — scattered specs absorbed

## Authentication and Keys

| Item | Measure |
|----|------|
| API key storage | SHA-256 hash + Fernet ciphertext only; plaintext never persisted to DB or logs |
| Key transport | HTTPS; `X-API-Key` header |
| Key invalidation | hard delete or legacy `revoked_at` |
| Session | Authing OIDC; mutating UI/API same-origin |
| Dev bypass | LAN only; `MA3_DEV_AUTH` forbidden on public internet |

## Authorization

- MCP: **only** DB keys + dev bypass; no anonymous reads
- key grants ⊆ owner entitlement; free tier Community writer locked
- Privilege escalation attempts: 404 (existence-oracle protection)
- Observatory: admin only → 403

## MCP Errors and Leakage

- `error.message` contains no secrets, stack traces, or SQL
- search explain is **not** returned via MCP (ADR-005 / anti rank-gaming)

## Writes and Content

- Write buffer: buffered records invisible to others
- Human — maintainers: remove privacy/values-noncompliant content (ADR-008)
- `ma3_ui_session` is **forbidden** for signing keys

## To Be Added

- [ ] Threat model (lightweight STRIDE)
- [ ] Dependency vulnerability scanning process
- [ ] Penetration testing / security review cadence
- [ ] Data retention and GDPR/PII handling
