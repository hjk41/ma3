# agent-client-sync — Docker multi-agent install/upgrade tests (real CLIs)

> Chinese version: [README.zh.md](README.zh.md)

**ma3 runs on the host (LAN test host `:8000`); Docker only installs agent binaries and exercises sync.**

## Architecture

```text
LAN host (maintainer intranet test host)
  ma3_v1 :8000          ← real service; upgrade tests restart + MA3_SKILL_VERSION
  docker compose
    runner              ← Claude / Codex / Cursor / Droid real CLIs
      → MA3_BASE_URL=http://host.docker.internal:8000
      → per-agent HOME (volume agent-homes)
```

The old compose also ran a ma3 container for **isolated upgrades** (freely bump skill version), but:

- Duplicated the already-deployed instance on the LAN host
- Increased build failure surface (Docker image layers, proxy, etc.)
- Did not test the ma3 you actually use

**Current approach**: during the upgrade phase, run `restart_host_ma3.sh 2.0.0` on the host, then sync again from agents in Docker; restore to `1.0.0` when finished.

## Real binaries (runner image)

| Agent | Install |
|-------|------|
| Claude Code | `npm i -g @anthropic-ai/claude-code` |
| Codex | `npm i -g @openai/codex` |
| Cursor | `curl cursor.com/install` → `agent` / `cursor-agent` |
| Droid | host binary bundle or factory installer |

## Run on the LAN host

```bash
# Deploy first (generic script + local LAN config; see deploy/README.md)
./deploy/deploy.sh deploy/deploy.<lan>.env
# Then run this scenario
cd code/eval/scenarios/agent-client-sync && bash run.sh
```

## Environment variables

| Variable | Default | Notes |
|------|------|------|
| `MA3_HOST_MA3_URL` | `http://host.docker.internal:8000` | runner → host ma3 |
| `MA3_RESTORE_VERSION` | `1.0.0` | skill version restored after the test |
| `MA3_DIR` | `~/ma3_deploy` | host ma3 path (restart script) |
