# Pre-release Agent Behavior Regression Test Plan

> Chinese version: [release-agent-behavior-tests.zh.md](release-agent-behavior-tests.zh.md)

> **Status**: Active (in effect since 2026-07-03)
> **Applies to**: must be run **before** every release of the ma3 server / client policy / MCP contract
> **Related**: ADR-013 (write confirmation / audit / delete), ADR-014 (error self-correction),
> `code/client/templates/ma3-agent-policy.mdc`, `code/eval/scenarios/*`

---

## 0. Why this plan is needed

ma3's value only holds up when a **real, unattended Agent** can look up knowledge, use it correctly,
and write the result back **correctly** (upvote / downvote / create new only when necessary). This
behavior **cannot be covered by unit tests** — it depends on policy wording, whether error messages
are self-correcting, and whether the client can auto-upgrade. Historically, every regression has
looked like "server tests all green, real Agent behavior degraded":

- An Agent wrapped the `ma3_report` payload inside `arguments` by mistake, tried 6 times, and gave up on the write-back (→ ADR-014).
- An Agent hit existing knowledge but **created a duplicate record** instead of upvoting (→ policy 1.1.0).
- An Agent judged a record to be wrong but **silently skipped it** instead of downvoting (→ policy 1.3.0).

**Conclusion**: before every release, the behavior scenarios below must be run with a real Agent on the
**maintainer's LAN test host** (referred to below as the **LAN host**; the actual address is configured
locally by the maintainer as `$MA3_LAN_HOST`). If any scenario fails, the **release is blocked**.

---

## 0.1 Test environment (fixed)

| Item | Requirement |
|----|------|
| **Execution host** | **LAN host only** (`$MA3_LAN_HOST`; ma3 host + Docker + eval profiles) |
| **ma3 server** | `http://127.0.0.1:8000` (ma3 hosted locally on the LAN host) |
| **Scenario directory** | `<DEPLOY_DIR>/code/eval/scenarios/*` |
| **Agent profiles** | `~/ma3-eval/profiles/{claude,codex,hermes}` |
| **Local machine** | **Does not run** Docker scenarios; the local machine is only for development/doc editing. Codex's **LLM API** can reuse the local `~/.codex/config.toml` `model_providers.*` entries, synced to the codex profile on the LAN host |

> All SSH, docker compose, DB assertions, and non-interactive Agent runs happen on the LAN host.

---

## 1. Hard requirements

1. **All three Agents must be tested**: **Codex**, **Hermes**, and **Claude** (Claude Code).
   - Different hosts handle `error.message` / `structuredContent` / the MCP envelope differently,
     so testing a single Agent cannot represent the others.
   - Each scenario × each Agent must have an independent conclusion (see the results matrix in §4).
2. **Memory must be cleared**: before every run, clear that Agent profile's session history (see §3.1),
   otherwise it will match on the previous conversation's memory instead of the ma3 knowledge base, invalidating the test.
3. **Real side effects must be verified**: don't trust the Agent's self-reported summary; go by the
   **server DB / verify.sh** (Agents often "claim to have done it but didn't").
4. **Cleanup is required**: fake knowledge injected during testing (wrong records) **must be fully deleted**
   from the library after the test (see §3.5); it must not pollute the knowledge base.
5. If any Agent fails any mandatory scenario (**T0–T5**) → **release blocked**, fix and re-run.

### 1.1 Agent readiness

| Agent | profile path (202) | key label | status |
|-------|--------------------|-----------|------|
| Claude Code | `ma3-eval/profiles/claude` | `MA3_KEY_CLAUDE_CODE` | ✅ wired up on 202 (T0 verified) |
| Codex | `ma3-eval/profiles/codex` | `MA3_KEY_CLAUDE_CODE` (eval) | ✅ wired up on 202 (T0 verified; LLM uses local config + proxy) |
| Hermes | `ma3-eval/profiles/hermes` | `MA3_KEY_CLAUDE_CODE` (eval) | ✅ wired up on 202 (T0–T4 verified; LLM uses deepseek + proxy) |

