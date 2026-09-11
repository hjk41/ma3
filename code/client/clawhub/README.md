# ma3 OpenClaw / ClawHub bundle

Path A package for [ClawHub](https://clawhub.ai/): remote MCP + ma3 skill.

ClawHub requires `openclaw.plugin.json` for `bundle-plugin` uploads. This folder
also ships Agent Plugins / Claude / Cursor markers so hosts can discover MCP + skills.

| File | Role |
|------|------|
| `openclaw.plugin.json` | ClawHub / OpenClaw package manifest |
| `plugin.json` | Agent Plugins 1.0.0 manifest |
| `mcp.json` / `.mcp.json` | Streamable HTTP MCP → `https://ma3.io/mcp` (OAuth; no API key) |
| `.claude-plugin/plugin.json` | Claude-compatible marker |
| `.cursor-plugin/plugin.json` | Cursor-compatible marker |
| `skills/ma3/SKILL.md` | Knowledge-loop skill (mirror of `../skills/ma3/SKILL.md`) |

## Install (after published)

```bash
openclaw plugins install clawhub:ma3
# or scoped: openclaw plugins install clawhub:@<owner>/ma3
openclaw gateway restart
openclaw mcp doctor ma3 --probe
```

Complete browser login when prompted for ma3 OAuth. CLI/headless: use a portal key from https://ma3.io/ui/keys/ (never publish keys).

## Publish to ClawHub

```bash
npm i -g clawhub
clawhub login
clawhub whoami

# Keep skill in sync with the canonical client skill:
cp ../skills/ma3/SKILL.md ./skills/ma3/SKILL.md

# Commit + push this folder first. ClawHub dry-run resolves the GitHub tree for
# source attribution when run inside the ma3 checkout.
clawhub package publish ./code/client/clawhub \
  --family bundle-plugin \
  --name ma3 \
  --display-name "ma3" \
  --version 1.6.0 \
  --topics "mcp,memory,knowledge" \
  --source-repo hjk41/ma3 \
  --source-path code/client/clawhub \
  --changelog "ma3 remote MCP + knowledge-loop skill" \
  --dry-run

# remove --dry-run to upload
```

Use `--owner <handle>` for org publishes. Scoped names must match the owner (e.g. `@acme/ma3`).

## Auth notes

- Interactive: URL-only MCP; client handles OAuth against ma3.
- Do not put `X-API-Key` or secrets in this package.
