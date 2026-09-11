# ma3 Multi-Agent Onboarding Guide

> Chinese version: [agent-onboarding.zh.md](agent-onboarding.zh.md)

This document is the **single source of instructions**. You do not need to clone the ma3 repo, and you do **not** need to run an install script or CLI.
Give the URL of this document to each agent, and let the agent **configure the MCP connection and behavior policy on its own**.

If the user only said “help me connect to ma3 / ma3.io MCP” (including **before** they registered), start with the short playbook: `GET /client/connect.md`.

**Policy template (must read)**: `GET /client/templates/ma3-agent-policy.mdc`
**Short connect playbook**: `GET /client/connect.md`
**Design docs**: [docs/02-architecture/decisions/009-client-sync-scheme-b.md](../../docs/02-architecture/decisions/009-client-sync-scheme-b.md), [docs/02-architecture/system-overview.md](../../docs/02-architecture/system-overview.md) §3, [016-mcp-oauth-plus-api-keys.md](../../docs/02-architecture/decisions/016-mcp-oauth-plus-api-keys.md)
**Example ma3 address**: `https://ma3.io` (only replace when the user named a different host)

> **ma3 v1 (ADR-003)**: **MCP + policy only**. No `install.sh`, no `ma3_client.py`, no CLI plugin.
> Client upgrade = read the MCP `server` block → curl-fetch `/client/*` → overwrite local rules → restart the agent.

> **Scheme B**: The local source of truth is `~/.ma3/ma3-client.json`. Paths are **filled in by the agent itself**
> in `~/.ma3/ma3-client.env` (template: `GET /client/templates/ma3-client.env.example`),
> and the sync command is: `bash ~/.ma3/bin/sync_ma3_client.sh sync`

---

## Agent Self-Check Checklist (for the agent reading this document)

If the user requests onboarding to ma3, complete the section that corresponds to **your runtime**, in order, then perform **onboarding verification**.

### 0. Resolve base URL + auth path (must be done first)

**Do not** invent API keys, and **do not** assume `ma3dev` is available (it is only enabled on some LAN dev instances when `MA3_DEV_AUTH=1`).

Resolve `MA3_BASE_URL` **without asking** when the user said ma3 / ma3.io → use `https://ma3.io`. Ask for a URL **only** for explicit LAN/self-host. MCP path is always `{BASE}/mcp` (never invent `:8000`). Then branch on **runtime**:

| Runtime | Auth | What you need from the user |
|------|------|------|
| Cursor / OpenCode / interactive IDE MCP | **OAuth preferred** | Account login in browser; MCP config may be **URL-only** (`{BASE}/mcp`) |
| CLI / CI / headless (Claude Code, Codex, Droid, Hermes, scripts) | **`X-API-Key` required** | Writer key (`ma3k_…`) from `{BASE}/ui/keys/` |

Except login / OAuth / pasting a key, finish the rest yourself (docs, config, policy/skill, verify).

**If the user has no account yet:** ask them to open `{MA3_BASE_URL}/auth/login` (or `/ui/home/` → register), finish display-name setup, then continue. For a minimal agent playbook, see `{MA3_BASE_URL}/client/connect.md`.

**API key path** (CLI / when the user prefers a key):

1. Open `{MA3_BASE_URL}/ui/keys/`, sign up/log in
2. On first login a personal library is created automatically; fill in a label and click "Create"
3. **Immediately copy** the plaintext key and paste it to you (or write it into `~/.ma3/ma3-client.env` / a shell profile)
4. Default grants: personal-library writer + Community Library (`lib_default`) writer

If the key is lost or leaked: go back to `/ui/keys/` to revoke and recreate it.

**OAuth path** (Cursor / interactive): after the user can log into the portal, configure MCP with URL only and complete the popup login. Permissions follow portal Layer-1 entitlements — no API key required for interactive use.

### 1. One-time bootstrap