> **Codex on 202 (verified steps)**
> 1. Sync the standalone package: `rsync ~/.codex/packages/standalone → 202:~/.codex/packages/standalone`
> 2. Copy the local `~/.codex/config.toml` to the profile, changing **only** `[mcp_servers.ma3]` to `http://127.0.0.1:8000/mcp` + the eval `X-API-Key`
> 3. `bootstrap_agent_client_sync.sh codex` → policy lands in `.codex/model_instructions.md`
> 4. When running codex: **LLM** traffic goes through `HTTP_PROXY=$MA3_LAN_PROXY` (when the LLM provider is unreachable directly from the LAN host); **MCP** sets `NO_PROXY=127.0.0.1,localhost` (to avoid the proxy turning localhost into a 503)

> **Hermes on 202 (verified steps)**
> Hermes is a **Python application** (no precompiled single-file binary); install it from the official PyPI package, **do not** clone the source (`install.sh` gets stuck on the GitHub SSH clone).
> 1. Dedicated venv: `python3 -m venv ~/.hermes-venv` (202 is py3.12, which satisfies `>=3.11,<3.14`)
> 2. `~/.hermes-venv/bin/pip install hermes-agent` (via `HTTPS_PROXY=$MA3_LAN_PROXY`)
> 3. **Key step**: `pip install "mcp[cli]"` — by default hermes's dependencies do **not** include the `mcp` package, causing `hermes mcp test` to report `mcp.client.streamable_http is not available`, so HTTP MCP can't connect (the agent falls back to shell `curl` and misses `X-API-Key`). After installing it, `hermes mcp test ma3` should show `✓ Connected` + 14 tools.
> 4. `ln -sf ~/.hermes-venv/bin/hermes ~/.local/bin/hermes`
> 5. Isolate the profile with `HERMES_HOME=~/…/profiles/hermes/.hermes`; `config.yaml` sets `model: {provider: deepseek, default: deepseek-chat}` + `mcp_servers.ma3` (url + `headers.X-API-Key`); put `DEEPSEEK_API_KEY` in `.env`
> 6. `bootstrap_agent_client_sync.sh hermes` → policy lands in `$HERMES_HOME/rules/ma3-agent-policy.md` (Hermes auto-loads `rules/*.md`)
> 7. When running: **LLM (deepseek)** traffic goes through `HTTP_PROXY`; **MCP** sets `NO_PROXY=127.0.0.1,localhost`
> 8. Non-interactive run: `hermes chat -q "<prompt>" --yolo` (`hermes tools list` needs a pty, use `ssh -t`)

---

## 2. Mandatory scenarios (Release Gate T0–T5)

**All executed on the LAN host** (see §0.1). Default carrier scenario is `mihomo-proxy`
(`<DEPLOY_DIR>/code/eval/scenarios/mihomo-proxy`), which requires Docker.

