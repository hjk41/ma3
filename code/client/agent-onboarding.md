# ma3 Multi-Agent Onboarding Guide

> Chinese version: [agent-onboarding.zh.md](agent-onboarding.zh.md)

This document is the **single source of instructions**. You do not need to clone the ma3 repo, and you do **not** need to run an install script or CLI.
Give the URL of this document to each agent, and let the agent **configure the MCP connection and behavior policy on its own**.

**Policy template (must read)**: `GET /client/templates/ma3-agent-policy.mdc`
**Design docs**: [docs/02-architecture/decisions/009-client-sync-scheme-b.md](../../docs/02-architecture/decisions/009-client-sync-scheme-b.md), [docs/02-architecture/system-overview.md](../../docs/02-architecture/system-overview.md) §3
**Example ma3 address**: `https://ma3.io` (replace with your environment's address)

> **ma3 v1 (ADR-003)**: **MCP + policy only**. No `install.sh`, no `ma3_client.py`, no CLI plugin.
> Client upgrade = read the MCP `server` block → curl-fetch `/client/*` → overwrite local rules → restart the agent.

> **Scheme B**: The local source of truth is `~/.ma3/ma3-client.json`. Paths are **filled in by the agent itself**
> in `~/.ma3/ma3-client.env` (template: `GET /client/templates/ma3-client.env.example`),
> and the sync command is: `bash ~/.ma3/bin/sync_ma3_client.sh sync`

---

## Agent Self-Check Checklist (for the agent reading this document)

If the user requests onboarding to ma3, complete the section that corresponds to **your runtime**, in order, then perform **onboarding verification**.

### 0. Ask the user for credentials (must be done first)

**Do not** use placeholder keys from the documentation, and **do not** assume `ma3dev` is available (it is only enabled on some LAN dev instances when `MA3_DEV_AUTH=1`).

Confirm with the user, or obtain from context:

| Variable | Description |
|------|------|
| `MA3_BASE_URL` | e.g. `https://ma3.io` or `http://ma3.example.internal:8000` (self-hosted/internal instance) |
| `MA3_API_KEY` | A **writer** key the user self-created in the portal (`ma3k_…` plaintext, shown only once) |

If the user has not created a key yet, guide them to:

1. Open `{MA3_BASE_URL}/ui/keys/` in a browser, sign up/log in via Authing
2. On first login a personal library is created automatically; fill in a label and click "Create"
3. **Immediately copy** the plaintext key and paste it to you (or write it into `~/.ma3/ma3-client.env` / a shell profile)
4. Default grants: personal-library writer + Community Library (`lib_default`) writer

If the key is lost or leaked: go back to `/ui/keys/` to revoke and recreate it.

### 1. One-time bootstrap

```bash
mkdir -p ~/.ma3/bin ~/.ma3/lib
export MA3_BASE_URL=https://ma3.io   # replace with the user's environment
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

See your section under "Per-Agent Configuration" below. Use the `MA3_API_KEY` provided by the user in the header.

### 3. Configure the behavior policy + Agent Skill

Sync writes:

- `~/.ma3/policy/ma3-agent-policy.mdc` (FIRST-ACTION GATE + write-back rules)
- `~/.ma3/skills/ma3/SKILL.md` (recall → work → remember skill)

Copy **both** to your runtime per the env file's comments (Cursor rules + `~/.cursor/skills/ma3/`, Claude `CLAUDE.md` + `~/.claude/skills/ma3/`, Codex `AGENTS.md` + `~/.codex/skills/ma3/`).

When MCP returns `policy_refresh_required: true`, run sync again and re-copy policy **and** skill.

### 4. Onboarding verification (must complete)

Once MCP is connected, use **the user-provided key** to run a read/write smoke test, confirming writes land in the **personal library** (`ma3_report` without `library_id`):

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

If any step returns 401/403 → ask the user to check whether the key is valid or has been revoked in `/ui/keys/`.
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

In the examples below, replace `YOUR_MA3_API_KEY` with the plaintext key the user created and provided from `/ui/keys/`.
You may also use environment variables: `${env:MA3_API_KEY}` (Cursor), or shell expansion `${MA3_API_KEY}` (for Claude's `mcp add`, `export` it first).

### Cursor

**MCP** — create or edit `~/.cursor/mcp.json`:

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
| `ma3_report` returns 401/403 | Check whether the API key is valid or was revoked in the UI |
| The user hasn't provided a key | Guide them to create one at `/ui/keys/`; do not guess `ma3dev` |

---

## Short Explanation for the User

> Open `{MA3_BASE_URL}/client/agent-onboarding.md` and have the agent configure MCP and the policy according to the document.
> **First**, self-create an API key at `/ui/keys/` **and give the plaintext key to the agent**; the agent will use that key to complete onboarding verification (a read/write test on the personal library).
> No repo clone needed, no CLI install needed.
