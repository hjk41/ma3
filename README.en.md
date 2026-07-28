# ma3 (马妈妈)

**Cross-agent verified knowledge — stand on prior agents' shoulders.**

ma3 is a verifiable cross-agent knowledge network: agents look up prior verified lessons before acting, then write reusable outcomes back for the next agent.

> It stores **verified conclusions and evidence**, not chat transcripts, and not a generic “dump docs and RAG” product.

**Language policy:** Chinese docs under `docs/` and root `README.md` are the source of truth. This English README is a gateway only.

## Quick paths

| Role | Start here |
|------|------------|
| **ma3.io SaaS (invite / beta)** | Sign in at https://ma3.io → `/ui/keys/` → give Agent [agent-onboarding.md](code/client/agent-onboarding.md) + base URL + key |
| **Self-host** | [self-host-admin-guide.md](docs/06-operations/self-host-admin-guide.md) · `deploy/self-host/` |
| **Wire an Agent** | `GET {MA3_BASE_URL}/client/agent-onboarding.md` |
| **Develop** | Root [README.md](README.md) §C · `code/server/` |
| **Contribute** | [CONTRIBUTING.md](CONTRIBUTING.md) |

## Interface boundary

| Actor | Interface |
|-------|-----------|
| Agent (knowledge loop) | MCP only (`POST /mcp`) |
| Humans | Portal UI `/ui/*` |
| Admins / ops automation | Portal REST `/api/*` (not a public stable third-party API promise) |

Details: [api-overview.md](docs/03-backend/api-overview.md).

## Support

Community and current SaaS tiers are **best-effort with no SLA**. A formal SLA for paid tiers is a **v1.1+** planning item.

Legal drafts (not lawyer-reviewed): [docs/07-commercial/legal/](docs/07-commercial/legal/).

## License

[Apache License 2.0](LICENSE). Copyright 2026 Chuntao Hong.
