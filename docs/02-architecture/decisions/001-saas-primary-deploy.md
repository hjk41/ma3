# ADR-001 — Multi-tenant SaaS as the primary v1 deployment form factor

> Chinese version: [001-saas-primary-deploy.zh.md](001-saas-primary-deploy.zh.md)

## Status

Accepted (2026-07-01)

## Context

The old repo carried LAN experiments, LTP intranet, and v4 SaaS docs at the same time, with auth and the data model tangled together. Q1 needed a chosen default form factor to finalize the architecture.

## Decision

- **v1 primary form factor = B: multi-tenant SaaS** (org + library + OIDC + library keys)
- **LAN / self-hosted = dev profile** (`MA3_DEV_AUTH=1`), **the same server binary** as SaaS, not a fork
- The org table **ships in v1** (Q3=B): every library must be attached to an `org_id`; single-node deployments use an implicit `org_default`

## Consequences

### Positive

- Consistent with the v4 design docs, avoiding a second migration
- Environments like 202 (LAN) become real dev testbeds rather than "another ma3"
- Auth, ACL, and Observatory boundaries can be written clearly

### Negative

- v1 implementation scope is larger than a "pure LAN core"
- Must emphasize in the profile-lan docs: dev_auth must not be used for public-facing SaaS

### Related

- Q1=B, Q3=B
- [deployment.md](../../06-operations/deployment.md) — SaaS profile (profile-saas details still to be filled in)
- [authorization-and-libraries.md](../../03-backend/authorization-and-libraries.md) — source of truth for org and ACL design
