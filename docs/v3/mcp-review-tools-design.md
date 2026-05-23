# ma3 MCP draft review tools design

Date: 2026-05-23
Status: proposed + implementation target

## Background

ma3 already exposes two different control planes for knowledge lifecycle work:

- Remote MCP for agent-oriented search and write-back (`ma3_context`, `ma3_report`, `ma3_case`, `ma3_validate`, `ma3_doctor`, `ma3_whoami`)
- REST routes for record review (`GET /libraries/{library_id}/drafts`, `PATCH /records/{record_id}/promote`, `PATCH /records/{record_id}/reject`, `DELETE /records/{record_id}`)

This split means an agent can submit knowledge through MCP, but cannot complete the human review loop through the same protocol. Operators and clients must mix MCP and REST.

## Goals

1. Close the agent-facing review loop inside MCP.
2. Keep the first version minimal and conservative.
3. Preserve the existing permission model from the REST API.
4. Keep MCP schema publication and runtime validation aligned through strict Pydantic payload models.
5. Return review-specific structured results that are easy for agents to reason about.

## Non-goals

- Do not expose bulk review in v1.
- Do not expose permanent delete in v1.
- Do not redesign the underlying record storage schema.
- Do not remove or deprecate the existing REST review routes.

## Proposed MCP tools

### 1. `ma3_list_drafts`

List pending-review records from one library.

#### Why one library at a time

The REST route is already library-scoped, and MCP callers with multi-library access should make the target explicit. This avoids ambiguous "review inbox" semantics and keeps authorization straightforward.

#### Input

```json
{
  "library_id": "lib_ca4043b1c70d",
  "limit": 20,
  "offset": 0,
  "include_full_json": false
}
```

#### Validation rules

- `library_id`: required, non-empty string
- `limit`: integer, `1..100`, default `20`
- `offset`: integer, `>= 0`, default `0`
- `include_full_json`: bool, default `false`

#### Authorization

Match current REST behavior:

- caller must have at least `writer` access to the target library
- library admin or global admin is also allowed

#### Structured result

Compact mode returns:

```json
{
  "library_id": "lib_ca4043b1c70d",
  "count": 2,
  "total_drafts": 2,
  "records": [
    {
      "record_id": "vk_xxx",
      "title": "...",
      "summary": "...",
      "risk_level": "high",
      "status": "draft",
      "updated_at": "2026-05-23T00:00:00+00:00"
    }
  ]
}
```

Full-json mode returns the same top-level fields, but `records` contain full record payloads.

### 2. `ma3_review_record`

Approve or reject a draft record.

#### Input

```json
{
  "record_id": "vk_xxx",
  "decision": "approve",
  "review_note": "Validated against source docs and safe to promote.",
  "include_full_json": false
}
```

#### Validation rules

- `record_id`: required, non-empty string
- `decision`: enum `approve | reject`
- `review_note`: required, non-empty string
- `include_full_json`: bool, default `false`

#### Authorization

More restrictive than listing drafts:

- caller must be library admin for the record's library, or
- caller must be global admin (`admin_bypass`)

#### State transition rules

v1 should only review drafts.

Allowed:
- `draft -> active` when `decision=approve`
- `draft -> invalid` when `decision=reject`

Rejected:
- `active -> ...`
- `invalid -> ...`
- missing record
- inaccessible record

This is intentionally stricter than the REST `reject` route, which currently also allows rejecting active records. MCP review is positioned as a draft-review workflow, not a general moderation override.

#### Structured result

Compact mode returns:

```json
{
  "record_id": "vk_xxx",
  "library_id": "lib_ca4043b1c70d",
  "decision": "approve",
  "old_status": "draft",
  "new_status": "active",
  "review_note": "Validated against source docs and safe to promote.",
  "reviewed_at": "2026-05-23T00:00:00+00:00",
  "reviewer": {
    "type": "admin",
    "principal_id": "admin"
  }
}
```

Full-json mode adds the updated `record` object.

## Why not expose delete in MCP v1

Permanent delete is materially more destructive than approve/reject. Review automation often wants a reversible "not approved" state, which `invalid` already provides. Keeping delete out of MCP reduces accidental irreversible actions and keeps the initial review surface smaller.

## Schema and validation contract

Both tools must follow the repo's MCP design rules:

1. Pydantic payload models live in `server/app/models/mcp_payloads.py`
2. `extra="forbid"`
3. each payload publishes at least one runnable example
4. `tool_input_schema()` remains the single schema source for `tools/list` and runtime validation
5. `ma3_validate.tool_name` enum must include the two new tools

## Error behavior

### `ma3_list_drafts`

- unauthenticated / wrong library role -> MCP permission error (`-32001`)
- missing library -> HTTP/MCP not found mapping
- payload issues -> `-32602` with structured `validation_errors`

### `ma3_review_record`

- record not found -> not found
- record outside caller admin scope -> permission denied
- non-draft record -> invalid params (`ValueError` -> `-32602`)
- payload issues -> `-32602` with structured `validation_errors`

## Auditing

The underlying `Record` model does not persist a reviewer principal field today. v1 therefore uses two existing audit channels:

- durable record fields: `review_note`, `reviewed_at`, status transition
- op log entry from `write_op_log("mcp_tool_call", ...)`, which already captures MCP caller identity

The MCP response should also include a `reviewer` summary so the caller can reason about the action immediately.

## Implementation plan

1. Add `Ma3ListDraftsPayload` and `Ma3ReviewRecordPayload`
2. Register them in `PAYLOAD_BY_TOOL`
3. Add tool descriptions and order entries in `mcp_tool_service`
4. Implement:
   - library-scoped draft listing with pagination in the MCP service layer
   - review action with explicit admin check and `draft`-only transitions
5. Update unit tests for schema alignment and validation enums
6. Add e2e MCP coverage for:
   - tools/list exposure
   - draft listing
   - approve flow
   - reject flow
   - writer cannot review
   - non-draft review rejected

## Future extensions

Possible v2 additions after observing real usage:

- optional `risk_level` or `updated_since` filters on `ma3_list_drafts`
- `ma3_review_batch` with explicit upper bound and partial-failure reporting
- persisted reviewer identity on the record model
- policy guard that prevents self-approval by the same principal that created the draft
