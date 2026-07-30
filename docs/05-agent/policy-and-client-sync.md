# Agent Policy and Client Sync

> Chinese version: [policy-and-client-sync.zh.md](policy-and-client-sync.zh.md)

> Operational steps source of truth: `code/client/agent-onboarding.md` (curl-able over HTTP)  
> Policy source of truth: `code/client/templates/ma3-agent-policy.mdc`

## Bootstrap Flow

```text
1. Human: create API key at /ui/keys/
2. curl ma3-client.env.example → ~/.ma3/ma3-client.env (edit MA3_BASE_URL)
3. curl sync scripts → ~/.ma3/bin + ~/.ma3/lib
4. sync_ma3_client.sh sync → ~/.ma3/ma3-client.json + policy + skill + mcp-tools cache
5. Configure IDE MCP (X-API-Key) + copy policy and skill to runtime
```

## Scheme B Version Fields

| Field | Meaning |
|------|------|
| `service_version` | server release |
| `skill_bundle_version` | policy + onboarding + Agent Skill bundle (default **1.6.0** = C1) |
| `sync_tooling_version` | sync scripts/lib |
| `tool_schema_version` | MCP payload generation |

The Agent reports on every MCP call: `client_version` (aligned with skill_bundle) and `tool_schema_version`.

Local source of truth: `~/.ma3/ma3-client.json`.

## MCP Response Upgrade Flags

| Flag | Agent action |
|------|------------|
| `policy_refresh_required` | sync + copy policy **and** skill to runtime |
| `mcp_reload_required` | sync + IDE reload MCP |
| `client_update_required` | sync + reload; **stop write paths** |

## Policy Highlights (Agent behavior)

- **FIRST-ACTION GATE (1.6.0)**: before mutating work, call `ma3_context` first
- Agent Skill `skills/ma3/SKILL.md` ships in the client bundle (recall → work → remember)
- After reusable conclusions: `ma3_report` (`confirmation` may be omitted)
- Writing to the community library: explicit `library_id: "lib_default"`
- On `status=buffered`: tell the user about the buffer period and early publish via the portal
- Rank-based downvote: only downvote hits judged wrong that rank **above** the record finally used
- On validation failure: read `error.message` to self-correct; `ma3_validate` for dry runs

## HTTP Bundle

| Path | Content |
|------|------|
| `GET /client/manifest.json` | versions + sha256 + urls |
| `GET /client/templates/ma3-agent-policy.mdc` | policy (1.6.0 GATE) |
| `GET /client/skills/ma3/SKILL.md` | Agent Skill |
| `GET /client/mcp-tools.json` | tools snapshot |
| `GET /client/scripts/sync_ma3_client.{sh,py}` | sync entrypoints |

## To Be Added

- [x] Default client bundle = C1 (GATE policy + skill)
- [ ] MCP configuration examples per Agent IDE (Cursor / Claude / Codex)
- [ ] Bundle mirroring approach for offline / air-gapped deployments