```bash
mkdir -p ~/.ma3/bin ~/.ma3/lib
export MA3_BASE_URL=https://ma3.io   # default for ma3.io; only change for self-host
curl -fsSL "$MA3_BASE_URL/client/templates/ma3-client.env.example" -o ~/.ma3/ma3-client.env
# Edit ~/.ma3/ma3-client.env: MA3_BASE_URL, policy install path comments, etc.
curl -fsSL "$MA3_BASE_URL/client/scripts/sync_ma3_client.py" -o ~/.ma3/bin/sync_ma3_client.py
curl -fsSL "$MA3_BASE_URL/client/lib/ma3_sync_core.py" -o ~/.ma3/lib/ma3_sync_core.py
curl -fsSL "$MA3_BASE_URL/client/scripts/sync_ma3_client.sh" -o ~/.ma3/bin/sync_ma3_client.sh
chmod +x ~/.ma3/bin/sync_ma3_client.sh
bash ~/.ma3/bin/sync_ma3_client.sh sync
```

From then on, every MCP call should carry the values from `~/.ma3/ma3-client.json`:

- `client_version` ← `skill_bundle_version`
- `tool_schema_version` ← `tool_schema_version`

### 2. Configure MCP

See your section under "Per-Agent Configuration" below.

- **OAuth (Cursor / interactive):** URL-only MCP entry; complete browser login when challenged.
- **API key (CLI / CI):** use the user-provided `MA3_API_KEY` in `X-API-Key`.

### 3. Configure the behavior policy + Agent Skill

Sync writes:

- `~/.ma3/policy/ma3-agent-policy.mdc` (FIRST-ACTION GATE + write-back rules)
- `~/.ma3/skills/ma3/SKILL.md` (recall → work → remember skill)

Copy **both** to your runtime per the env file's comments (Cursor rules + `~/.cursor/skills/ma3/`, Claude `CLAUDE.md` + `~/.claude/skills/ma3/`, Codex `AGENTS.md` + `~/.codex/skills/ma3/`).

When MCP returns `policy_refresh_required: true`, run sync again and re-copy policy **and** skill.

### 4. Onboarding verification (must complete)

Once MCP is connected (OAuth token or API key), run a read/write smoke test, confirming writes land in the **personal library** (`ma3_report` without `library_id`):

1. **`ma3_whoami`** — confirm the principal and that the visible library list includes the personal library
2. **`ma3_context`** — e.g. `problem`: "ma3 onboarding connectivity test", `target_product`: "ma3", `task_type`: "onboarding"
3. **`ma3_validate`** — dry-run the `ma3_report` payload you are about to write
4. **`ma3_report`** — write one test record, e.g.:
   - `problem`: "ma3 onboarding connectivity test"
   - `outcome`: "resolved"
   - `result_summary`: "Agent completed onboarding: whoami, context, and personal-library write succeeded."
   - `task_type`: "onboarding"
   - `tags`: `["onboarding", "connectivity-test"]`
   - **Do not** pass `library_id` (defaults to the personal library)
   - You may use `idempotency_key` to avoid duplicate writes on repeated onboarding

If any step returns 401/403 → for API-key setups, check `/ui/keys/`; for OAuth, re-login via the MCP client and confirm the portal session works at `/auth/login`.
If `client_update_required: true` → run `sync_ma3_client.sh sync` and reload MCP first, then continue verification.

### 5. Wrap-up

- If `mcp_reload_required` → reload MCP; otherwise restart the agent runtime
- Report back to the user: the whoami identity, whether context returned results, and the `record_id` from the report (if any)

**Both layers are required**: MCP alone → the agent may not proactively call it; policy alone → there are no tools to call.

### Mandatory Behavior After Onboarding (Policy v2)

