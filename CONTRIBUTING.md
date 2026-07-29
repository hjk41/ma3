# Contributing to ma3

Thanks for helping. This document covers **how to contribute**; product intent lives in `docs/`.

> Chinese version: [CONTRIBUTING.zh.md](CONTRIBUTING.zh.md) (if present)

## Language policy

| Surface | Language |
|---------|----------|
| Source code & comments | English |
| **Default docs** (`README.md`, `docs/**/*.md`) | **English** (source of truth for links & PRs) |
| Chinese docs | Sibling `*.zh.md` next to the English file (e.g. `pitch.zh.md`) |
| Legal / security | English default; Chinese siblings where applicable |

When you change behavior documented in `docs/`, update the **English** file. Update the `.zh.md` sibling when you can; do not leave English stale.

## Development setup

Follow root `README.md` §C (local server) or `deploy/self-host/` for Compose.

```bash
cd code/server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export MA3_DEV_AUTH=1 MA3_DEV_API_KEY=ma3dev MA3_DISABLE_EMBEDDINGS=1
export MA3_DATABASE_URL=sqlite:///./data/ma3.db
pytest -q tests/unit
```

CI runs unit + integration (+ Postgres smoke) and builds the self-host Docker image (see `.github/workflows/ci.yml`).

## Pull requests

1. Keep changes focused; prefer small PRs.
2. Behavior / API changes must update the matching **English** doc under `docs/` (and README links when entry points change). Prefer updating `.zh.md` in the same PR when practical.
3. Architecture changes need an ADR under `docs/02-architecture/decisions/`.
4. Do not commit secrets, `deploy.*.env`, or local `tmp-*/` scratch trees.
5. Fill the PR template; link issues when applicable.

## Interface boundary (do not blur)

| Actor | Interface |
|-------|-----------|
| Agent (knowledge loop) | MCP only (`POST /mcp`) |
| Humans | Portal UI `/ui/*` |
| Admins / automation | Portal REST `/api/*` (session or user API key; **not** a public stable third-party API promise) |

See `docs/03-backend/api-overview.md` and ADR-003.

## Docs maintenance

- Feature index: `docs/01-product/feature-index.md`
- Doc map / maturity: `docs/README.md`
- Design decision summaries only: `docs/09-engineering/design-archive/` (not specs)
- Planned design topics: `docs/09-engineering/design-backlog.md`

## License

Contributions are accepted under the Apache License 2.0 (`LICENSE`).
