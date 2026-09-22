# Deployment Overview

> Chinese version: [deployment.zh.md](deployment.zh.md)

> Detailed Authing steps: [deployment-authing.md](deployment-authing.md)

## Deployment Profiles

| Profile | Purpose | Auth | Database |
|---------|------|------|--------|
| **profile-saas** | Public SaaS / staging — **primary** | OIDC (e.g. Authing) + API Key | PostgreSQL |
| **profile-lan** | dev / intranet staging (any LAN host) | optional `MA3_DEV_AUTH=1` (intranet only) | Postgres or SQLite |
| **profile-selfhost** | Community self-hosting (Docker Compose) | bootstrap key / local accounts / optional OIDC | PostgreSQL (bundled in compose) |
| profile-ltp | legacy | — | not v1 core |

**Same binary**; profile behavior switches via environment variables. Docs are not tied to a specific host —
the LAN staging host is configured by the maintainer in a local deploy env file (not committed to git).

## Required Environment Variables (SaaS)

```bash
# Database
MA3_DATABASE_URL=postgresql://...

# OIDC (prefer MA3_OIDC_*; Authing can use the MA3_AUTHING_* aliases)
MA3_OIDC_ENABLED=1
MA3_OIDC_ISSUER=...
MA3_OIDC_CLIENT_ID=...
MA3_OIDC_CLIENT_SECRET=...
MA3_PUBLIC_BASE_URL=https://...

# Admins (must be non-empty when OIDC is on, otherwise startup is refused)
MA3_AUTH_ADMIN_USERS=admin@example.com

# Search (vector on by default)
# MA3_DISABLE_EMBEDDINGS=1

# HF cache (offline in production)
HF_HUB_OFFLINE=1
HF_HOME=/path/to/hf
```

## Community Self-Hosting (Compose)

See **[self-hosting.md](self-hosting.md)** and `deploy/self-host/` in the repo (bootstrap key / optional OIDC).

## Directories and Data

- Production code is fetched by the server into `$REMOTE_DIR/releases/<full-sha>`; operator
  worktrees are not uploaded. `$REMOTE_DIR/current` changes only after a successful cutover.
- Normal deploys send only compact arguments over SSH. The host reuses
  `$REMOTE_DIR/bin/prepare_git_release.sh`, then runs the cutover script from the fetched release.
- Runtime `ma3.env` and `data/` remain directly under `$REMOTE_DIR`, outside every release.
- Prewarm embeddings → `HF_HOME/hub/`
- The deploy bundle includes `server/scripts/` (seed fallback)

Production Git access uses anonymous HTTPS for a public repository, or a repository-scoped,
read-only GitHub Deploy Key for a private repository.
See [deploy/README.md](../../deploy/README.md) for host bootstrap, exact-SHA guards, directory
layout, deployment, and rollback.

## Health Checks

```bash
curl -s "$BASE/healthz"
curl -s "$BASE/doctor"   # or MCP ma3_doctor
```

## Post-Deploy Acceptance (mandatory)

Every production deploy (`ENV_MODE=preserve`) must be accepted per the standard procedure in **[deploy/README.md](../../deploy/README.md)**:

1. Push the desired commit to the configured `GIT_REF`.
2. `./deploy/deploy.sh deploy/deploy.<prod>.env` (the host fetches that exact commit; the local config is not in git; remote smoke + public `verify_ma3_prod.sh` run automatically)
3. Or standalone verification: `MA3_BASE_URL=$MA3_BASE_URL bash deploy/common/verify_ma3_prod.sh` (against the production public URL)

Checklist summary: healthz / UI & Auth / client bundle / anonymous MCP rejection / `ma3dev` rejection / pytest.  
When `VERIFY_API_KEY` is unset, MCP test cases requiring an API key are skipped; this must be noted when reporting.

LAN (`regenerate`) uses `deploy/common/verify_ma3.sh`; do not mix it with the production checklist.

## Caddy blue-green (SaaS preserve, optional)

For near-zero downtime on bare-metal + Caddy (not Compose self-host): enable `BLUE_GREEN=1` in the local prod deploy env after the live Caddyfile imports `deploy/caddy/upstream.caddy.example` (see `deploy/caddy/Caddyfile.ma3.io.example` and **[deploy/README.md](../../deploy/README.md)**). Until that one-time wiring is done, keep the classic `pkill` restart path.

## To Be Added

- [x] `deploy/self-host` docker compose example (see [self-hosting.md](self-hosting.md))
- [ ] systemd example
- [x] Secret management (`MA3_API_KEY_ENCRYPTION_SECRET`, bootstrap key file)
- [ ] Backup/restore procedure (summary already written into self-hosting.md)
- [x] Caddy blue-green cutover helpers (`deploy/common/bluegreen_remote.sh`, opt-in via `BLUE_GREEN=1`)
