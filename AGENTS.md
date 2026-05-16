<coding_guidelines>
# AGENTS.md — ma3 Project Guide for Agents

This document is for Claude / Droid / Codex / any agent that lands in
`/root/code/ma3`. It captures **operating rules**, **MCP design contracts**,
and **deployment pitfalls** so the next agent does not re-derive them.

The ma3 server itself is the canonical knowledge store for cross-product
lessons; `ma3_context` against `target_product=ma3` will surface them.
This file captures the parts that are specific to *this repo* — code
conventions, MCP design rules, and the LTP cutover playbook.

## What ma3 is

ma3 ("马妈妈") is a verified knowledge network for agents. The server
under `server/` exposes a FastAPI app with:

- v1 records / libraries / search (legacy)
- v2 cases / graph / agent context (current)
- Remote MCP at `/mcp` (Streamable HTTP JSON-RPC)
- HTML UI at `/ui/*`
- Health + deploy identity at `/healthz`, `/v2/doctor`

Prod URL: `https://ma3.zhilicon.com`. Deployment lives under
`deploy/ltp/` and is fronted by `dns-manager` (same control plane as
inferhub v2).

## MCP design contracts (non-negotiable)

These rules exist because we burned a session debugging silent `-32602`
errors with no field info. Re-derived as of 2026-05-16, commit `25669ac`.

1. **Pydantic payload model is the SINGLE source of truth.** Every MCP
   tool has a `Ma3<Tool>Payload(BaseModel)` in
   [server/app/models/mcp_payloads.py](server/app/models/mcp_payloads.py).
   `tool_input_schema(name) -> model.model_json_schema(ref_template="#/$defs/{model}")`
   is consumed by **both** `list_mcp_tools()` (the wire schema) and
   `_validate_args()` (the runtime validator). Do not introduce a parallel
   hand-written `_schema({...})` dict; the test
   `tests/unit/test_mcp_schema_alignment.py` will fail if you do.

2. **`extra="forbid"` on every payload model.** Without it, a typo like
   `outome` instead of `outcome` silently falls through to defaults and
   the required-field error surfaces against the wrong field.

3. **`json_schema_extra={"examples": [...]}` is part of the contract.**
   Agents copy-paste from `inputSchema.examples[0]`. Every payload model
   must publish at least one example that round-trips through
   `model.model_validate(example)`.

4. **Structured `error.data` is mandatory for -32602.** Custom exception
   `McpToolValidationError(tool_name, errors)` in
   [server/app/models/mcp.py](server/app/models/mcp.py) carries the full
   `ValidationError.errors()` list. The route layer
   ([server/app/api/routes_mcp.py](server/app/api/routes_mcp.py)) emits
   `{tool_name, validation_errors: [{loc, msg, type, ctx?}, ...], schema_hint}`.
   The schema_hint **must** mention both `tools/list` and `ma3_validate`.

5. **`ma3_validate` is the dry-run channel.** Agents iterate against it
   before paying write quota. Never make it conditional on auth role; it
   has no side effects.

6. **Nested type definitions come from real models, not anonymous dicts.**
   `AgentAction`, `EvidenceItem`, `TargetRef` must appear in the published
   schema's `$defs` so clients can author payloads from the schema alone.
   Verified by `test_ma3_report_schema_documents_actions_and_evidence_shape`.

7. **`AgentAction` may grow optional fields, not required ones.** Adding
   required fields is a wire-breaking change for v0 clients. We added
   `rationale` / `ref` / `note` as optional + `extra="forbid"`; future
   fields follow the same rule.

## Health & doctor as deploy identity (not yes/no probes)

`/healthz` and `/v2/doctor` are NOT just "is it up" probes; they are the
**identity surface** for blue-green verification. Both expose:

