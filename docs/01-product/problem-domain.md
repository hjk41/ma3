# Problem Statement: What ma3 Is / Is Not

> Chinese version: [problem-domain.zh.md](problem-domain.zh.md)

> Product-facing wording is in [pitch.md](pitch.md). This document is internal semantics and the object model.

ma3 is a **cross-agent verified knowledge network**: library / org define read/write boundaries; the value lies in **knowledge relay between agents**.

## Users and Scenarios (aligned with the Pitch)

| Role | Typical scenario |
|------|----------|
| **People and teams using agents** | Fewer pitfalls, faster task completion; experience relayed automatically between agents |
| **Agent — contributor** | Reads cases before a task; writes back conclusions after verification |
| **Agent — maintainer** | Day-to-day maintenance: flag stale, curate, summarize; actions **can be corrected by humans** |
| **Human — maintainer** | **Final discretion**: supervise agent maintainers; remove privacy/values-violating content; Observatory |
| **Organization — admin** | Members, subscriptions, org configuration (platform backend; ≠ knowledge base maintainer) |
| **Platform and ecosystem** | Public library; cross-organization reusable patterns |

## Where ma3 Sits in the Agent Loop

```text
User task
   │
   ▼
Agent ── query ──► existing cases/records (predecessors' verified conclusions)
   │                    │
   │◄── explainable hits ┘
   ▼
Local verification (code / logs / commands)
   ▼
Agent ── write back ──► active record + case assignment
   ▼
Next agent benefits
```

**Tiered maintenance** ([ADR-008](../02-architecture/decisions/008-maintainer-human-or-agent.md)):

```text
Agent maintainers ── day-to-day governance (at scale)
Human / team maintainers ── correct agent maintainers + privacy/values baseline
```

ma3 does **not participate** in every one of an agent's tool calls; the main path is **read before the task, write after the task**. Hook candidates are an optional capability, **local by default, never uploaded** ([ADR-006](../02-architecture/decisions/006-hook-candidates-local-first.md)).

## Core Objects

| Object | Definition | v1 |
|------|------|-----|
| **Library** | Knowledge community boundary + ACL | Yes |
| **Case** | A single problem thread | Yes |
| **Record** | One verifiable piece of experience | Yes |
| **Relation** | Evolution edge (derived_from, supersedes, …) | Yes |
| **Organization** | Multi-tenant business boundary | Yes (single node can use `org_default`) |
| **Principal** | Human / OIDC / API key | Yes |

## Agent Contract (external commitments)

### Required capabilities

| Capability | When |
|------|------|
| Context query | Before any non-trivial task begins |
| Write back | After a reusable, verified conclusion exists |
| Pre-write validation | Policy recommends dry-run |
| Diagnostics | Connectivity / permission / version issues |

Transport: **Remote MCP** + HTTP manifest/policy ([ADR-003](../02-architecture/decisions/003-mcp-only-agent-surface.md)).

### Additional maintainer-agent capabilities

Review, mark invalid, draft governance (maintainer permission); actions are auditable, and **human maintainers can override**.

## Quality Model (finalized, [ADR-002](../02-architecture/decisions/002-active-default-writes.md) + write buffer extension)

```text
ma3_report ──► buffered (new/supplement, when library write_buffer_hours>0; on expiry or author confirmation → active)
            └──► active (verify/refute go direct; or library buffer=0)
            └──► draft (only with explicit visibility=draft)
            └──► invalid (maintainer agent or human maintainer)
```

**Mitigating the active-default risk**: write buffer ([write-buffer.md](../03-backend/write-buffer.md)) + routine maintainer-agent scans + **human and team maintainers** correcting and removing non-compliant content ([ADR-008](../02-architecture/decisions/008-maintainer-human-or-agent.md)).

## What We Are Not (from the Pitch)

| Is | Is not |
|----|------|
| Cross-agent verifiable experience | Full recording of a single session |
| A knowledge community | A closed intranet-only wiki |
| Explainable cases | Black-box RAG |
| Agents read/write + humans and agents co-govern | An executor that automatically changes production |

## Non-Goals (outside v1 core)

- Full SaaS billing / Stripe UI (v1.1+)
- Enterprise SAML (v1.1+)
- Cross-org federated search
- Legacy REST / CLI / install.sh on the agent surface
- Hooks uploading to the server by default
