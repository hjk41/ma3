# External System Integrations

> Chinese version: [external-integrations.zh.md](external-integrations.zh.md)

> **Status**: Partially finalized — deployment details in [../06-operations/deployment-authing.md](../06-operations/deployment-authing.md)

## System Context

```text
                    ┌─────────────┐
  Agent (MCP) ─────►│             │◄───── Authing OIDC (human login)
  X-API-Key         │  ma3 server │       session cookie
                    │             │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         PostgreSQL    HF embeddings   HTTP client bundle
         (or SQLite)   (optional off)   manifest/policy/sync
```

## Integration Inventory

| External system | Purpose | Protocol | Docs |
|----------|------|------|------|
| **Authing** | User signup/login; Observatory/portal session | OIDC authorization_code | [deployment-authing.md](../06-operations/deployment-authing.md) |
| **PostgreSQL** | Production data, FTS, pgvector | SQL | [deployment.md](../06-operations/deployment.md) |
| **SQLite** | Testing / local dev | SQL | — |
| **Hugging Face** | sentence-transformers cache | Local HF_HOME; offline in production | [system-overview.md](system-overview.md) §7 |
| **Agent IDE** | Cursor / Claude Code / Codex, etc. | MCP JSON-RPC over HTTP | [../05-agent/getting-started.md](../05-agent/getting-started.md) |
| **Stripe** | Payments (v1.1) | Webhook stub | [../03-backend/billing-and-quotas.md](../03-backend/billing-and-quotas.md) §8 |

## Boundary Conventions

| Surface | Credential | Capabilities |
|----|------|------|
| **MCP data path** | `X-API-Key` only | Read/write records, search, feedback |
| **Web UI** | Authing session cookie | Portal, key management, Observatory (admin) |
| **Bearer on MCP** | — | Grants **no** data access (anonymous / bearer reads abolished) |

## To Be Added

- [ ] Production domain / TLS / reverse proxy topology diagram
- [ ] Backup and restore (Postgres)
- [ ] Multi-instance deployment and session stickiness (if needed)
