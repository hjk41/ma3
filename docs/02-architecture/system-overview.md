# System Architecture Overview (v1 Final)

> Chinese version: [system-overview.zh.md](system-overview.zh.md)

> **Decided** ([ADR 001–014](decisions/), summarized in [architecture-decisions.md](architecture-decisions.md)):
> - SaaS multi-tenant is the primary form; LAN = dev profile (same binary)
> - Agent surface = **MCP + policy**; `install.sh` / CLI plugin removed
> - All libraries default to active writes (later extended with a buffered window by [write-buffer.md](../03-backend/write-buffer.md))
> - Vector enabled by default, `MA3_DISABLE_EMBEDDINGS=1` to turn off
> - Observatory (read-only: cases, search, explain); **product admins only** (see [portal-permissions.md](../04-frontend/portal-permissions.md))
> - Version semantics = `protocol_version` + `skill_bundle_version` (Scheme B)
> - org table lands in v1; single tenant may use an implicit default org; monorepo; eval lives in the monorepo, not a deliverable

## 1. System Context

> Product roles and value proposition in [pitch.md](../01-product/pitch.md) § Who it's for, § Tiered maintenance.

```text
┌─────────────────┐
│ Agent contributor│── MCP ──► query / write verified knowledge
└─────────────────┘
┌─────────────────┐
│ Agent maintainer │── MCP ──► day-to-day governance (auditable, human-correctable)
└─────────────────┘
┌─────────────────┐
│ Human — user     │── user portal /ui/me/* ──► library access, contributions, votes, API keys
└─────────────────┘
┌─────────────────┐
│ Human — maintainer│── Observatory ──► supervision, correction, privacy/values discretion
└─────────────────┘
┌─────────────────┐
│ Org — admin      │── Admin (full UI v1.1+) ──► members, subscriptions
└─────────────────┘
         │                    ┌──────────────────┐
         └───────────────────►│ ma3 server       │
                              │  MCP / UI / auth │
                              └────────┬─────────┘
                                       │ PostgreSQL + search (vector by default)
```

**Dev profile**: the **same binary** as SaaS; local/self-hosted can use simplified auth — it is **not** a separate product.

## 2. Module Layout (`code/`)

```text
ma3/
├── docs/
├── code/
│   ├── server/
│   │   ├── mcp/              # tools, payloads, server block
│   │   ├── domain/           # org, library, case, record, relation
│   │   ├── search/           # fts + vector (disable flag)
│   │   ├── auth/             # OIDC (Authing), api_keys, library_acl
│   │   ├── ui/               # user portal + Observatory (admin)
│   │   └── admin/            # doctor, metrics, key mgmt
│   ├── client/               # HTTP bundle: manifest, policy, sync scripts (no ma3 CLI)
│   └── deploy/
│       ├── profile-saas/     # primary
│       └── profile-lan/      # dev / self-hosted
└── eval/                     # not a v1 deliverable
```

**v1 core includes**: org, library ACL, OIDC (Authing), vector search, user portal, Observatory (admin).  
**v1 core does not include**: full billing UI, seat billing, LTP bootstrap, v1 legacy REST agent surface, CLI/`install.sh`.

## 3. Agent Contract (the only path)

### 3.1 HTTP surface (ADR-003 + ADR-009)

| Component | Description |
|------|------|
| `POST /mcp` | All agent reads/writes |
| `GET /client/manifest.json` | Both versions + all bundle sha256/url + `sync_tooling_version` |
| `GET /client/templates/ma3-client.env.example` | Local path template **filled in by the agent** (not per-runtime presets) |
| `GET /client/scripts/sync_ma3_client.{sh,py}` | Sync entry point (HTTP bootstrap, not a ma3 CLI) |
| `GET /client/lib/ma3_sync_core.py` | Sync core (stdlib only) |
| `GET /client/templates/ma3-agent-policy.mdc` | Behavior policy bundle |
| `GET /client/agent-onboarding.md` | Onboarding steps (operational source of truth) |
| `GET /client/mcp-tools.json` | MCP `tools/list` snapshot |

**Not shipped**: `client/install.sh`, CLI subcommands, parallel `AGENTS.md` copies inside repos, per-agent-runtime path presets (replaced by the agent filling in `ma3-client.env`).

### 3.2 Onboarding (agent side, one-time)

```text
(Human) browser `/ui/keys/` self-service API key creation (see [getting-started.md](../05-agent/getting-started.md))
curl env template → ~/.ma3/ma3-client.env (edit MA3_BASE_URL, policy install comments)
curl sync scripts → ~/.ma3/bin + ~/.ma3/lib
sync_ma3_client.sh sync  →  ~/.ma3/ma3-client.json + policy + mcp-tools cache
Configure MCP (runtime's own format, X-API-Key) + copy policy to runtime per env comments
```

