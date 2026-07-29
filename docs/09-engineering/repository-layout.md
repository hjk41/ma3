# Repository layout

> Chinese version: [repository-layout.zh.md](repository-layout.zh.md)

> Update this file in the same PR when the structure changes. The live tree in the repo is the source of truth.

## Top level

```text
ma3/
├── README.md / README.zh.md / CONTRIBUTING.md / CHANGELOG.md / LICENSE / SECURITY.md
├── code/
│   ├── server/          FastAPI: MCP, portal UI, REST, auth, search
│   ├── client/          HTTP bundle: manifest, policy, sync scripts
│   └── eval/            Evaluation scenarios (not a v1 release artifact)
├── docs/                Systematized docs (01–09; English default, *.zh.md Chinese)
└── deploy/
    ├── self-host/       Community Compose delivery
    └── *.sh / README    Maintainer push & verify (env files not in git)
```

Runtime data and secrets stay in the deploy directory / environment variables (e.g. `<DEPLOY_DIR>`). **Do not** assume a committed `data/` or `ma3.env` under the repo root.

## Server modules

```text
code/server/app/
├── api/           MCP, portal HTML, REST (keys/orgs/libraries/setup/admin), i18n, setup_gate
├── services/      mcp, onboarding, api_key, org, invite, local_auth, setup, billing, …
├── storage/       db, search, ranking
├── models/        mcp_payloads
├── auth/          session, OIDC / local
└── core/          config, security
```

## Client surface

```text
code/client/
├── agent-onboarding.md
├── templates/ma3-agent-policy.mdc
├── scripts/sync_ma3_client.{sh,py}
└── lib/ma3_sync_core.py
```

## Tests

```text
code/server/tests/
├── unit/
└── integration/
```

CI: `.github/workflows/ci.yml` (unit + integration + self-host Docker build).

## Design process drafts

`docs/09-engineering/design-archive/` keeps only per-topic **decision summaries** (not contractual). Planned design items: `design-backlog.md`.
