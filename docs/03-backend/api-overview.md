# HTTP / MCP API Overview

> Chinese version: [api-overview.zh.md](api-overview.zh.md)

## Principle: MCP owns knowledge, REST owns everything else

| Channel | Purpose | Auth |
|------|------|------|
| **MCP** `POST /mcp` | Knowledge loop: query, report, upvote/downvote, draft/publish/delete, whoami/doctor/validate | `X-API-Key` |
| **REST** `/api/*` | Post-deployment operations: registration/setup, accounts, API keys, orgs, members, libraries & authorization, Observatory management | `X-API-Key` (recommended) or portal session (browser; write operations require same-origin) |
| **Shell / Compose** | Installation, `./up.sh`, bootstrap file rotation | Host-level ops (**does not** expose HTTP) |
| **OIDC browser redirect** | SaaS / self-hosted IdP login | Interactive exception (an agent cannot substitute for browser OAuth) |

Self-host **bootstrap** API key: can use MCP knowledge tools; **cannot** call portal management REST endpoints (users, orgs, setup completion, etc.).

The full agent flow (once Compose is up) should be completable with **REST + MCP** alone, with no need to open a browser. See [self-hosting.md](../06-operations/self-hosting.md#agent-surface-mcp--rest).

## Routing surface

| Prefix | Auth | Consumer |
|------|------|--------|
| `POST /mcp` | `X-API-Key` | Agent (knowledge) |
| `GET /client/*` | Public | Agent bootstrap (manifest, policy, sync) |
| `/api/auth/*`, `/api/setup/*`, `/api/local-users` | Public or partially requires local admin key | Agent day-0 / local accounts |
| `/api/me`, `/api/keys`, `/api/orgs`, `/api/libraries`, `/api/principals` | User API key or session | Agent / browser |
| `/api/admin/*` | Product admin API key or session | Agent / Observatory |
| `/auth/*` | OIDC / local HTML | Browser |
| `/ui/*` | Session or anonymous | Browser SSR (same service as REST, not required) |
| `/healthz` | Public | Ops |

## MCP Tools (knowledge loop)

| Tool | Read/Write | Description |
|------|-------|------|
| `ma3_context` | Read | Context search |
| `ma3_case` | Read | Case expansion |
| `ma3_locate_by_id` | Read | Locate by ID |
| `ma3_report` | Write | Report a record |
| `ma3_feedback` | Write | Upvote / downvote / clear |
| `ma3_validate` | — | Dry-run |
| `ma3_doctor` | — | Diagnostics |
| `ma3_whoami` | — | Identity + library capabilities |
| `ma3_list_my_writes` | Read | Own writes |
| `ma3_list_drafts` / `ma3_review_record` | Read/Write | Maintainer |
| `ma3_publish_record` / `ma3_patch_record` / `ma3_delete_record` / `ma3_restore_record` | Write | Record lifecycle |

For full parameters see MCP `tools/list` and [../05-agent/mcp-tools-reference.md](../05-agent/mcp-tools-reference.md) (if it exists).

## REST (operations surface)

### Identity & day-0

| Method | Path | Description |
|------|------|------|
| GET | `/api/setup/status` | Setup status |
| PATCH | `/api/setup/registration` | Open/close registration (local admin) |
| POST | `/api/setup/registration/ack` | Acknowledge keeping it open |
| POST | `/api/setup/complete` | Complete onboarding |
| POST | `/api/auth/register` | Register (optionally mint an API key; optional `invite` for auto org join) |
| POST | `/api/auth/login` | Login and mint an API key |
| GET/PATCH | `/api/local-users` | List local accounts / promote-demote admin |
| GET/PATCH | `/api/me` | Current principal; set display name on first use |
| GET | `/api/principals?q=` | Search by display name (for adding members) |

### API keys

| Method | Path | Description |
|------|------|------|
| GET/POST | `/api/keys` | List / create (`X-API-Key` or session) |
| PATCH/DELETE | `/api/keys/{key_id}` | Change label/grants; delete (cannot delete the key used for the current call) |

See [../04-frontend/api-keys-ui-and-api.md](../04-frontend/api-keys-ui-and-api.md) for details.

### Organizations & libraries

| Method | Path | Description |
|------|------|------|
| GET/POST | `/api/orgs` | List / create team org |
| GET | `/api/orgs/creation-quota` | Org creation quota |
| GET | `/api/orgs/{id}` | Details + library list |
| GET | `/api/orgs/{id}/settings` | Read-only settings such as billing labels |
| GET/POST | `/api/orgs/{id}/members` | List members / add (optional `alias`) |
| PATCH/DELETE | `/api/orgs/{id}/members/{principal_id}` | Change role / alias / remove |
| POST | `/api/orgs/{id}/invites` | Create an invite; optional `member_alias`; returns `token` + `invite_url` |
| GET/DELETE | `/api/orgs/{id}/invites`… | List / revoke |
| GET | `/api/invites/preview?token=` | Preview invite (public, includes alias) |
| POST | `/api/invites/redeem` | Redeem invite into org with an existing account |
| POST | `/api/orgs/{id}/libraries` | Create an org library |
| GET | `/api/libraries` | Libraries visible to the current principal |
| GET | `/api/libraries/{id}` | Details + stats |
| GET | `/api/libraries/{id}/records` | Paginated records in a library (maintainer) |
| GET/POST/DELETE | `/api/libraries/{id}/grants`… | Library-level authorization |
| GET/PATCH | `/api/libraries/{id}/settings` | Write buffer period |
| GET | `/api/libraries/{id}/storage` | Usage |

### Admin (product admin)

| Method | Path | Description |
|------|------|------|
| GET | `/api/admin/observatory/stats` | System statistics |
| GET | `/api/admin/billing/overview` | Billing overview |
| GET | `/api/admin/users` | User list |
| PATCH | `/api/admin/users/{principal_id}/plan` | Set free/pro |
| GET | `/api/admin/orgs` | All organizations |

## Error format

MCP: JSON-RPC 2.0; **`error.message` must be self-correctable** — [error-handling.md](../05-agent/error-handling.md).

REST: standard FastAPI `{"detail": "..."}`; 403/404 do not leak information.

## Versioning

- `service_version`, `tool_schema_version`, `skill_bundle_version` — [policy-and-client-sync.md](../05-agent/policy-and-client-sync.md)
- MCP response `structuredContent.server` upgrade flags
