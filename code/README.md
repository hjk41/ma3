# ma3 v1 — 实现

Greenfield server per `../docs/PITCH.md` and ADR 001–008.

## Quick start

```bash
cd /home/hct/ma3_v1/code/server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export MA3_DEV_AUTH=1
export MA3_DEV_API_KEY=ma3dev
export MA3_DATABASE_URL=sqlite:///./data/ma3.db
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001 --app-dir .
```

## Smoke checks

```bash
curl -sS http://127.0.0.1:8001/healthz | jq .
curl -sS http://127.0.0.1:8001/client/manifest.json | jq .
curl -sS http://127.0.0.1:8001/mcp/info | jq .
```

MCP `tools/list` / `tools/call` via POST `/mcp` with header `X-API-Key: ma3dev`.

## Layout

```text
server/app/
  api/          health, mcp, client static, observatory stub
  core/         config, dev auth
  models/       MCP payloads (Pydantic single source of truth)
  services/     mcp_tool_service, mcp_server_info
  storage/      sqlite bootstrap + queries
client/         HTTP bundle：manifest, onboarding, policy, sync scripts, env template (ADR-009)
```

## Tests

```bash
cd server && .venv/bin/pytest -q tests/unit
```

## Next milestones

1. PostgreSQL + org/library ACL (SaaS profile)
2. Vector search + `MA3_DISABLE_EMBEDDINGS`
3. Observatory 完整只读 + 人 — 维护者纠偏 UI
4. OIDC auth profile
