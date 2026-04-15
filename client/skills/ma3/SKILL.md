---
name: ma3
description: Connect agents to ma3 (马妈妈) — the institutional memory for this environment. Agents search before acting on any technical task, write back reusable outcomes, and manage knowledge libraries. Use when the user mentions ma3 or 马妈妈, or whenever prior experience might shortcut trial-and-error.
---

# ma3（马妈妈）

ma3 is institutional memory. Other agents before you have already debugged, deployed, configured, and migrated through problems you'll face today. Their findings live here. Search first — don't reason from scratch about problems that have already been solved.

Treat `ma3` and `马妈妈` as equivalent.

## Search First

When you start any technical task, search ma3 before taking action. Don't ask the user whether to search. Don't announce that you're about to search. Just search.

**Always search when the task involves:** debugging, configuration, deployment, installation, migration, infrastructure, or any domain where prior experience would help.

**Skip search only when:** the task is purely creative, conversational, or involves no external systems at all.

One search takes a few seconds. Finding a verified prior solution can save minutes or hours of trial-and-error.

## Write Back — Leave Notes for the Next Agent

After completing any task where you applied or tested a ma3 record, write an ingest immediately. Don't skip this step.

- Record proved correct → `outcome: "success"` with `based_on_record_id`
- Record failed or partially worked → `outcome: "failure"` or `"partial_success"` with observations
- New reusable finding (no prior record) → independent ingest without `based_on_record_id`
- Always use `feedback_type: "derived_record"`, `relation_type: "derived_from"`, `draft_only: true`

This is how you leave knowledge for the agent that comes after you.

## Client

```powershell
python C:\Users\chunt\plugins\ma3\skills\ma3\scripts\ma3_client.py <subcommand> ...
```

Read/write (uses `MA3_API_KEY` — library token):
- `healthz`
- `whoami`
- `list-libraries`
- `search`
- `get-record`
- `ingest [--library <library_id>]`

Admin (uses `MA3_ADMIN_KEY`):
- `create-library`
- `create-token <library_id> [--label <label>] [--role reader|writer|admin]`
- `list-tokens`
- `revoke-token`
- `promote`
- `reject`

Environment variables:
- `MA3_BASE_URL` — defaults to `https://hjk41.cc`
- `MA3_API_KEY` — library token for normal read/write
- `MA3_LIBRARY_ID` — which library this token belongs to (used in ingest output; optional)
- `MA3_ADMIN_KEY` — for library/token management and promote/reject
- `MA3_AUTH_MODE` — `x-api-key` (default) or `bearer`
- Legacy fallback: `YINGCHAN_BASE_URL`, `YINGCHAN_API_KEY`, `YINGCHAN_AUTH_MODE`

## Multi-library config (same server)

When you have tokens for multiple libraries on the same server, use `endpoints.json`
in the plugin root instead of env vars. Each entry is one (token, library) pair:

```json
[
  {
    "name": "personal",
    "base_url": "https://hjk41.cc",
    "api_key": "tok_personal_xxx",
    "library_id": "lib-abc123",
    "admin_key": "rc-admin-key"
  },
  {
    "name": "team",
    "base_url": "https://hjk41.cc",
    "api_key": "tok_team_yyy",
    "library_id": "lib-def456"
  }
]
```

- **search**: fans out to all endpoints — each token sees its own private library plus
  public libraries. Results are merged and deduplicated by `record_id`. This is correct.
- **ingest**: must target one library. Use `--library <library_id>` or `--endpoint <name>`:
  ```
  ingest --library lib-abc123 --input feedback.json
  ingest --endpoint personal  --input feedback.json   # equivalent
  ```
  Omitting both flags when multiple endpoints are configured will error with a clear message.

To find a library's ID: run `list-libraries` (shows `library_id` for each)
or check the ingest response's `_library_id` field.

Bundled format references:
- `examples/search-payload.example.json`
- `examples/ingest-payload.example.json`

## Operating Loop

### 0. Check service reachability

```powershell
python C:\Users\chunt\plugins\ma3\skills\ma3\scripts\ma3_client.py healthz
```

If unavailable: continue the task normally and inform the user. Do not block on this.

If the output contains `version_warning`: run `self-update` before proceeding.

```powershell
python C:\Users\chunt\plugins\ma3\skills\ma3\scripts\ma3_client.py self-update
```

### 1. Search — do this before anything else

Create `search.json` and call:

```powershell
python C:\Users\chunt\plugins\ma3\skills\ma3\scripts\ma3_client.py search --input search.json
```

Search payload:

```json
{
  "problem": "short statement of the problem",
  "query_intent": "find_verified_fix",
  "task_type": "short_task_type",
  "target": {
    "product": "product name",
    "component": "component name or null"
  },
  "goal": "what success looks like",
  "environment": {
    "os": "windows|linux|macos|other",
    "shell": "powershell|bash|zsh|cmd|other",
    "runtime": "python|node|go|...|null",
    "sandbox": "workspace-write|read-only|none|...|null",
    "workspace_boundary": "workspace-write|host-root|...|null",
    "network_profile": "restricted|enabled|production|...|null"
  },
  "versions": {
    "agent": "agent version or null",
    "target": "target tool version or null"
  },
  "observations": [],
  "constraints": [],
  "config_excerpt": null,
  "max_primary": 3,
  "max_contrasting": 2
}
```

`environment` and `versions` are optional — omit for non-technical records.

Use `primary_records` first. Use `contrasting_records` to detect known failures.

### 2. Read a promising record

```powershell
python C:\Users\chunt\plugins\ma3\skills\ma3\scripts\ma3_client.py get-record <record_id>
```

Focus on: `summary`, `claim`, `steps`, `applicable_if`, `not_applicable_if`, `risk_level`, `execution_mode`.

Do not apply a record blindly when it is high-risk or mismatched to the environment.

### 3. Do the task

Apply the approach. Observe what happens.

### 4. Write feedback back — mandatory

Create `feedback.json` and call:

```powershell
python C:\Users\chunt\plugins\ma3\skills\ma3\scripts\ma3_client.py ingest --input feedback.json
```

(`examples/ingest-payload.example.json` shows the full field reference — do not pass it directly.)

Feedback payload:

```json
{
  "problem": "what you were solving",
  "task_type": "same as original search",
  "goal": "desired outcome",
  "target": { "product": "...", "component": "..." },
  "observations": ["what you observed when applying the record"],
  "actions": [{"action": "what you did", "note": "optional"}],
  "outcome": "success|failure|partial_success",
  "result_summary": "one-sentence summary",
  "evidence": [{"kind": "manual_observation", "summary": "...", "ref": null}],
  "based_on_record_id": "<the record_id you applied>",
  "feedback_type": "derived_record",
  "relation_type": "derived_from",
  "draft_only": true
}
```

## Write-Back Rules

- `draft_only: true` by default.
- Use `dry_run: true` when field quality is uncertain.
- Set `based_on_record_id` whenever you applied an existing record.
- Avoid raw secrets in any field.
- If `requires_manual_review` is true: do not claim the write-back is final.
- If `persisted: false`: treat as preview only.
- If `401`: tell the user the deployment requires `MA3_API_KEY`.
- If `403`: this is a **token permission issue**, not a bug. Do not retry or debug the code. Run `whoami` to see the token's role. Reader tokens cannot write — the user needs to configure a writer or admin token as `MA3_API_KEY`. Tell the user directly.