- `instance_id` (one-per-job, set via `MA3_INSTANCE_ID`)
- `git_commit` (full hash, set via `MA3_GIT_COMMIT`)
- `job_name` (LTP/PAI job, prefer explicit `MA3_JOB_NAME`)
- `deployed_at` (ISO timestamp captured at process boot in `Settings.__post_init__`)

Cutover verification reduces to a one-liner:

```bash
curl -sS https://ma3.zhilicon.com/healthz \
  | jq '{commit:.git_commit, job:.job_name, deployed_at:.deployed_at}'
```

The `/ui/overview` HTML page renders the same identity in a server-side
banner (`<div class="deploy-banner">`) at the top of every page. This
survives JS failures and lets users / operators screenshot which backend
served them.

## LTP cutover playbook

Proven on 2026-05-16 (commit `75f6338` → `25669ac`). The full procedure
lives as a ma3 case (`ma3_context target_product=ma3 target_component=ltp-cutover`),
but the short checklist:

1. `git push origin v2` with the new commit.
2. **Fetch current prod job config** from
   `GET /api/v2/jobs/<owner>~<old-job-name>/config` and clone it.
3. **Edit cloned config**: `name`, `MA3_GIT_COMMIT`, `MA3_INSTANCE_ID`,
   `MA3_PORT` (use a port the **old** instance isn't using — LTP shared-VC
   shares host net namespace, so 18190 collides), inject `MA3_JOB_NAME=<new-name>`.
4. **Submit YAML**: `POST /api/v2/jobs` with
   `Content-Type: text/yaml`. JSON content type returns
   `InvalidProtocolError: must be object`.
5. **Secrets**: extract from running prod
   `/proc/<uvicorn-pid>/environ` in BINARY mode
   (`open(..., "rb").read().split(b"\x00")`). The naive
   `tr "\0" "\n"` truncates multi-line values like SSH keys, and the
   bootstrap silently fails with `Load key ...: error in libcrypto`.
6. Poll `state=RUNNING` (~1 min). Then SSH into candidate and poll
   `curl http://127.0.0.1:<MA3_PORT>/healthz` until `instance_id` matches
   the new name.
7. **Sanity-check the schema** before flipping traffic: `tools/list` must
   show `AgentAction` in `$defs` and `actions.items.$ref=#/$defs/AgentAction`.
   `ma3_validate` dry-run must return `{ok: true}` for a known-good
   payload.
8. **Final-backup-after-candidate-up** to minimize drift:
   - on prod container: `bash deploy/ltp/backup_postgres.sh`
   - on candidate: `kill $(cat /root/ma3-instance/ma3.pid)`
   - `bash deploy/ltp/restore_postgres.sh` with
     `MA3_BACKUP_MANIFEST=latest`
   - `python server/scripts/migrate_v1_to_v2_cases.py --apply` (idempotent)
   - restart uvicorn with **full env**:
     `set -a; . /root/ma3-instance/ma3.env; set +a; export MA3_JOB_NAME=...; nohup .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port $MA3_PORT ...`
     Forgetting `set -a; . ma3.env` makes `instance_id` and `git_commit`
     return `null` even though uvicorn is fine — it's not a regression,
     just unset env.
9. **Verify parity** vs prod: `/v2/doctor` shows
   `records == indexed` and matches the prod count.
10. **Record rollback target** to `/tmp/ma3-cutover-rollback.txt` BEFORE
    the dns-manager PATCH (old IP:port + old job name). Rollback is just
    paste-old-IP back through PATCH.
11. **dns-manager PATCH uses QUERY STRING, not JSON body**:
    ```bash
    curl -sS -X PATCH -H "Authorization: Bearer $LTP_TOKEN" \
      "https://dns.zhilicon.com/api/records/ma3?backend_ip=10.100.193.54&backend_port=18191"
    ```
    JSON body returns 200 + the **old** record (silent no-op). Always
    follow up with a `GET` to confirm `backend.port` actually changed.
12. **External HTTPS verification** must show the new commit:
    ```bash
    curl https://ma3.zhilicon.com/healthz | jq .git_commit
    curl https://ma3.zhilicon.com/ui/overview | grep deploy-banner
    ```