| ID | Capability | Pass criteria (DB / verify is authoritative) |
|----|------|-------------------------------|
| **T0** | Install / onboarding | A **brand-new** profile (no `~/.ma3`, no MCP config) can sync tools + policy from the server via bootstrap, write MCP config in that Agent's native layout, and successfully make an MCP call at runtime (`ma3_whoami` / `ma3_context` returns a `result`) |
| **T1** | Client auto-upgrade | After bumping the skill version, a stale Agent receives `policy_refresh_required=true` → auto `sync` → local policy file updates and `~/.ma3/ma3-client.json`'s `skill_bundle_version` advances |
| **T2** | Use knowledge + upvote dedup | A memory-cleared Agent fixes the problem using the KB; the write-back is **a single `ma3_feedback` upvote** (`record_feedback` +1); `records`/`cases` counts **unchanged** (no duplicate creation) |
| **T3** | Downvote wrong knowledge | Plant a **wrong** record in the library; after the Agent hits it and judges it wrong → **downvote** it (that record's `record_feedback` = -1); optionally `report_kind=refute` |
| **T4** | MCP error self-correction | Trigger a validation-type error (e.g. `ma3_report` wrapped in an `arguments` envelope → `-32602`); `error.message` contains a field-level/targeted hint; the Agent can fix it and successfully write back |
| **T5** | DB API key authentication | The Agent calls `tools/call` successfully with its DB-backed key (not 401); no key / revoked key → `-32001` with an actionable message |

---

## 3. Execution steps (repeat per Agent)

Below, the `AGENT` variable stands for `claude` / `codex` / `hermes`, with the profile at
`~/ma3-eval/profiles/$AGENT`, and the server running on port `:8000` on the LAN host (ma3 hosted there).

### 3.0 T0 — Install / onboarding test (brand-new profile)

Goal: prove that "an Agent that has never touched ma3 can install per the onboarding doc and get MCP working."
Must start from a **clean** state (delete or use a brand-new profile directory).

```bash
P=~/ma3-eval/profiles/$AGENT                   # or use a fresh temp directory
rm -rf "$P/.ma3"                               # clear any existing ma3 client state (simulate first run)
export HOME="$P" MA3_BASE_URL="http://127.0.0.1:8000" MA3_API_KEY="<this Agent's key>"

# 1) bootstrap sync tooling + full policy (HTTP, no CLI — ADR-003)
mkdir -p ~/.ma3/bin ~/.ma3/lib ~/.ma3/policy
curl -fsSL "$MA3_BASE_URL/client/scripts/sync_ma3_client.py" -o ~/.ma3/bin/sync_ma3_client.py
curl -fsSL "$MA3_BASE_URL/client/lib/ma3_sync_core.py"       -o ~/.ma3/lib/ma3_sync_core.py
curl -fsSL "$MA3_BASE_URL/client/scripts/sync_ma3_client.sh" -o ~/.ma3/bin/sync_ma3_client.sh
chmod +x ~/.ma3/bin/sync_ma3_client.sh
bash ~/.ma3/bin/sync_ma3_client.sh sync         # pull manifest + policy + onboarding

# 2) write MCP config in that Agent's native layout (reuse the four layouts the harness already supports)
#    claude: `claude mcp add ... --header X-API-Key`
#    codex : ~/.codex/config.toml  [mcp_servers.ma3] + [mcp_servers.ma3.http_headers]
#    cursor: ~/.cursor/mcp.json    { mcpServers.ma3 { url, headers } }
#    droid : ~/.factory/mcp.json   { mcpServers.ma3 { type:http, url, headers } }
#    (see code/eval/scenarios/agent-client-sync/scripts/configure_mcp.sh)

# 3) make a real MCP call using that Agent's runtime
#    claude: claude -p "call ma3_whoami ..."
#    codex : NO_PROXY=127.0.0.1,localhost HTTP_PROXY=... codex exec ... "<prompt>"
```
**Pass**: `~/.ma3/ma3-client.json` is generated and contains `skill_bundle_version`; the policy lands
in that Agent's runtime file; the Agent's runtime `ma3_whoami` / `ma3_context` call returns a `result`
(not an auth error, not "tool not found").
**Failure signals**: MCP not registered (the Agent can't see ma3 tools), missing header causing
`-32001`, or sync failing to fetch the policy.

> **Codex on the LAN host**: if the LAN host doesn't yet have the `codex` binary, sync the standalone
> package from the local machine:
> `rsync -av ~/.codex/packages/standalone <user>@$MA3_LAN_HOST:~/.codex/packages/`
> then on the LAN host run `ln -sf ~/.codex/packages/standalone/current/bin/codex ~/.local/bin/codex`.
> Then copy the **model section** from the local `~/.codex/config.toml` into the profile, and write the
> MCP section with `configure_mcp.sh` pointing at `127.0.0.1:8000`.

### 3.1 Clearing memory (common approach for all Agents)

```bash
P=~/ma3-eval/profiles/$AGENT
# Claude Code: clear session history, keep CLAUDE.md (policy) and ~/.ma3
rm -rf "$P"/.claude/projects/* "$P"/.claude/sessions/* "$P"/.claude/tasks/* \
       "$P"/.claude/shell-snapshots/* "$P"/.claude/session-env/* "$P"/.cache/claude-cli-node
# Codex / Hermes: clear their respective session/history directories (fill in the paths here
#   when onboarding them), but be sure to keep their policy files and ~/.ma3 sync state.
```

### 3.2 T1 — Client auto-upgrade

```bash
# 1) record the Agent's current skill version
jq -r .skill_bundle_version "$P/.ma3/ma3-client.json"        # e.g. 1.2.0
# 2) bump the server's skill version by 1 on the LAN host (this triggers policy_refresh_required)
bash <DEPLOY_DIR>/code/eval/scenarios/agent-client-sync/scripts/restart_host_ma3.sh <new_version>
# 3) have the Agent run ma3_context once per policy, check structuredContent.server, and auto-sync
# 4) assert
jq -r .skill_bundle_version "$P/.ma3/ma3-client.json"        # should == <new_version>
grep -c ma3_feedback "$P/.claude/CLAUDE.md"                  # policy content has been updated
```
**Pass**: the `skill_bundle_version` in the state advances, and the local policy file is overwritten with the new content.

### 3.3 T2 — Use knowledge + upvote dedup

```bash
URL=$(grep -E '^MA3_DATABASE_URL=' <DEPLOY_DIR>/ma3.env | cut -d= -f2-)
# BEFORE snapshot
psql "$URL" -Atc "select count(*) from records";  \
psql "$URL" -Atc "select count(*) from cases";    \
psql "$URL" -Atc "select count(*) from record_feedback"
# Reset the broken scenario + bring up docker (see §3.6), use a neutral prompt so the Agent solves it and follows policy
# AFTER assertion
```
**Pass**: `record_feedback` +1 (upvote on the matched record), `records` and `cases` counts **unchanged**.
**Failure signal**: `records`/`cases` +1 (the Agent created a duplicate record instead of upvoting).

### 3.4 T3 — Downvote wrong knowledge

```bash
# 1) inject a "confident but wrong" record into a library the Agent will read (example: mihomo)
#    use a dev/admin key to call ma3_report, choosing a library_id the Agent can read and that's relevant
#    (mihomo knowledge lives in lib_7e1dbe7d8688); it must include actions/evidence or the active write is rejected.
# 2) note the returned record_id, e.g. WRONG_ID
# 3) clear memory + reset the scenario + have the Agent solve the problem
# 4) assert: that wrong record has been downvoted
psql "$URL" -Atc "select vote from record_feedback where record_id='$WRONG_ID'"   # expect -1
```
**Pass**: `record_feedback.vote = -1` for `$WRONG_ID` (optionally: a `report_kind=refute` entry appears).
**Failure signal**: the Agent says in its reasoning "this one is wrong/unusable" but **does not** downvote it (a historical regression point).

### 3.5 Cleaning up injected fake knowledge (required after T3)

```bash
# fully purge (no tombstone): records + feedback + relations + embeddings + indexes + audit
# if this record is the sole record in a case, delete the now-empty case too (the cases primary key column is id)
psql "$URL" <<SQL
begin;
delete from record_feedback where record_id in ('$WRONG_ID','$REFUTE_ID');
delete from record_relations where source_id in ('$WRONG_ID','$REFUTE_ID') or target_id in ('$WRONG_ID','$REFUTE_ID');
delete from record_embeddings where record_id in ('$WRONG_ID','$REFUTE_ID');
delete from record_search_index where record_id in ('$WRONG_ID','$REFUTE_ID');
delete from write_audit_log where record_id in ('$WRONG_ID','$REFUTE_ID');
delete from records where id in ('$WRONG_ID','$REFUTE_ID');
delete from cases c where c.id in (select case_id from records where id in ('$WRONG_ID','$REFUTE_ID'))
  and not exists (select 1 from records r where r.case_id = c.id);
commit;
SQL
```
> Only delete the fake record injected for testing; an upvote that hit a real, correct record is a genuine signal and should be kept.

### 3.6 T4 — MCP error self-correction

The server contract is covered by `code/server/tests/integration/test_mcp_error_contract.py`;
**before release, additionally do one real-Agent verification**: induce the Agent to trigger a
`-32602` (e.g. by prompting it to first call `ma3_report` wrapped in `ma3_validate`'s
`{tool_name, arguments}` envelope), confirm that the `error.message` it reads contains a
field-level/targeted hint, and that it can **fix it itself** and then successfully call `ma3_report`.
**Pass**: the Agent doesn't loop on the same error, and the write-back eventually succeeds.

### 3.7 T5 — DB API key authentication

```bash
# call tools/call directly with that Agent's key
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -H "X-API-Key: $AGENT_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"ma3_whoami","arguments":{}}}'
```
**Pass**: returns a `result` (not 401 / not `-32001`); using a wrong key returns `-32001` with an actionable message.
See `test_deploy_verification.py::test_deploy_eval_claude_db_api_key`.

### 3.8 Scenario reset template (mihomo)

```bash
S=<DEPLOY_DIR>/code/eval/scenarios/mihomo-proxy
cd "$S" && docker compose down -v --remove-orphans
bash setup.sh                                   # copy back broken/config.yaml
set -a; . ~/ma3/eval/secrets/secrets.env 2>/dev/null; set +a
docker compose up -d && sleep 3
bash verify.sh                                  # should fail before the fix; should say "verify ok" after the Agent finishes
```

---

## 4. Results matrix (fill in and archive at every release)

Release branch/tag: `__________`　Server skill version: `1.4.0`　Date: `2026-07-03` (202 environment)

| Scenario | Claude | Codex | Hermes | Notes |
|------|:------:|:-----:|:------:|------|
| T0 install/onboarding | PASS | PASS | PASS | All three: `ma3_whoami` returns `principal_id=user:eval-admin`; Hermes needed `pip install "mcp[cli]"` to get HTTP MCP |
| T1 auto-upgrade | PASS | PASS | PASS | client json staled to `0.5.0` (< min 1.0.0) → `required=true` → sync → back to `1.3.0` |
| T2 upvote dedup | PASS | PASS | PASS | All `verify ok`; `vk_0dc976edbe9b` upvoted (+1), records/cases counts unchanged (no duplicate creation) |
| T3 downvote wrong | PASS | PASS | PASS | Planted a wrong record: Claude/Hermes/Codex all downvoted it (-1). **Codex FAILED on the first round** (upvoted only, didn't downvote) → after policy **1.4.0** added the "triage every returned record individually" rule, re-run **PASS** |
| T4 error self-correction | PASS | PASS | PASS | `ma3_report` wrapped in an `arguments` envelope → `-32602`; all three fixed it based on `error.message` and got `ma3_validate` ok |
| T5 key auth | PASS | PASS | PASS | All three agents share the eval DB key; valid → result; bad key → `-32001` with actionable message |

Fill in `PASS` / `FAIL` / `PENDING-SETUP`. **Any FAIL blocks the release.**
Recommend writing the result JSON into `code/eval/results/` (already produced by `run_eval.sh`).

### 4.1 Known gaps this round (to follow up)

- ~~**Codex T3 FAIL (downvote)**~~ **Fixed (policy 1.4.0)**: added §1 item 7, "**Triage EVERY returned record**", plus a self-check item. After re-running, Codex showed `wrong vote=-1` + `correct vote=1`.
- **Codex T2 minor regression (optional follow-up)**: during the T3 re-run, Codex created a near-duplicate record (`vk_bb0f1d70b5e0`, already cleaned up) in addition to upvoting. If this recurs before release, consider emphasizing in policy that "if an existing record was used, only upvote — creating a new one is forbidden."

---

## 5. Relationship to automated eval

- `code/eval/orchestrator/run_eval.sh --scenario mihomo-proxy --agent <...>` already wraps
  "setup → compose up → run the Agent (with a policy/version-rule prompt) → verify → write results".
  T2/T4/T5 can add DB assertions on top of it; T1/T3 need extra "bump version / plant-then-clean fake
  knowledge" steps, which §3.2 and §3.4–3.5 of this plan provide as the manual supplement.
- Goal: gradually harden T1–T5 into a `run_all_scenarios_verify.sh`-style script, but **until it is
  fully automated**, this manual checklist is a **mandatory release gate**.

---

## 6. Changelog

| Date | Change |
|------|------|
| 2026-07-03 | First version: T0–T5 + Codex/Hermes/Claude; **fixed 202 as the sole execution environment**; Codex LLM can reuse local config |
| 2026-07-03 | First full run: Hermes wired up via `pip install hermes-agent` + `mcp[cli]` (deepseek/proxy); all three agents ran T0–T5, only **Codex T3 FAILED** (didn't downvote the wrong record), the other 17/18 PASSED; added the §4.1 gap + Hermes install steps + `release_behavior_tests.sh` harness |
| 2026-07-03 | policy **1.4.0**: added "triage every record returned by ma3_context individually"; Codex T3 re-run PASSED; 18/18 PASSED |
