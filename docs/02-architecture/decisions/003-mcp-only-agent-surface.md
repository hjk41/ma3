# ADR-003 — Agent surface is MCP + policy only; CLI and install.sh removed

> Chinese version: [003-mcp-only-agent-surface.zh.md](003-mcp-only-agent-surface.zh.md)

## Status

Accepted (2026-07-01), **client sync details are in [ADR-009](009-client-sync-scheme-b.md)**

## Context

North Star: "MCP + one policy." The old repo had install.sh, the ma3_client.py CLI, a Codex skill directory, and multiple AGENTS.md copies, which violates P2.

## Decision

**Core agent onboarding retained:**

1. Remote MCP `POST /mcp`
2. `GET /client/manifest.json`
3. `GET /client/templates/ma3-agent-policy.mdc`
4. `GET /client/agent-onboarding.md`

**ADR-009 extensions (still not the ma3 CLI):**

5. `GET /client/templates/ma3-client.env.example` — agent fills in local paths itself
6. `GET /client/scripts/sync_ma3_client.{sh,py}` + `GET /client/lib/ma3_sync_core.py` — manifest-driven sync / self-updating tooling
7. `GET /client/mcp-tools.json` — MCP tools snapshot

**Removed / not migrated in v1:**

- `client/install.sh`
- `client/skills/ma3/scripts/ma3_client.py` and all CLI subcommands
- The in-repo parallel `AGENTS.md` meant for agents to copy (operational content moved into deploy docs)

**Retained (not part of the agent surface):**

- Maintainer REST (key management, health)
- Observatory UI
- `ma3_doctor` / `ma3_whoami` via MCP

There is no offline CLI for the **ma3 write path**; when the network fails, the agent skips ma3 and gives a brief explanation (already covered by policy).

Client refresh goes through the **sync scripts + manifest** (ADR-009), or a minimal bootstrap via plain curl; both are read-only HTTP pulls.

## Consequences

### Positive

- A single MCP write contract; a clear server-block + manifest upgrade path
- Reduces documentation and code drift
- Multiple runtimes are handled by having the agent fill in the env; the repo does not maintain N sets of presets

### Negative

- Cannot use a CLI for diagnostics in a non-HTTP environment (curl against MCP or the doctor HTTP endpoint can substitute)
- Existing users relying on install.sh need to change onboarding (env template + sync, or curl for the policy)
- MCP schema changes still require an in-IDE reload

### Related

- Q4, Q7, P2
- [ADR-009](009-client-sync-scheme-b.md) client sync Scheme B
- `05-doc-code-mapping.md` client section
