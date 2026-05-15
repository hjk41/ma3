# ma3 v2 Overall Design

## 1. Background

ma3 v1 has been running in production long enough to reveal three recurring problems:

1. **Agent usage is too chatty and slow.** A normal agent loop often runs separate client commands for `search`, `get-record`, and `ingest`. Each command starts a new CLI process and creates separate HTTP requests. On the server side, search also loads feedback and relations per candidate record, creating an N+1 query pattern.
2. **The system is not transparent enough.** Operators cannot easily see what is inside ma3, how search is behaving, how many records are useful, or which parts of the system are slow or unhealthy.
3. **Related experiences are not reliably connected.** v1 has record relations such as `derived_from`, `supersedes`, and `same_problem_family`, but there is no first-class object representing “the same task/problem over time”. In practice, related experiences can remain fragmented.

v2 is a breaking redesign. It keeps the product goal—verified institutional memory for agents—but changes the primary agent interface, observability surface, and knowledge model.

## 2. Goals

- Make the fast path for agents a single remote MCP tool call, not multiple standalone CLI calls or a per-host local daemon.
- Make search and storage behavior explainable and measurable.
- Introduce a first-class Case/Thread model so that multiple records about the same underlying issue are grouped and evolved together.
- Treat PostgreSQL as the production storage and search path.
- Provide explicit diagnostics for endpoint, network, TLS, authentication, authorization, and version compatibility problems.

## 3. Non-goals for v2 Initial Implementation

- No human-facing web UI in the first implementation phase.
- No full backward compatibility guarantee for v1 API shapes or CLI flows.
- No production-grade SQLite parity; SQLite remains a development backend only.
- No automated application of records to user systems. ma3 recommends and explains; agents remain responsible for action.

## 4. Architecture Overview

```text
Agent / Codex / Claude
        |
        | remote MCP / tool calls (primary)
        v
ma3 remote MCP server
  - hosted with the ma3 service
  - exposes typed agent tools
  - centralizes auth, endpoint config, versioning, and observability
  - keeps warm server-side process state and caches safe metadata
  - batches workflow calls and record/case reads
  - exposes doctor/whoami
        |
        | internal service calls / v2 HTTP API
        v
ma3 server
  - workflow API
  - search + explain
  - case assignment
  - metrics + stats
        |
        v
PostgreSQL
  - cases
  - records
  - relations
  - feedback
  - search indexes
  - request/search event summaries
```

The CLI remains as a wrapper for diagnostics, one-shot manual use, bootstrap, and environments that do not support remote MCP. It is no longer the primary high-frequency agent path.

The v2 design intentionally chooses a **remote MCP server** over a local MCP daemon. This centralizes upgrades, authentication policy, metrics, and tool schema evolution in the production ma3 deployment. Agents that support remote MCP can connect directly to the ma3 MCP endpoint without installing or keeping a local background process warm.

## 5. Core Concepts

### 5.1 Case / Thread

A **Case** represents one durable problem thread: the same task, bug, environment issue, operational incident, or recurring workflow. Cases provide the missing grouping layer above records.

A case stores:

- stable `case_id`
- title and summary
- target product/component
- normalized problem family
- tags
- state: `open`, `resolved`, `stale`, `archived`
- canonical record pointer, when known
- aggregate counters and timestamps

### 5.2 Record

A **Record** remains the atomic knowledge item: an experience, measurement, conclusion, failure, correction, or decision. In v2, each record should belong to zero or one primary case. Records may also be connected with relation edges.

### 5.3 Relation

A **Relation** remains the graph edge used for record-to-record and case-to-record evolution:

- `derived_from`
- `supersedes`
- `conflicts_with`
- `same_problem_family`
- `invalid_under`

Relations are used for explanation, search grouping, and case evolution, not just for display.

## 6. Agent Experience

The primary v2 agent path is:

1. Agent calls the remote ma3 MCP server with a task description and environment fingerprint.
2. ma3 returns:
   - best records
   - relevant cases
   - full enough details for immediate use
   - relation graph summary
   - why each item matched
   - warnings and known conflicts
3. Agent acts in its environment.
4. Agent writes back the result with optional `case_id` override.
5. Server assigns the new record to a case automatically when no explicit case is supplied.

This replaces the v1 pattern of separate `search`, `get-record`, and `ingest` client invocations.

