# Administrator Guide

> Chinese version: [administrator-guide.zh.md](administrator-guide.zh.md)

> **Status**: For self-hosted operations, the operations runbooks are authoritative; this document keeps the SaaS / Observatory entry points.

## Self-hosted instance administrators (recommended)

Full steps (deployment, Web/Agent initialization, inviting members, aliases, MCP):

→ **[self-host-admin-guide.md](../06-operations/self-host-admin-guide.md)**

Technical details: [self-hosting.md](../06-operations/self-hosting.md), [api-overview.md](../03-backend/api-overview.md).

## Product administrators (Observatory)

| Capability | Path | Notes |
|------|------|------|
| Global Stats + enumeration | `/ui/observatory/` | Local admin or `MA3_AUTH_ADMIN_USERS` |
| Local accounts / registration toggle | `/ui/observatory/local-users/` | Common in self-host |
| User billing plan | `/ui/observatory/users/` or `PATCH /api/admin/users/{id}/plan` | |
| Record detail | `/ui/records/{id}` | Same route as regular users |

## Platform operations (OIDC / public internet)

| Task | Reference |
|------|------|
| Configure OIDC / Authing | [self-hosting.md](../06-operations/self-hosting.md), [deployment-authing.md](../06-operations/deployment-authing.md) |
| Admin allowlist | `MA3_AUTH_ADMIN_USERS` |
| TLS reverse proxy | `deploy/self-host/Caddyfile.example` |

## To be added (SaaS)

- [ ] Screenshot-level Observatory walkthrough
- [ ] Content moderation process (invalid records, privacy deletions)
- [ ] User support escalation path