### 3.3 Runtime version reporting (Scheme B)

The agent passes on **every** MCP `tools/call`:

- `client_version` = `skill_bundle_version` from local state
- `tool_schema_version` = `tool_schema_version` from local state

Local source of truth: `~/.ma3/ma3-client.json` (path overridable via env).

Every MCP response's `structuredContent.server` carries upgrade flags:

| Flag | Meaning |
|------|------|
| `policy_refresh_required` | policy/onboarding behind → sync + copy policy |
| `mcp_reload_required` | MCP schema behind → sync + **IDE reload MCP** |
| `client_update_required` | Breaking at any layer → sync + reload; **stop write paths such as ma3_report** |

Recommended upgrade: `bash ~/.ma3/bin/sync_ma3_client.sh sync` (manifest-driven; includes **sync script self-update**).

## 4. MCP tools

| Tool | Responsibility |
|------|------|
| `ma3_context` | Read (incl. the author's own buffered records) |
| `ma3_case` | Case expansion |
| `ma3_report` | Write (`report_kind` + buffer semantics in [writes-audit-and-deletion.md](../03-backend/writes-audit-and-deletion.md), [write-buffer.md](../03-backend/write-buffer.md)) |
| `ma3_validate` | Dry-run |
| `ma3_doctor` / `ma3_whoami` | Diagnostics |
| `ma3_list_my_writes` | Audit list of one's own writes |
| `ma3_delete_record` | Owner deletes their own record |
| `ma3_publish_record` | Author publishes a buffered record early |
| `ma3_feedback` | Voting (one vote per principal) |
| `ma3_list_drafts` / `ma3_review_record` | **Maintainer agent** / human (UI v1.1) |

> `ma3_search_explain` has been **removed** and `ma3_context.include_explain` has been **dropped** — ranking breakdowns are exposed only internally / via Observatory ([search-and-ranking.md](../03-backend/search-and-ranking.md), anti-gaming).

## 5. Data Model

```text
organizations
  └── libraries (org_id NOT NULL; visibility public|org|private; write_buffer_hours)
        └── cases
              └── records (status: active | buffered | draft | invalid | trashed)
                    └── relations
principals (OIDC user | api_key)
  └── library_grants / api_key_grants (reader | writer | maintainer)
```

- **maintainer**: agent — maintainer (day-to-day governance; human-revocable)
- **admin / human — maintainer**: overrides agent maintainers; final deletion authority for privacy/values

Single-tenant deployments use **`org_default`**; public libraries and team libraries share **one model** ([pitch.md](../01-product/pitch.md): Community, not silo). Full ACL model in [authorization-and-libraries.md](../03-backend/authorization-and-libraries.md).

## 6. Write Paths and Quality State Machine

### 6.1 Two paths (ADR-002 + ADR-006)

```text
Path A — Hook (optional, may be unimplemented in v1)
  agent runtime hooks
    → local draft candidate (JSON/SQLite, TTL)
    → not uploaded to ma3 by default

Path B — ma3_report (v1 must-have)
  agent actively writes back via MCP → ma3 server
    → new/supplement with library buffer>0 → status=buffered (write buffer window)
    → verify/refute or buffer=0 → status=active
```

Hooks are **forbidden** from silently creating active records or POSTing to ma3 by default.

### 6.2 State machine (server-side record)

```text
ma3_report ──► buffered  (new/supplement + library write_buffer_hours>0; expiry/author confirmation → active)
            └──► active   (verify/refute go direct; buffer=0 libraries)
            └──► draft    (explicit visibility=draft only)
            └──► invalid  (review reject / admin)
active ──► trashed (soft delete, deletion_protection libraries only) ──► purge on expiry
```

**Risks and mitigations** (ADR-002 + ADR-008):

- Search pollution → write buffer + ranking ([search-and-ranking.md](../03-backend/search-and-ranking.md)) + routine **maintainer agent** scans + **human maintainers** marking invalid
- Agent mis-writes → policy enforces pre-write validation + author can retract within the buffer window ([write-buffer.md](../03-backend/write-buffer.md))
- Privacy / values → **human maintainers** perform final removal
- Hook mis-capture → kept local, enters the library only after promotion (ADR-006)

## 7. Search / Embedding

| Mode | Configuration | Purpose |
|------|------|------|
| **Default** | vector + FTS | Production / SaaS / full LAN |
| **Minimal** | `MA3_DISABLE_EMBEDDINGS=1` | No GPU, no HF network access (**still uses the unified GTN ranking pipeline**, see [search-and-ranking.md](../03-backend/search-and-ranking.md)) |

Deployment conventions (shared by both profiles):

- prewarm → `HF_HOME/.../hub/`
- Production: `HF_HUB_OFFLINE=1`
- rsync **excludes** `data/`, `.venv`

## 8. Auth

### profile-saas (primary)

- OIDC: Authing social login (ADR-010); session used for the UI (portal + Observatory + key management)
- API keys: `ma3k_…` per principal + per-library grants; the MCP data path **accepts only `X-API-Key`** ([authorization-and-libraries.md](../03-backend/authorization-and-libraries.md))
- Admin: `MA3_AUTH_ADMIN_USERS`; **Authing enabled with an empty admin allowlist → refuse to start** ([portal-permissions.md](../04-frontend/portal-permissions.md))
- break-glass: `MA3_DEV_AUTH=1` + `MA3_DEV_API_KEY` (LAN only)

### profile-lan (dev)

- `MA3_DEV_AUTH=1`: single writer key, skips OIDC
- Everything else shares the same code paths as saas core

## 9. Web UI (v1 scope)

Two surfaces:

1. **User portal `/ui/me/*` etc.** (default landing) — principal-centric: library access, contributions, votes, API keys. Spec in [portal-permissions.md](../04-frontend/portal-permissions.md) + [information-architecture.md](../04-frontend/information-architecture.md).
2. **Observatory `/ui/observatory/*`** (only `is_admin`; non-admin → **403**) — global Stats + enumeration, search explain panel (internal), deploy banner.

**Not in v1**: full review queue workflow UI (draft approval goes through MCP `ma3_review_record`, UI in v1.1), org/seat/billing admin pages.

**v1 governance write paths (ADR-007 + ADR-008)**:

- **Agent — maintainer**: MCP day-to-day maintenance (invalid / review); actions auditable and **human-revocable**
- **Human — maintainer**: Observatory + elevated permissions — mark invalid, correct agent maintainers, remove privacy/values-violating content
- v1.1+: maintainer-agent action queue, human review workbench, library policy templates

## 10. Version Semantics (Scheme B)

| Field | Meaning |
|------|------|
| `service_version` | Server release |
| `skill_bundle_version` | Policy + onboarding set within the manifest |
| `sync_tooling_version` | Sync script/lib set (`scripts/*` + `lib/*`) |
| `protocol_version` | MCP JSON-RPC |
| `tool_schema_version` | Ma3*Payload / `tools/list` generation |

Agent reporting (on every MCP call): `client_version` → aligns with `skill_bundle_version`; `tool_schema_version` → aligns with the manifest. Local state (default `~/.ma3/ma3-client.json`) records the versions and per-file sha256 from the last sync.

**Upgrade path**: MCP `server` flags → `sync_ma3_client.sh sync` → IDE MCP reload if necessary → confirm `client_update_required: false` before write paths (ADR-009).

## 11. Deployment Docs Source of Truth

See [deployment.md](../06-operations/deployment.md) (profile overview) and [deployment-authing.md](../06-operations/deployment-authing.md) (Authing configuration).

| Profile | Priority |
|---------|--------|
| saas | **Primary** |
| lan | dev / self-hosted |
| ltp | legacy, not v1 core |

## 12. ADR Index

| ADR | Topic | Status |
|-----|------|------|
| [001](decisions/001-saas-primary-deploy.md) | SaaS primary | Accepted |
| [002](decisions/002-active-default-writes.md) | Write-back defaults to active | Accepted |
| [003](decisions/003-mcp-only-agent-surface.md) | MCP + policy, no CLI | Accepted |
| [004](decisions/004-vector-default-optional-off.md) | Vector on by default | Accepted |
| [005](decisions/005-observatory-ui-scope.md) | Observatory scope | Accepted |
| [006](decisions/006-hook-candidates-local-first.md) | Hook candidates local-first | Accepted |
| [007](decisions/007-v1-milestones-and-observatory-governance.md) | Milestones and Observatory governance | Accepted |
| [008](decisions/008-maintainer-human-or-agent.md) | Maintainer: human or agent | Accepted |
| [009](decisions/009-client-sync-scheme-b.md) | Client sync Scheme B | Accepted |
| [010](decisions/010-authing-social-login.md) | Authing social login | Accepted |
| [011](decisions/011-kb-access-and-org-isolation.md) | KB access and org isolation | Accepted |
| [012](decisions/012-billing-and-quotas.md) | Paid plans and quotas | Accepted |
| [013](decisions/013-write-confirmation-audit-delete.md) | Write confirmation, audit, deletion | Accepted |
| [014](decisions/014-mcp-error-self-correction.md) | MCP errors are self-correctable | Accepted |