The remote MCP layer is responsible for translating compact, schema-validated tool arguments into the v2 workflow APIs. Agents should not need to construct full ma3 JSON payloads or know which HTTP endpoints are involved.

## 7. Transparency and Observability

v2 exposes transparency in three layers:

1. **Machine metrics**: Prometheus-compatible `/metrics` for request counts, latency, error rates, search path, ingest counts, and case assignment outcomes.
2. **Stats APIs**: JSON endpoints for library totals, case totals, record status distribution, relation coverage, stale records, and search/index health.
3. **Explain APIs**: search responses can include score breakdown, candidate counts, filtered counts, full-scan flags, FTS/vector contribution, relation boosts/penalties, and case grouping decisions.

This allows maintainers to iterate search quality and knowledge hygiene without guessing.

## 8. Storage Direction

PostgreSQL is the production target. v2 should use explicit relational tables and indexes instead of relying primarily on JSON payload scans for production search paths.

SQLite may remain for local development and basic tests, but it does not need to match every production optimization.

## 9. Compatibility and Migration

v2 is allowed to break v1 interfaces, but migration should be explicit:

- Keep a read-only v1 import/backfill path for existing records.
- Generate initial cases from existing records and relations.
- Preserve original v1 record payloads where possible for auditability.
- Document the old-to-new API mapping.

## 10. Success Criteria

- A normal agent lookup and write-back flow can be completed through the remote MCP server without repeated standalone CLI calls or local JSON payload files.
- Operators can answer “what is in ma3?” and “why did search return this?” via APIs and metrics.
- Related experiences are grouped under cases and visible as evolution threads.
- Search avoids known N+1 relation/feedback loading patterns.
- Diagnostics clearly distinguish network, TLS, auth, permission, and version failures.

## 11. LTP One-shot Deployment

v2 supports starting a prod-like ma3 instance from a single LTP/OpenPAI job. The job acts as a bootstrapper rather than requiring a human to SSH into the container and upload files.

The intended flow is:

1. LTP job receives code ref, backup location, public URL, and secrets.
2. Container pulls ma3 code from Codeup/Git and checks out a pinned commit.
3. Container restores PostgreSQL from a manifest-backed backup on CephFS/3FS.
4. Container injects runtime identity through environment variables.
5. Container starts ma3 and writes an instance manifest back to shared storage.

Runtime identity is explicit:

- `MA3_PUBLIC_BASE_URL`: external URL used to render `/agents.md` dynamically.
- `MA3_INSTANCE_ID`: unique instance identifier for diagnostics and manifests.
- `MA3_GIT_COMMIT`: exact code commit served by the instance.

Secrets such as admin keys, database passwords, and Git credentials must come from LTP secrets and must not be written to logs or instance manifests.

Initial deployment uses full PostgreSQL dump restore only. Delta sync from production is intentionally deferred until there is a versioned, idempotent export/import protocol that covers records, feedback, relations, libraries, cases, deletes, and status updates.

## 12. Knowledge Observatory Web UI

v2 should include a web interface named **ma3 Knowledge Observatory**. Its purpose is not generic CRUD administration, but helping humans understand and improve the knowledge base.

The UI should answer:

- What knowledge exists in ma3 now?
- Which topics are growing or under-covered?
- How are cases, records, and relations connected?
- Which records are stale, conflicting, low-verification, or repeatedly unhelpful?
- Why did search return a specific result?
- What are the highest-value improvement actions?

Initial pages:

1. **Overview**: records, cases, status distribution, relation coverage, case coverage, search volume, zero-result rate, latency, high-risk/low-verification highlights.
2. **Topics**: distribution by product, component, tag, problem family, and case cluster; includes fast-growing topics and searched-but-under-covered topics.
3. **Cases**: browse and inspect Case/Thread timelines, canonical records, related records, conflicts, supersession, and known failure paths.
4. **Search Explain**: run a query through `/v2/search/explain`, inspect scoring and filters, and submit search feedback.
5. **Quality Actions**: prioritized curation tasks from `/v2/stats/quality-actions`.

Later pages can add graph exploration, review workflows, query replay, and ranking experiment comparison.

The UI should be backed by v2 APIs rather than direct database access so that the same transparency surfaces remain available to agents and scripts.
