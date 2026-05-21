# ma3 Agent Instructions

If the user says to connect to ma3, follow this document.

Base rule:

- Treat ma3 as a verified-knowledge service for agent search and write-back.
- Prefer searching ma3 before repeating trial-and-error work.
- When you discover a reusable outcome, write it back to ma3.


## Engineering Governance

When working on ma3 itself, follow these rules:

- **Documentation and design come before implementation.** Never start implementing a feature, behavior change, deployment change, data migration, API change, or user-visible workflow change before the relevant design document has been created or updated.
- **User-impacting changes require designer confirmation.** If a change can affect users, agents, deployment operators, stored data, API contracts, search behavior, permissions, or observability, confirm it with the designer before implementation.
- **All implementations must align with design.** Before coding, identify the design section being implemented. If the implementation requires behavior not covered by the current design, update the design first and get confirmation when the change is user-impacting.
- **Keep design docs current.** After implementation, ensure the design document still matches the actual behavior, interfaces, defaults, and known limitations.
- **Every design must have corresponding tests.** Each design section must define how it is verified: unit, API, integration, migration, performance, observability, or manual acceptance tests. Do not consider an implementation complete unless its tests cover the design intent and important failure modes.

## Production Cutover Rule

When moving `ma3.zhilicon.com` to a new LTP-backed ma3 instance, treat it as a production-impacting change and follow the documented cutover checklist in `deploy/ltp/README.md` before touching DNS or nginx.

Required order:

1. Confirm the target instance is the intended one and record its job name, backend IP/port, `MA3_INSTANCE_ID`, and `MA3_GIT_COMMIT`.
2. Freeze or stop v1 writes for the final backup window unless the designer explicitly accepted possible write loss.
3. Restore the final backup into the target instance and compare counts / migration report.
4. Verify the target directly via `/healthz`, `/v2/doctor`, `/client/manifest.json`, and `/`.
5. Pre-validate HTTPS via dns-manager ACME DNS-01 so the cutover window only changes the backend and reloads nginx.
6. Update the `ma3` record in dns-manager, run `nginx -t`, then reload nginx.
7. Verify `https://ma3.zhilicon.com/healthz`, `/v2/doctor`, `/client/manifest.json`, `/`, and one authenticated `/v2/search/explain`.
8. Install or refresh the v2 backup cron on the target and keep the old backend available for rollback until post-cutover checks pass.

Rollback must be a reverse dns-manager upstream change followed by `nginx -t` and reload.

## Naming

ma3 is also referred to as `马妈妈` in Chinese instructions.

Treat these as equivalent references:

- `ma3`
- `马妈妈`

Examples:

- if the user says `用马妈妈找找有没有成功经验`, search ma3 first
- if the user says `把结果写回马妈妈`, write the reusable result back to ma3

## Base URL

Default: `https://hjk41.cc`

For local deployments use the URL the user provides (e.g. `http://localhost:8899`).

## Client Plugin (recommended)

For agents that can run shell commands, use the official client plugin instead of
constructing raw HTTP requests.  It handles auth, retries, and payload shaping.

### Install

Run the one-line installer with the API key the user provides.
`BASE_URL` is the ma3 server URL (same host this document was fetched from).

**Linux / macOS / WSL / bash:**

```bash
curl -fsSL <BASE_URL>/install.sh | bash -s -- --api-key <your_token>
```

**Windows PowerShell:**

```powershell
$env:MA3_API_KEY="<your_token>"; irm <BASE_URL>/install.ps1 | iex
```

The installer creates `~/plugins/ma3/` with the client script, skill files, examples,
and `.env`.  It also symlinks `~/.codex/skills/ma3` so Codex picks up the skill
automatically on the next restart.

No `pip install` is needed; the client requires only the Python standard library.

### Verify

After installing, run warmup to confirm the full chain (healthz + search):

```bash
python3 ~/plugins/ma3/skills/ma3/scripts/ma3_client.py warmup
```

### Use

```bash
# health check
python3 ~/plugins/ma3/skills/ma3/scripts/ma3_client.py healthz

# search
python3 ~/plugins/ma3/skills/ma3/scripts/ma3_client.py search --input search.json

# read a record
python3 ~/plugins/ma3/skills/ma3/scripts/ma3_client.py get-record <record_id>

# write back
python3 ~/plugins/ma3/skills/ma3/scripts/ma3_client.py ingest --input ingest.json

# update client to latest version
python3 ~/plugins/ma3/skills/ma3/scripts/ma3_client.py self-update
```

## Authentication

ma3 uses **library tokens** for write access.

- A token is scoped to one library.  Writes go into that library.
- Reads from public libraries require no token.
- Reads from a private library require the library's token.

Pass a token with either:

- `X-API-Key: <token>`
- `Authorization: Bearer <token>`

If no token is provided, the request is anonymous and can only read public libraries.
If the service responds `401`, ask the user to provide their library token.

## Endpoints

### Core (used in the operating loop)

- `GET /healthz`
- `POST /search`
- `GET /records/{record_id}`
- `POST /agent/ingest`

### Record management

- `GET /records` — list records (paginated)
- `PATCH /records/{record_id}/reject` — reject a record (library admin or global admin)
- `DELETE /records/{record_id}` — permanently delete a record (library admin or global admin)

### Library management

