# Glossary

> Chinese version: [glossary.zh.md](glossary.zh.md)

| Term | Meaning |
|------|------|
| **Agent** | AI client that calls ma3 over MCP (Cursor, Claude Code, etc.) |
| **Principal** | Identity subject, e.g. `user:{authing_sub}` |
| **Principal ID** | Permanent internal identifier; shown read-only on the settings page |
| **Display name** | User-visible nickname; set once at setup; globally unique (case-insensitive) |
| **Library** | Knowledge-base boundary; includes visibility, ACL, write_buffer_hours |
| **Personal library** | `kind=personal`; name `{display_name}'s personal library` |
| **Community Library** | `lib_default`; public |
| **Case** | Container for a problem thread |
| **Record** | One verifiable experience; status: active/buffered/draft/invalid/trashed |
| **Entitlement** | Layer 1: which libraries a principal is **allowed** to touch |
| **Key grant** | Layer 2: a given API key's reader/writer capability on a library |
| **Stats** | Library aggregate numbers (case/record counts); visible to normal users |
| **Enumerate** | **List** browse of records/cases; library admin / product admin only |
| **Mutate** | Change status, delete, grant, export |
| **Write buffer** | Window after write before publish; status=buffered; author-visible only |
| **Draft** | Maintainer review queue; mutually exclusive with buffer |
| **confirmation** | Pre-write audit metadata; **not a gate**; defaults to agent_judged |
| **Observatory** | Product-admin global read-only UI |
| **GTN** | Gate-Then-Nudge search ranking scheme |
| **Read unit** | Billed read usage; counted on successful `ma3_context` / `ma3_case` responses |
| **MCP** | Model Context Protocol; ma3 Agent's only data plane |

## Deprecated terms (do not use in docs)

| Deprecated | Replacement |
|------|------|
| Revoke / revoked (user UI) | **Delete** |
| Libraries (top bar) | **Libraries** (product copy may localize; English docs use Libraries) |
| My contributions / My votes (subnav) | Top bar **Records / Votes** |
| Overview Principal ID + copy | Settings read-only |
| ma3_search_explain | Internal / Observatory only |
