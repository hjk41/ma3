# ADR-009 — Client sync (Scheme B): agent self-fills env + self-updating manifest

> Chinese version: [009-client-sync-scheme-b.zh.md](009-client-sync-scheme-b.zh.md)

## Status

Accepted (2026-07-01)

## Context

ADR-003 settled on "MCP + policy, no CLI," but did not specify:

1. **Multiple agent runtimes** (Cursor, Codex, Claude Code, Droid…) each have different policy/MCP paths; maintaining per-runtime presets in the repo does not scale.
2. **Two client version layers**: policy/onboarding (skill bundle) and the MCP `tools/list` schema (tool schema) upgrade on different cadences.
3. **The sync scripts themselves** will evolve alongside the server; users cannot be required to clone the repo or manually replace scripts.

The old repo's `install.sh` / `ma3_client.py` CLI has been removed; a lightweight, HTTP-bootstrappable replacement is needed.

## Decision

### 1. Not a CLI — an HTTP-served sync toolchain

v1 **does not reintroduce** `ma3_client.py` subcommands or `install.sh`. Instead it provides:

| HTTP path | Purpose |
|-----------|------|
| `GET /client/manifest.json` | Version + sha256/url for every bundle file |
| `GET /client/templates/ma3-client.env.example` | **Agent-filled** local path template |
| `GET /client/scripts/sync_ma3_client.{sh,py}` | Sync entry point (stdlib + thin wrapper) |
| `GET /client/lib/ma3_sync_core.py` | Sync core (stdlib only, can be copied standalone) |
| `GET /client/templates/ma3-agent-policy.mdc` | Behavior policy bundle |
| `GET /client/agent-onboarding.md` | Operational instructions |
| `GET /client/mcp-tools.json` | MCP tools/list snapshot |

Implementation: `code/client/lib/ma3_sync_core.py` (source of truth); `server/app/services/client_sync.py` only re-exports for test adaptation.

### 2. Agent self-fills the env; the repo does not maintain runtime presets

- Template: `ma3-client.env.example` (served over HTTP)
- During onboarding, the agent copies it to `~/.ma3/ma3-client.env` and edits:
  - `MA3_BASE_URL`
  - Install directory (default `~/.ma3`)
  - Relative paths for bundle files on disk (`MA3_POLICY_REL`, etc.)
  - **Example comments**: how to copy the policy to Cursor/Codex/Claude/Droid (executed by the agent, not hardcoded by ma3)

`sync_ma3_client.sh` **sources this env** at startup; per-runtime differences are handled as a one-time configuration step on the agent side.

### 3. Scheme B — local state is the source of truth for versions

| Local file | Purpose |
|----------|------|
| `~/.ma3/ma3-client.env` | Paths and base URL (agent-maintained) |
| `~/.ma3/ma3-client.json` | Synced versions + file sha256 + flags |
| `~/.ma3/policy/ma3-agent-policy.mdc` | Skill bundle (must be copied to the runtime) |
| `~/.ma3/mcp-tools.json` | tools/list cache |

On **every MCP call**, the agent passes:

- `client_version` ← state's `skill_bundle_version`
- `tool_schema_version` ← state's `tool_schema_version`

The server returns in `structuredContent.server`:

- `policy_refresh_required`
- `mcp_reload_required`
- `client_update_required` (either layer breaking → **write paths forbidden**)

### 4. Sync and self-updating tooling

```bash
bash ~/.ma3/bin/sync_ma3_client.sh sync   # or check (exit 2 = updates available)
```

`sync` flow:

1. `GET /client/manifest.json`
2. If the manifest's scripts/lib sha256 differs from local → download and overwrite `~/.ma3/bin`, `~/.ma3/lib` (**tooling self-update**)
3. Download changed policy / onboarding / mcp-tools to `MA3_CLIENT_INSTALL_DIR`
4. Write `ma3-client.json`; if `mcp_reload_required` → the agent reloads MCP in the IDE

The manifest also includes `sync_tooling_version` (server-side `settings.sync_tooling_version`), useful for signaling "the sync tooling itself has changed."

If tooling was updated mid-run, stderr prompts to **re-run sync** (the current process may still be executing the old script).

### 5. Relationship to ADR-003

- ADR-003 forbids **a CLI for the ma3 write path** (report/context etc.) and **install.sh**.
- ADR-009's sync scripts are **read-only HTTP pulls + local file writes**; they do not replace MCP and have no write access to the ma3 server.
- Minimal bootstrap can still use plain `curl` (env template + three scripts); sync is the recommended path.

## Consequences

### Positive

- Supports any agent runtime without the ma3 repo maintaining N sets of paths
- Dual versions (skill + tool schema) can upgrade independently; MCP reload is decoupled from policy refresh
- When the server ships new sync scripts → the manifest hash changes → the agent auto-updates on its next sync

### Negative

- The MCP `tools/list` cache still depends on an **IDE reload**; sync cannot substitute for Cursor refreshing the MCP connection
- The first onboarding has more steps than "just curl the policy"; the agent must understand the env and copy the policy itself
- `ma3_sync_core.py` shares source code with server tests; deployment must ensure the HTTP-served content matches the repo

### Related

- ADR-003 (MCP-only agent surface)
- `04-target-architecture-draft.md` §3, §10
- `code/client/agent-onboarding.md` (operational source of truth)
- `code/eval/scenarios/agent-client-sync/` (Docker multi-agent install/upgrade tests)
- `tests/integration/test_client_sync.py`
