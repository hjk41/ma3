# Contributing to ma3

Thanks for helping. This document covers **how to contribute**; product intent lives in `docs/`.

## Language policy

| Surface | Language |
|---------|----------|
| Source code & comments | English |
| Primary docs (`docs/`, root `README.md`) | Chinese (source of truth) |
| English entry | `README.en.md` (gateway only; docs tree is not fully translated) |
| Legal / security policy | English or bilingual as noted in each file |

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

CI runs unit + integration tests and builds the self-host Docker image (see `.github/workflows/ci.yml`).

## Pull requests

1. Keep changes focused; prefer small PRs.
2. Behavior / API changes must update the matching doc under `docs/` (and README links when entry points change).
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
