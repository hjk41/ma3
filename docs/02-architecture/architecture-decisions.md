# Architecture Decision Records (ADR Index)

> Chinese version: [architecture-decisions.zh.md](architecture-decisions.zh.md)

> ADR bodies live in the [decisions/](decisions/) directory.

| ADR | Topic | Body |
|-----|------|------|
| 001 | SaaS as primary deployment | [001-saas-primary-deploy.md](decisions/001-saas-primary-deploy.md) |
| 002 | Write-back defaults to active | [002-active-default-writes.md](decisions/002-active-default-writes.md) |
| 003 | MCP-only Agent surface | [003-mcp-only-agent-surface.md](decisions/003-mcp-only-agent-surface.md) |
| 004 | Vector default on | [004-vector-default-optional-off.md](decisions/004-vector-default-optional-off.md) |
| 005 | Observatory scope | [005-observatory-ui-scope.md](decisions/005-observatory-ui-scope.md) |
| 006 | Hook candidates local-first | [006-hook-candidates-local-first.md](decisions/006-hook-candidates-local-first.md) |
| 007 | Milestones and Observatory governance | [007-v1-milestones-and-observatory-governance.md](decisions/007-v1-milestones-and-observatory-governance.md) |
| 008 | Maintainer: human or agent | [008-maintainer-human-or-agent.md](decisions/008-maintainer-human-or-agent.md) |
| 009 | Client sync Scheme B | [009-client-sync-scheme-b.md](decisions/009-client-sync-scheme-b.md) |
| 010 | Authing social login | [010-authing-social-login.md](decisions/010-authing-social-login.md) |
| 011 | KB access and org isolation | [011-kb-access-and-org-isolation.md](decisions/011-kb-access-and-org-isolation.md) |
| 012 | Billing and quotas | [012-billing-and-quotas.md](decisions/012-billing-and-quotas.md) |
| 013 | Write confirmation, audit, delete | [013-write-confirmation-audit-delete.md](decisions/013-write-confirmation-audit-delete.md) |
| 014 | MCP errors are self-correctable | [014-mcp-error-self-correction.md](decisions/014-mcp-error-self-correction.md) |
| 015 | Pluggable OIDC + self-hosted bootstrap key | [015-oidc-pluggable-selfhost-bootstrap.md](decisions/015-oidc-pluggable-selfhost-bootstrap.md) |
| 016 | MCP OAuth (Auth Spec) + API Key dual-auth | [016-mcp-oauth-plus-api-keys.md](decisions/016-mcp-oauth-plus-api-keys.md) |

## Product-level decisions (no standalone ADR)

| Decision | Summary | Spec |
|------|------|------|
| Observatory non-admin → 403 | Not 302 | [portal-permissions.md](../04-frontend/portal-permissions.md) |
| Stats ≠ Enumerate | Regular users get Stats + deep links only | Same as above |
| API Key deletion is non-revocable | Hard delete of the row | [api-keys-ui-and-api.md](../04-frontend/api-keys-ui-and-api.md) |
| Display name one-time setup | Globally unique | [display-name-registration.md](../04-frontend/display-name-registration.md) |
| Search GTN Option B | Relevance-first + wrong_tier | [search-and-ranking.md](../03-backend/search-and-ranking.md) |

## New ADR process

1. Copy [decisions/000-template.md](decisions/000-template.md)
2. Increment the number, status Accepted / Superseded
3. Update this index + related backend/frontend spec docs