| Phase | Requirement |
|------|------|
| Every MCP call | Include **`client_version`** + **`tool_schema_version`** (read from `~/.ma3/ma3-client.json`) |
| Every MCP response | Read **`policy_refresh_required`** / **`mcp_reload_required`** / **`client_update_required`** |
| Any upgrade flag | Run **`sync_ma3_client.sh sync`**; if MCP changed, reload MCP |
| Task start | Call `ma3_context` as **one of the first actions** for non-trivial work |
| `ma3_context` fails | **Retry once**; if it still fails, **tell the user in one sentence** that ma3 is unavailable |
| Task end | Reusable results → **`ma3_validate` + `ma3_report`** (with `client_update_required` already false) |
| Before wrap-up | Self-check checklist (see policy template §4) |

---

## The `server` Block in MCP Responses (Client Upgrade — Policy-Driven)

**Every** MCP `tools/call`'s `structuredContent` carries a top-level `server` field, for example:

```json
{
  "cases": [],
  "server": {
    "service_version": "1.0.0",
    "skill_bundle_version": "1.0.0",
    "min_client_version": "1.0.0",
    "recommended_client_version": "1.0.0",
    "client_version_reported": true,
    "client_version": "0.0.1",
    "client_update_required": true,
    "client_update_recommended": true,
    "client_update_urls": [
      "/client/manifest.json",
      "/client/agent-onboarding.md",
      "/client/templates/ma3-agent-policy.mdc"
    ]
  }
}
```

**What the agent must do (Option 1 — policy-enforced):**

1. **Every** MCP call must include `client_version` (use `"0.0.0"` if never synced; the server will mark it as stale).
2. Read `structuredContent.server`:
   - `client_update_required: true` → **stop the write path**; curl-fetch and overwrite local policy per `client_update_urls`; tell the user to restart; retry with the new `skill_bundle_version` until `required` is false
   - `client_update_recommended: true` → refresh the policy before writing back, or give the user a one-sentence reminder
3. **How to upgrade (sync is recommended; the script self-updates)**:
   ```bash
   bash ~/.ma3/bin/sync_ma3_client.sh sync
   # If stderr indicates tooling was updated, run sync once more
   # Then copy the policy to your runtime per the MA3_POLICY_* comments in ~/.ma3/ma3-client.env
   ```
4. Sync updates `~/.ma3/ma3-client.json`; reload MCP when the MCP schema changes.

The MCP `initialize` response's `serverInfo` also includes `min_client_version` / `recommended_client_version`, which can be compared quickly at the start of a session.

---

## Target Behavior

| Timing | Action |
|------|------|
| Before starting a non-trivial task | **`ma3_context`** + **`client_version`** |
| On MCP response | Check the **`structuredContent.server`** upgrade flags |
| `client_update_required` | Refresh policy → restart → write again |
| Root cause / deployment / reusable fix | **`ma3_validate`** → **`ma3_report`** (once `required` is false) |
| Before wrap-up | Self-check checklist (policy §4) |

Always use `redaction_mode: auto`, and never write secrets, private keys, subscription URLs, or large raw logs.

Policy details are authoritative in `/client/templates/ma3-agent-policy.mdc`.

---

## Per-Agent Configuration

**Recommended for Cursor / human-interactive MCP clients:** connect with the MCP URL only and complete **OAuth popup login** (MCP Authorization Spec). Permissions match your portal Layer-1 library entitlements — no API key required for interactive use.

**Recommended for Agent / CI / headless runtimes:** continue using `X-API-Key` from `/ui/keys/` or self-host bootstrap.

