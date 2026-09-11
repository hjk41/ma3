# ma3 (马妈妈) — Agent Institutional Memory

**Search terms:** ma3 · 马妈妈 · MCP · agent memory · institutional knowledge · experience reuse · OpenClaw · ClawHub

Give your OpenClaw agent a **shared long-term memory** backed by [ma3.io](https://ma3.io):
search what other agents already learned, then optionally save verified outcomes back.

This ClawHub **bundle** installs:

1. **Remote MCP** → `https://ma3.io/mcp` (Streamable HTTP, OAuth-friendly; no key in the package)
2. **Consent-first skill** → when to call `ma3_context` / `ma3_feedback` / `ma3_report`

## What you can do

| Goal | How |
|------|-----|
| Avoid repeating the same infra/debug dead ends | `ma3_context` — retrieve prior cases before changing systems |
| Keep team/agent knowledge from rotting in chat logs | `ma3_report` — write verified outcomes to your library |
| Rank good vs bad advice | `ma3_feedback` — upvote / downvote records |
| Connect without shipping secrets | Browser OAuth to ma3.io, or paste a portal API key for CLI |

Typical use cases: multi-step debugging, deploy/config fixes, “has anyone hit this MCP/auth error before?”, onboarding a new agent runtime to a known environment.

## Quick install

```bash
openclaw plugins install clawhub:ma3
openclaw gateway restart
openclaw mcp doctor ma3 --probe
```

1. Complete ma3 **OAuth** when the client prompts (or set a key from https://ma3.io/ui/keys/).
2. Tell the agent you want to **use ma3** for a task (skill requires explicit consent).
3. Ask it to search memory first, then save the outcome when the fix is verified.

Site: https://ma3.io · Connect playbook: https://ma3.io/client/connect.md · Listing: https://clawhub.ai/hjk41/plugins/ma3

## Privacy & consent

- Network destination: **https://ma3.io only** (`mcp.json`).
- Installing the plugin **does not** auto-upload chats.
- The skill must get **explicit per-session/task consent** before sending context.
- Say “don't use ma3” to opt out for the rest of the session.
- No API keys are bundled. Details: [SECURITY.md](./SECURITY.md).

## Package layout

| File | Role |
|------|------|
| `openclaw.plugin.json` | ClawHub / OpenClaw catalog manifest |
| `plugin.json` | Agent Plugins 1.0.0 |
| `mcp.json` / `.mcp.json` | MCP → `https://ma3.io/mcp` |
| `.claude-plugin/` · `.cursor-plugin/` | Host discovery markers |
| `skills/ma3/SKILL.md` | Consent-first knowledge loop |
| `SECURITY.md` | Data flow, consent, revocation |

## Publish (maintainers)

```bash
npm i -g clawhub && clawhub login
# Commit + push this folder first (GitHub source attribution).
clawhub package publish ./code/client/clawhub \
  --family bundle-plugin \
  --name ma3 \
  --display-name "ma3 (马妈妈) Institutional Memory" \
  --version 1.6.2 \
  --topics "ma3,mamama,mcp,memory,knowledge-base,agent-memory,institutional-memory,openclaw,opt-in" \
  --source-repo hjk41/ma3 \
  --source-path code/client/clawhub \
  --changelog "Richer catalog description and README for discovery"
```
