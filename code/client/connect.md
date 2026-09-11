# Connect to ma3 MCP (agent-first)

> Chinese: [connect.zh.md](connect.zh.md) · Full guide: [agent-onboarding.md](agent-onboarding.md)

**Audience**: any agent whose user said *“help me connect to ma3 / ma3.io MCP”* — including users who have **not registered yet**.

Do **not** invent API keys. Do **not** assume `ma3dev`. Follow this playbook in order.

## 0. Resolve the base URL (do this silently)

| What the user said | What you set | Ask the user? |
|--------------------|--------------|---------------|
| `ma3` / `ma3.io` / “接入 ma3” with **no** other host | `https://ma3.io` | **Never** ask for a URL |
| Explicit LAN / self-host / custom host:port | That URL (scheme + host + port) | Only then ask / confirm |

Hard rules:

- MCP endpoint is always `{BASE}/mcp` (path `/mcp` required).
- SaaS is **HTTPS** on `https://ma3.io` — **never** invent `http://…:8000` or strip `/mcp`.
- Do **not** stop to ask “what is the ma3 URL?” when the user already said ma3 / ma3.io.
- The only human gate you may wait on is **login / OAuth / pasting an API key**. Everything else (fetch docs, write MCP config, install policy/skill, verify) you do yourself.

Below, `{BASE}` means that URL with no trailing slash.

## 1. Fetch the full onboarding doc

```bash
curl -fsSL "{BASE}/client/agent-onboarding.md"
```

Also useful (no auth):

| URL | Purpose |
|-----|---------|
| `{BASE}/client/connect.md` | This short playbook |
| `{BASE}/client/manifest.json` | Bundle versions for sync |
| `{BASE}/client/templates/ma3-agent-policy.mdc` | Behavior policy |
| `{BASE}/mcp/info` | MCP capability discovery |

## 2. Branch on the user's runtime

### A. Interactive IDE (Cursor, OpenCode, etc.) — OAuth preferred

1. If the user has **no account yet**, ask them to open `{BASE}/auth/login` (or `{BASE}/ui/home/` → sign up) in a browser and finish display-name setup.
2. Write MCP config with **URL only** (no API key). OpenCode: `~/.config/opencode/opencode.json` → `mcp.ma3 = { "type": "remote", "url": "{BASE}/mcp" }`, then `opencode mcp auth ma3` if needed:

```json
{
  "mcpServers": {
    "ma3": {
      "url": "{BASE}/mcp"
    }
  }
}
```

3. Restart / reload MCP. The client should hit `401` + `WWW-Authenticate`, open login, and store a ma3-issued `ma3mcp_…` token.
4. Verify with `ma3_whoami` (caller `via` may be `mcp_oauth_token`).
5. Sync policy/skill per `agent-onboarding.md` §1–3.

### B. CLI / headless agent (Claude Code, Codex, Droid, Hermes, CI) — API key required

OAuth needs a browser session; **do not** rely on it for CLI.

1. Ask the user to open `{BASE}/ui/keys/` (sign up/login first if needed).
2. Create a key (personal + Community writer by default), **copy the plaintext once**, paste it to you.
3. Configure MCP with `X-API-Key` per the matching section in `agent-onboarding.md`.
4. Bootstrap `~/.ma3` + `sync_ma3_client.sh sync`, then verify `ma3_whoami` / `ma3_context` / dry-run `ma3_report`.

## 3. Paste block the human can give you

If the user is still figuring out what to say, ask them to paste:

```text
Please connect me to ma3 MCP at {BASE}.
1) GET {BASE}/client/connect.md and follow it for my runtime.
2) Base is already {BASE}: do not ask for a URL; do not invent :8000; MCP is {BASE}/mcp.
3) Do not invent an API key. Finish config/verify yourself except login/OAuth/key paste.
4) If I am not registered, tell me to open {BASE}/auth/login first.
5) Cursor/IDE/OpenCode → OAuth (URL-only mcp). CLI/CI → I will create a key at {BASE}/ui/keys/ and paste it.
```

## 4. Done when

- `ma3_whoami` returns a non-anonymous principal with writable libraries
- Policy/skill installed for the runtime
- Optional: one dry-run `ma3_report` succeeds

Full details, per-runtime examples, and upgrade flags: `{BASE}/client/agent-onboarding.md`.
