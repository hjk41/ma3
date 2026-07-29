# ADR-005 — Observatory read-only UI ships in v1

> Chinese version: [005-observatory-ui-scope.zh.md](005-observatory-ui-scope.zh.md)

## Status

Accepted (2026-07-01)

## Context

Q11: does v1 need a UI. **Maintainers** (human or agent) need to "see what's in the library and why it matched," consistent with P4 explainable search.

## Decision

**v1 includes Observatory (read-only)**, routed at `/ui/observatory/*`:

| Page | Function |
|------|------|
| Overview | Deploy banner, library statistics, doctor summary |
| Cases | Case list and detail |
| Records | Record detail, relations |
| Search | Query + explain panel (internal ranking breakdown logic; explain is **not** exposed via MCP, to prevent ranking manipulation/SEO abuse) |

**v1 is primarily read-only browsing**; **human maintainers** additionally have write actions (consistent with ADR-007/008, aligned with Pitch §Maintenance layers):

| Write action | Description |
|--------|------|
| Mark record **invalid** | Corrects stale or erroneous entries |
| **Revoke / override** an agent maintainer's action | Restores mistakenly flagged/deleted items |
| Clear content that violates privacy/values policy | Final judgment call |

**Not included in v1:**

- The full review queue UI (draft approval goes through MCP or ships in v1.1)
- Org/seat/billing management

Observatory uses the OIDC session (SaaS) or **human maintainer** cookie/API under dev_auth (LAN profile). **Agent maintainers** use a library_maintainer/admin API key + MCP, and do not depend on the UI.

## Consequences

### Positive

- Humans can verify agent write-backs and search behavior
- Consistent with the North Star that "maintainers can answer what's in the library"; agents can participate in equivalent maintenance actions via MCP

### Negative

- Requires maintaining an HTML/JS or server-template layer
- Requires reusing auth and library ACL on the UI path

### Related

- Q11=B
- Portions of the old `server/app/api/routes_ui.py` can be reused