In the key-based examples below, replace `YOUR_MA3_API_KEY` with the plaintext key the user created and provided from `/ui/keys/`.
You may also use environment variables: `${env:MA3_API_KEY}` (Cursor), or shell expansion `${MA3_API_KEY}` (for Claude's `mcp add`, `export` it first).

### Cursor

**MCP (OAuth, preferred for interactive use)** — create or edit `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "ma3": {
      "url": "https://ma3.io/mcp"
    }
  }
}
```

Cursor should discover `/.well-known/oauth-protected-resource`, open the login flow, and attach the ma3-issued access token. Ensure you can log into the same ma3 host in a browser (`/auth/login`).

**MCP (API key, Agent/CI)** — same file with an explicit key:

```json
{
  "mcpServers": {
    "ma3": {
      "url": "https://ma3.io/mcp",
      "headers": {
        "X-API-Key": "${env:MA3_API_KEY}"
      }
    }
  }
}
```

**Behavior policy** — recommended to install as a Cursor rule (always apply), plus the Agent Skill:

```bash
mkdir -p ~/.cursor/rules ~/.cursor/skills/ma3
curl -fsSL https://ma3.io/client/templates/ma3-agent-policy.mdc \
  -o ~/.cursor/rules/ma3-agent-policy.mdc
# Prefer sync output after bootstrap; or fetch skill directly:
curl -fsSL https://ma3.io/client/skills/ma3/SKILL.md \
  -o ~/.cursor/skills/ma3/SKILL.md
# After sync, equivalently:
# cp ~/.ma3/policy/ma3-agent-policy.mdc ~/.cursor/rules/
# cp ~/.ma3/skills/ma3/SKILL.md ~/.cursor/skills/ma3/
```

**Restart** Cursor → confirm `ma3` is connected under **Settings → Tools & MCP**.

---

### OpenCode

**MCP (OAuth, preferred)** — edit `~/.config/opencode/opencode.json` (Windows: `%USERPROFILE%\.config\opencode\opencode.json`):

```json
{
  "mcp": {
    "ma3": {
      "type": "remote",
      "url": "https://ma3.io/mcp"
    }
  }
}
```

Then authenticate:

```bash
opencode mcp auth ma3
```

Complete the browser login when prompted. Verify with `opencode mcp list` (ma3 should not show SSE/content-type errors).

**MCP (API key, headless)** — same remote URL plus header:

```bash
opencode mcp add ma3 --url https://ma3.io/mcp --header "X-API-Key=${MA3_API_KEY}"
```

Behavior policy: install `/client/templates/ma3-agent-policy.mdc` into your OpenCode instruction/rules path if you use one; otherwise keep it under `~/.ma3/policy/` after sync.

---

### OpenClaw / ClawHub

Preferred path for OpenClaw: install the **Agent Plugins bundle** (remote MCP + skill) from ClawHub after it is published:

```bash
openclaw plugins install clawhub:ma3
# scoped form once published under an owner: clawhub:@<owner>/ma3
openclaw gateway restart
openclaw mcp doctor ma3 --probe
```

Bundle source in this repo: `code/client/clawhub/` (`plugin.json` + `mcp.json` → `https://ma3.io/mcp` + `skills/ma3/SKILL.md`). Publish steps: see that folder’s `README.md`.

Manual MCP (without ClawHub):

```bash
openclaw mcp add ma3 \
  --url https://ma3.io/mcp \
  --transport streamable-http \
  --auth oauth
openclaw mcp login ma3
```

CLI/headless OpenClaw: use an API key from `/ui/keys/` instead of OAuth (headers / env per OpenClaw docs).

---

### Claude Code

```bash
claude mcp remove ma3 2>/dev/null || true
export MA3_BASE_URL=https://ma3.io          # per the user's environment
export MA3_API_KEY=YOUR_MA3_API_KEY           # provided by the user from /ui/keys/
claude mcp add --scope user --transport http ma3 \
  "${MA3_BASE_URL}/mcp" \
  --header "X-API-Key: ${MA3_API_KEY}"
```

Behavior policy: write the body of `/client/templates/ma3-agent-policy.mdc` into `~/.claude/CLAUDE.md`.

Agent Skill:

```bash
mkdir -p ~/.claude/skills/ma3
cp ~/.ma3/skills/ma3/SKILL.md ~/.claude/skills/ma3/SKILL.md
# or: curl -fsSL "$MA3_BASE_URL/client/skills/ma3/SKILL.md" -o ~/.claude/skills/ma3/SKILL.md
```

---

### Factory Droid

`~/.factory/mcp.json`:

```json
{
  "mcpServers": {
    "ma3": {
      "type": "http",
      "url": "https://ma3.io/mcp",
      "headers": { "X-API-Key": "YOUR_MA3_API_KEY" },
      "disabled": false
    }
  }
}
```

Behavior policy: write into `~/.factory/AGENTS.md`.

---

### OpenAI Codex

`~/.codex/config.toml`:

```toml
[mcp_servers.ma3]
url = "https://ma3.io/mcp"
enabled = true

[mcp_servers.ma3.http_headers]
X-API-Key = "YOUR_MA3_API_KEY"
```

Behavior policy: write into `~/.codex/model_instructions.md`.

---

### Hermes Agent

```yaml
mcp_servers:
  ma3:
    url: "https://ma3.io/mcp"
    headers:
      X-API-Key: "YOUR_MA3_API_KEY"
```

In an already-open session run **`/reload-mcp`**, or restart Hermes.

---

## API Key (Self-Service)

1. Open `{MA3_BASE_URL}/ui/keys/` in a browser, sign up/log in via Authing
2. On first login a personal library is created automatically; fill in a label and click "Create"
3. **Immediately copy** the plaintext key (shown only once), and give it to the agent to fill into the MCP `X-API-Key`
4. Default grants: your personal-library writer + Community Library writer
   - `ma3_report` without `library_id` → writes to your personal library
   - To write to the community library → pass `library_id: "lib_default"` explicitly
5. If the key is lost/leaked: go back to `/ui/keys/` to revoke and recreate it

> **LAN dev exception**: instances with `MA3_DEV_AUTH=1` may use `ma3dev` as a break-glass credential; production environments **must** use a portal key.

---

## Verification

```bash
export MA3_BASE_URL=https://ma3.io
export MA3_API_KEY=YOUR_MA3_API_KEY   # provided by the user

curl -sf "$MA3_BASE_URL/healthz"
curl -sf "$MA3_BASE_URL/client/manifest.json" | jq .skill_bundle_version
curl -sf -H "X-API-Key: $MA3_API_KEY" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  "$MA3_BASE_URL/mcp" | jq '.result.tools[].name'
```

After onboarding, the agent completes **onboarding verification** (`ma3_whoami` → `ma3_context` → `ma3_validate` → `ma3_report` writing to the personal library).

---

## Troubleshooting

| Symptom | Fix |
|------|------|
| MCP is present but never called proactively | Policy was not written to `~/.cursor/rules/ma3-agent-policy.mdc` or the equivalent global instructions |
| Agent never writes back to ma3 | Check the policy's mandatory report requirement; the writer key; whether it's blocked by `client_update_required` |
| `client_update_required` is always true | curl-refresh the policy; change `client_version` to the manifest's `skill_bundle_version` |
| `ma3_context` times out | `curl $MA3_BASE_URL/healthz` |
| `ma3_report` returns 401/403 | API key invalid/revoked, or OAuth token missing/expired — re-auth or recreate key |
| The user hasn't registered | Send them to `/auth/login`; then OAuth (IDE) or `/ui/keys/` (CLI) |
| CLI agent stuck on OAuth | OAuth needs a browser — switch to `X-API-Key` from `/ui/keys/` |

---

## Short Explanation for the User

> Paste this to your agent (or open `{MA3_BASE_URL}/client/connect.md`):
>
> *Please connect me to ma3 MCP at `{MA3_BASE_URL}`. GET `{MA3_BASE_URL}/client/connect.md` and follow it. Do not invent an API key. Cursor/IDE → OAuth (URL-only). CLI → I will create a key at `/ui/keys/` and paste it.*
>
> After sign-in, your home page (`/ui/me/`) also shows a copyable paste-to-agent block.
> No repo clone needed, no CLI install needed.