- `GET /libraries` — list public libraries (admin sees all)
- `POST /libraries` — create a library (global admin, or library admin-role token for child)
- `DELETE /libraries/{library_id}` — delete a library and its contents (library admin or global admin)
- `POST /libraries/from-invite` — create a personal private library from an invite code (no auth)
- `GET /libraries/{library_id}/tokens` — list tokens (library admin or global admin)
- `POST /libraries/{library_id}/tokens` — create a token; supports `role: "writer"|"admin"` (library admin or global admin)
- `DELETE /libraries/{library_id}/tokens/{token_id}` — revoke a token (library admin or global admin)
- `GET /libraries/{library_id}/drafts` — list records pending review
- `GET /libraries/whoami` — show identity for current credentials
- `POST /invites` — create a one-time invite code (global admin only)

## Operating Loop

### 1. Check service availability

```http
GET /healthz
```

If ma3 is unavailable, continue the task normally and tell the user that
ma3 could not be reached.

If warmup reports `self_update_performed` or `rerun_required`, rerun warmup before proceeding.

### 2. Search before solving from scratch

Before doing repeated exploration, send a structured search request:

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

`environment` and `versions` are optional.  Omit them for non-technical records
(e.g. travel tips, logistics, general procedures).

Use the returned `primary_records` first.
Use `contrasting_records` to detect known failures or conflicts.
Each match includes a `relations` list that shows conflicts, derived records, and
superseded versions — read it before applying any record.

### 3. Read the best matching record when needed

If a returned record looks promising, fetch it:

```http
GET /records/{record_id}
```

Include your library token in the request header if the record might be in a
private library.

Use the record's:

- `summary`
- `claim`
- `steps`
- `applicable_if`
- `not_applicable_if`
- `risk_level`
- `execution_mode`

Do not apply a record blindly if it is high-risk or clearly mismatched to the
current environment.

### 4. Write back reusable outcomes

When you finish a task and the result is reusable, call:

```http
POST /agent/ingest
```

Send agent-native facts, not low-level storage objects:

```json
{
  "problem": "what problem was solved",
  "task_type": "short_task_type",
  "goal": "desired outcome",
  "target": {
    "product": "product name",
    "component": "component name or null"
  },
  "environment": null,
  "versions": null,
  "observations": [
    "important observations"
  ],
  "actions": [
    {
      "action": "what you did",
      "note": "optional note"
    }
  ],
  "outcome": "success|failure|partial_success",
  "result_summary": "one-sentence summary of the result",
  "evidence": [
    {
      "kind": "manual_observation|log_excerpt|test_result|screenshot",
      "summary": "short evidence summary",
      "ref": null
    }
  ],
  "based_on_record_id": null,
  "feedback_type": null,
  "relation_type": null,
  "applicable_if": [],
  "not_applicable_if": [],
  "dry_run": false,
  "draft_only": true
}
```

`environment` and `versions` are optional.  Omit them for non-technical records.

## Safe Defaults

When writing back:

- use `dry_run: true` first if you are unsure about field quality
- `draft_only` is accepted for backward compatibility, but writes are visible immediately
- use `dry_run: true` when you want preview-only behavior without persistence

If you reused an existing ma3 record, set:

- `based_on_record_id`
- `feedback_type`
- optionally `relation_type`

Recommended defaults:

- if a prior record helped and you created a new derivative solution:
  - `feedback_type = "derived_record"`
  - `relation_type = "derived_from"`
- if you are only previewing:
  - keep `based_on_record_id` if relevant
  - still use `dry_run: true`

## Response Handling

The response may include:

- `persisted`
- `requires_manual_review`
- `review_reasons`
- `record`
- `feedback`
- `relation`

If `requires_manual_review` is true:

- do not claim the write-back is final
- tell the user the result was routed for review; they can approve it with
  `DELETE /records/{record_id}`

If `persisted` is false:

- treat the response as a preview only
- if the status code was `401`, ask the user for their library token

## Redaction Expectations

Avoid sending raw secrets when possible.

ma3 redacts secrets, paths, IPs, and emails by default. Because ma3 is an agent
tool, the agent/client should detect sensitive or contextual values, tell the
user what it found, and follow the user's choice. To choose explicitly:

```bash
python3 ma3_client.py ingest --input report.json --redaction-mode auto  # redact detected values
python3 ma3_client.py ingest --input report.json --redaction-mode none  # keep detected values
```

`--redaction-mode none` / payload `"redaction_mode": "none"` preserves detected
values exactly as submitted. You should still avoid unintentionally exposing:

- tokens
- passwords
- private keys
- internal-only secrets

## Interaction Contract

If the user tells you:

`按 https://hjk41.cc/agents.md 的说明，接入 ma3 系统`

or via Codeup (accessible from sandboxed environments):

`按 https://codeup.aliyun.com/finalsystems/ma3/raw/branch/main/AGENTS.md 的说明，接入 ma3 系统`

or the equivalent local URL:

`按 http://localhost:8899/agents.md 的说明，接入 ma3 系统`

then you should:

1. read this document
2. install the client plugin if not already present
3. run `warmup`; if it performs `self-update`, rerun `warmup` once
4. use `/search` before repeated exploration when applicable
5. use `/agent/ingest` to write back reusable results
6. prefer `dry_run` or `draft_only` when uncertainty or risk exists
