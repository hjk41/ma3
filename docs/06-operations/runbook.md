# Operations Runbook

> Chinese version: [runbook.zh.md](runbook.zh.md)

> TODO(v1.1): complete release/rollback/migration steps (see checklist at the end); currently covers only a quick reference of common operations.

## Common Operations (placeholder)

| Scenario | Steps | Doc |
|------|------|------|
| First Authing deployment | console + env + verification curl | [deployment-authing.md](deployment-authing.md) |
| Add a product admin | update `MA3_AUTH_ADMIN_USERS` + restart | [authentication.md](../03-backend/authentication.md) |
| User cannot log in | check callback URL, issuer, cookies | deployment-authing |
| MCP 401 | key deleted/expired? `ma3_doctor` | [getting-started.md](../05-agent/getting-started.md) |
| Search has no vector | `MA3_DISABLE_EMBEDDINGS`, HF cache | [system-overview.md](../02-architecture/system-overview.md) |
| Startup fails on admin allowlist | set `MA3_AUTH_ADMIN_USERS` | portal-permissions |

> TODO(v1.1):
>
> - Release steps (rsync, migrate, restart, smoke test)
> - Rollback procedure
> - Database migration execution and verification
> - Log locations and common greps
> - On-call contacts