13. **Stop old job**: `PUT /api/v2/jobs/<owner>~<old>/executionType` with
    `{"value":"STOPPED"}`. Returns 202, but `state` polls keep returning
    `RUNNING` for ~30–60s. Trust the 202 and external probe; don't
    block on `state==STOPPED`.

## Test gates (run before any commit touching server/)

```bash
cd /root/code/ma3/server
python3 -m pytest -x -q
```

198 tests must pass. The MCP schema-alignment test (
`tests/unit/test_mcp_schema_alignment.py`) is the CI brick that catches
inputSchema-vs-Pydantic drift; never xfail it.

For LTP-specific changes (`deploy/ltp/`):

```bash
bash deploy/ltp/bootstrap_ma3_ltp.sh --help 2>/dev/null || true   # syntax sanity
shellcheck deploy/ltp/*.sh                                         # if shellcheck is installed
```

## Repo conventions

- **No Chinese-only comments in code paths**: keep code English. UI strings
  in Chinese are fine.
- **Pydantic models live under `app/models/`**, grouped by domain. Add new
  MCP tools' payload models to `app/models/mcp_payloads.py`, not next to
  the route handler.
- **Tests follow the route**: each new route file gets a matching
  `tests/e2e/test_*.py`; each new service gets a `tests/unit/test_*.py`.
- **`backfill_search_indexes` runs in a daemon thread at startup** so
  `/healthz` becomes available immediately. Don't put any DB-writing
  initialization in the request path.
- **`MA3_DATABASE_URL` is the source of truth** for which DB backend
  applies. `MA3_DB_PATH` is only consulted when database_url is unset
  (SQLite fallback for tests). Never read both in the same code path.

## Pitfalls speed-list

| Symptom | Root cause | Fix |
|---|---|---|
| `-32602 Invalid params` with no field info | route layer dropped `ValidationError.errors()` | catch `McpToolValidationError`, populate `error.data.validation_errors` |
| `tools/list` schema differs from runtime validator | parallel hand-written schema | use `tool_input_schema(name)` only |
| Candidate uvicorn `address already in use` | LTP shared-VC, host net namespace, port collision with old | set `MA3_PORT` to a different value on the candidate |
| Candidate `Load key ...: error in libcrypto` | SSH key extracted via `tr "\0" "\n"` truncated multi-line | extract `/proc/PID/environ` in binary, split on `\x00` |
| `POST /api/v2/jobs` returns `InvalidProtocolError` | wrong content type | `Content-Type: text/yaml` |
| dns-manager PATCH returns 200 but backend didn't change | JSON body instead of query string | use query string params; verify with follow-up GET |
| `instance_id: null` after manual uvicorn restart | env not sourced | `set -a; . ma3.env; set +a` before nohup |
| `state: RUNNING` after `executionType=STOPPED` | LTP transitions are async | trust the 202 and external probe; don't block |
| `record_count` drift between prod and candidate | candidate restored from old cron backup | take final backup AFTER candidate is up, restore, then flip |

## Production identity (as of 2026-05-16)

| Field | Value |
|---|---|
| URL | https://ma3.zhilicon.com |
| Backend | 10.100.193.54:18191 |
| Job | chuntao.hong~ma3-v2-prod-20260516-140109 |
| Commit | 25669aca74ac565c8c419f2657ed939d8a3ab701 |
| DNS proxy | dns-manager record `ma3` |
| Backup dir | /mnt/cephfs/home/chuntao.hong/ma3_v2_backups |
| PG | localhost:auto-detect / ma3db / ma3user |

Rollback: PATCH the dns-manager `ma3` record back to the previous
backend IP:port. Keep at least one prior `ma3-v2-prod-*` job's
`/api/v2/jobs/<owner>~<name>/config` exportable for fast resurrection.
</coding_guidelines>
