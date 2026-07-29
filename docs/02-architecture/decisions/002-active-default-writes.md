# ADR-002 — `ma3_report` defaults to active

> Chinese version: [002-active-default-writes.zh.md](002-active-default-writes.zh.md)

## Status

Accepted (2026-07-01)

## Context

Q5 required choosing among draft / active / library-level configuration. There is tension between verified knowledge (P1) and immediate visibility.

## Decision

- **`ma3_report` writes with `status=active` by default**, consistently across all library types
- **`draft` only applies when** the payload explicitly sets `visibility=draft` (or a future library-level enforced policy, not enabled by default in v1)
- The MCP response must include `status: "active"`, and **must not** default to `requires_manual_review`
- **Hook / agent-memory candidates** remain separate from Records and **must not** be auto-activated (per Q2/P1)

## Consequences

### Positive

- After an agent writes back, it is immediately visible via `ma3_context`, keeping the loop simple
- Consistent with the current `immediate_visibility` behavior on LAN, keeping migration cost low

### Negative

- Mis-written or low-quality records enter the search index directly
- Requires reliance on ranking, manual `invalid` marking via Observatory, and validate/redaction in the agent policy

### Mitigations (required in v1, aligned with Pitch §Maintenance layers)

1. Search ranking down-weights low-signal records (explain is extensible)
2. **Agent maintainer** routinely flags suspected stale entries (auditable)
3. **Human maintainer** **corrects** the agent maintainer via Observatory, and clears content that violates privacy/values policy
4. Policy enforces a pre-write dry-run + automatic redaction
5. `ma3_list_drafts` / `ma3_review_record` are for the maintainer agent; humans do not block the default write path

### Related

- Q5, P1, P6
- MCP `ma3_report` response schema
