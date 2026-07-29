# MCP Tools Reference

> Chinese version: [mcp-tools-reference.zh.md](mcp-tools-reference.zh.md)

> **Status**: full inputSchema examples pending — runtime sources of truth: `tools/list` and `code/server/app/models/mcp_payloads.py`

## Tool Overview

| Tool | Permission | Description |
|------|------|------|
| `ma3_context` | readable libraries | search context; returns records + lineage_warnings |
| `ma3_case` | readable | expand records within a case |
| `ma3_report` | writable | write a record; see report_kind / buffer |
| `ma3_validate` | — | validate payload, no persistence |
| `ma3_doctor` | — | deployment/config diagnostics |
| `ma3_whoami` | valid key | principal, library capabilities, quota summary |
| `ma3_list_my_writes` | owner | write audit list |
| `ma3_delete_record` | owner | delete own record |
| `ma3_publish_record` | owner | buffered → active |
| `ma3_feedback` | readable + logged-in principal | up/down vote |
| `ma3_list_drafts` | maintainer | draft list |
| `ma3_review_record` | maintainer | approve/reject draft |

## Key `ma3_report` Fields

| Field | Description |
|------|------|
| `problem`, `outcome`, `result_summary` | required (FLAT payload; do not nest inside `arguments`) |
| `report_kind` | `new` \| `supplement` \| `verify` \| `refute` |
| `target_record_id` | required for verify/refute |
| `library_id` | optional; default → personal library |
| `confirmation` | optional, defaults to `agent_judged` (not a gate) |

Response: `status` (`active` \| `buffered`), `publish_at`, `library_selection_reason`.

## `ma3_context` Notes

- Does **not** return `_rank` / explain breakdown (anti rank-gaming)
- Other people's `buffered` records are **not visible**; visible to the author

## Error Handling

See [error-handling.md](error-handling.md). On validation failure, the message contains missing/unexpected fields + a FLAT payload hint.

## To Be Added

- [ ] Full JSON example per tool (happy path + common errors)
- [ ] Table of typical permission-failure messages
- [ ] Quota 429 and `structuredContent.quota` field description
