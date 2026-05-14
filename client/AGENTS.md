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

## Bootstrap Contract

If the user asks to install, connect, bootstrap, remove, or uninstall ma3, do the work yourself.
Do not stop at handing the user `install.ps1`, `install.sh`, `uninstall.ps1`, or `uninstall.sh`
unless command execution is unavailable.

Fresh install:

- Read this document first.
- Run the platform-appropriate install flow yourself.
- Ensure the install flow adds direct `python <ma3_client.py> ...` / `python3 <ma3_client.py> ...`
  allow-rules for Codex execpolicy and Claude permissions. Prefer these direct invocations over
  wrapping them in nested `powershell -Command` or `bash -lc` strings.
- Re-invoke the host CLI after install to confirm ma3 is discoverable.
- Run at least `healthz` and one real `search` or `warmup` before declaring success.

Uninstall:

- If Claude Code has `ma3@finalsystems` installed as a plugin, remove it.
- Run the platform-appropriate uninstall flow yourself.
- Ensure the Codex execpolicy rule file and Claude allow-rules are removed.
- Re-check discoverability before declaring ma3 fully removed.

## Client Plugin (recommended)

For agents that can run shell commands, use the official client plugin instead of
constructing raw HTTP requests.  It handles auth, retries, and payload shaping.

**Repository**: `https://github.com/hjk41/ma3`

### Install

Preferred bootstrap path:

Windows PowerShell:

```powershell
Invoke-WebRequest http://<server>/install.ps1 -OutFile install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1 -ApiKey <token> -BaseUrl http://<server>
```

Linux/macOS:

```bash
curl -fsSL http://<server>/install.sh -o install.sh
bash ./install.sh --api-key <token> --base-url http://<server>
```

If the host is Claude Code and plugin install is available, agents may also bootstrap with:

```powershell
claude plugins marketplace add /path/to/ma3/client
claude plugins install ma3@finalsystems
```

Then run the installed `install.ps1` / `install.sh` in the plugin directory so `.env`,
Codex skill links, and Claude permission rules are created automatically.

### Configure

Create a `.env` file in the cloned directory (see `.env.example`):

```
MA3_BASE_URL=https://hjk41.cc   # or your local URL
MA3_API_KEY=your_library_token  # for normal read/write
MA3_ADMIN_KEY=your_admin_key    # for library/token management (optional)
MA3_AUTH_MODE=x-api-key         # or: bearer
```

### Post-install verification

After running `install.sh` (or `install.ps1`), verify the installation before use:

**1. Confirm `ma3_client.py` is present**

```bash
ls ~/plugins/ma3/skills/ma3/scripts/ma3_client.py
```

Expected: file exists and is executable.

**2. Confirm `.env` has the required keys**

```bash
grep -E "MA3_BASE_URL|MA3_API_KEY" ~/plugins/ma3/.env
```

Expected: both keys are set and non-empty.

**3. Confirm skill symlinks exist (Claude Code and Codex only)**

```bash
ls -la ~/.claude/skills/ma3   # Claude Code
ls -la ~/.codex/skills/ma3    # Codex
```

Expected: both are symlinks pointing to `~/plugins/ma3/skills/ma3`.

If a symlink is missing, create it:

```bash
ln -sf ~/plugins/ma3/skills/ma3 ~/.claude/skills/ma3
ln -sf ~/plugins/ma3/skills/ma3 ~/.codex/skills/ma3
```

**4. Run a health check**

```bash
python ~/plugins/ma3/skills/ma3/scripts/ma3_client.py healthz
```

Expected: `{"status": "ok", ...}`.  A `version_warning` in the response means
you should run `self-update` before proceeding.

---

**For agents outside Claude Code and Codex:** the skill directory is never
auto-loaded for you.  You must locate `ma3_client.py` yourself and call it
directly.  Steps 1–2 and 4 above are the minimum verification.  If the default
path `~/plugins/ma3/skills/ma3/scripts/ma3_client.py` does not exist, search
for it with:

```bash
find ~ -name "ma3_client.py" 2>/dev/null | head -5
```

Record the resolved path and use it in all subsequent `python <path> <command>`
calls.  Do not rely on a skill being injected into your context.

---

### Use

```bash
# health check
python /path/to/ma3/skills/ma3/scripts/ma3_client.py healthz

# search
python /path/to/ma3/skills/ma3/scripts/ma3_client.py search --input search_payload.json

# read a record
python /path/to/ma3/skills/ma3/scripts/ma3_client.py get-record <record_id>

# write back
python /path/to/ma3/skills/ma3/scripts/ma3_client.py ingest --input ingest_payload.json

# update client to latest version
python /path/to/ma3/skills/ma3/scripts/ma3_client.py self-update
```

PowerShell wrapper equivalents are also available in `scripts/`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\healthz.ps1
powershell -ExecutionPolicy Bypass -File scripts\search.ps1 --input search_payload.json
powershell -ExecutionPolicy Bypass -File scripts\get-record.ps1 <record_id>
powershell -ExecutionPolicy Bypass -File scripts\ingest.ps1 --input ingest_payload.json
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
- `PATCH /records/{record_id}/promote` — approve a draft (library admin or global admin)
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

If the response contains `version_warning`, run `self-update` before proceeding.

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
- `draft_only` is accepted for backward compatibility, but new writes are visible immediately
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
  `PATCH /records/{record_id}/promote`

If `persisted` is false:

- treat the response as a preview only
- if the status code was `401`, ask the user for their library token

## Redaction Expectations

Avoid sending raw secrets when possible.

ma3 applies write-time redaction for common patterns (Windows and Unix paths,
emails, IPs, GitHub tokens, AWS keys, password assignments), but you should still
avoid exposing:

- tokens
- passwords
- private keys
- internal-only secrets

## Interaction Contract

If the user tells you:

`按 https://hjk41.cc/agents.md 的说明，接入 ma3 系统`

or via GitHub (accessible from sandboxed environments):

`按 https://raw.githubusercontent.com/hjk41/ma3/main/AGENTS.md 的说明，接入 ma3 系统`

or the equivalent local URL:

`按 http://localhost:8899/agents.md 的说明，接入 ma3 系统`

then you should:

1. read this document
2. install the client plugin yourself if not already present
3. check `/healthz`; run `self-update` if `version_warning` appears
4. use `/search` before repeated exploration when applicable
5. use `/agent/ingest` to write back reusable results
6. prefer `dry_run` or `draft_only` when uncertainty or risk exists

If the user says to uninstall ma3, you should:

1. remove the Claude plugin if present
2. run the platform uninstall flow yourself
3. verify that ma3 is no longer discoverable
