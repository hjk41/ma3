# ADR-006 — Hook candidates default to local storage, not uploaded to ma3 until explicitly promoted

> Chinese version: [006-hook-candidates-local-first.zh.md](006-hook-candidates-local-first.zh.md)

## Status

Accepted (2026-07-01)

## Context

Hooks automatically capture session, prompt, tool-use, and other context throughout the agent lifecycle (see the old repo's `docs/agentmemory-mechanism-lessons.md`). If this were treated as the same path as `ma3_report`'s active-by-default behavior, verified knowledge would get polluted by raw traces.

The product owner confirmed: hook candidates **must not** be auto-activated; and further clarified that they should be **stored locally by default**, rather than on the ma3 server.

## Decision

### 1. Storage location

| Layer | Default location | Content |
|------|----------|------|
| **Hook candidates** | **Local** (agent machine) | Session snapshots, truncated tool traces, draft report templates, fingerprint dedup state |
| **Verified records** | **ma3 server** | Cases/records promoted via `ma3_report` or human review |

Hooks **do not write** any searchable data to ma3 by default.

### 2. The only path to ma3

Local candidate → explicit action → server:

1. The agent calls **`ma3_report`** (defaults to `active`, see ADR-002)
2. A **maintainer** (human/agent) **promotes** a local or server-side draft via Observatory / the review process
3. Optionally: the payload explicitly sets `visibility=draft` to submit to ma3's draft queue (**not** hook-auto-triggered)

Without one of the above steps → **does not enter the ma3 index**.

### 3. Hook implementation boundary (may not ship in v1, but the boundary is set now)

- Hook scripts attach to the hook directory of the **agent runtime** (Cursor/Codex, etc.), and **do not** depend on the ma3 CLI / `install.sh` (ADR-003)
- Local storage: lightweight JSON or SQLite, with **TTL / session-level cleanup**
- Hook-side requirements: **truncation** (e.g., tool output capped at 8k), **redaction**, **deduplication**, **timeout + try/catch**; failures must not block the agent
- **Forbidden**: auto-POSTing to ma3 on every `post-tool-use`; hooks silently creating `active` records

### 4. Relationship to ADR-002 / ADR-003

```text
Hook (local draft candidate)
        │
        │  agent curates + ma3_validate + ma3_report
        ▼
ma3 server (active by default)

Hook ──✗──► ma3 active   (forbidden)
Hook ──✗──► ma3 default upload  (forbidden)
```

## Consequences

### Positive

- Sensitive raw traces default to staying on the local machine
- High-frequency hooks don't hammer ma3's network or index
- Consistent with P1 (verified over raw), Q2=A
- Hooks can still be integrated on the agent IDE side after removing the CLI

### Negative

- Local candidates are not shared across machines when collaborating (requires writing back via `ma3_report` before **other agents** can see it within the library)
- Doing "cross-session local retrieval" would require a self-managed local index (not part of ma3 v1 core)

### v1 scope

- **The ADR constraint takes effect immediately** (design boundary)
- **Hook implementation is an optional module** and does not block v1 core (MCP + Observatory + SaaS auth)
- If implemented, it lands at `code/client/hooks/` (example scripts + local store spec), **not** a required server component

## Related

- ADR-002 (`ma3_report` defaults to active)
- ADR-003 (MCP + policy, no CLI)
- Q2=A (verified over raw)
- Old repo `docs/agentmemory-mechanism-lessons.md` §1
