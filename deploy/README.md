# ma3 deployment and verification

> Chinese version: [README.zh.md](README.zh.md)

## Principles (mandatory)

**After every deployment, the operator must run the verification checklist themselves and only report success to the user when everything passes.**  
Do not claim “deployment complete” without verification.

On failure: fix → redeploy → **re-run the full checklist** → then report (with a short result summary).

---

## Standard path (every production deploy)

Production (`ENV_MODE=preserve`, e.g. ma3.io) always follows this path:

```bash
# 1. Deploy (automatic: remote Git fetch by exact SHA → assert ma3.env → blue-green → verify)
./deploy/deploy.sh deploy/deploy.ma3.io.env

# 2. If auto-verify did not pass, or you only want to re-run verification (no redeploy):
export MA3_BASE_URL=https://ma3.io
export MA3_EXPECT_INSTANCE_ID=ma3-v1-hk
export MA3_EXPECT_PUBLIC_BASE_URL=https://ma3.io
# Recommended: set a production read-only/ops API key to unlock doctor / context / whoami MCP cases
# export MA3_API_KEY=ma3k_...   # or set VERIFY_API_KEY= in deploy.ma3.io.env
bash deploy/common/verify_ma3_prod.sh
```

On the preserve path, after remote loopback smoke passes, `deploy.sh` **automatically** runs `verify_ma3_prod.sh` locally against the public URL.

### Production checklist (`verify_ma3_prod.sh`)

| # | Check | Pass criteria |
|---|------|----------|
| 1 | `/healthz` | `status=ok`; `instance_id` / `public_base_url` match config; includes `vector`; **no** `dev_auth` |
| 2 | UI / Auth | `/ui/home/` → 200; `/ui/me/`, `/ui/observatory/`, `/ui/keys/` → 302; `/auth/login` → 302 to Authing/OIDC |
| 3 | Client bundle | `/client/manifest.json`, `agent-onboarding.md`, policy/env templates, sync scripts, `mcp-tools.json` all 200 and non-empty |
| 4 | MCP anonymous & discovery | `tools/list` ≥ 13; anonymous `ma3_whoami` has `readable_library_ids=[]`; anonymous `ma3_context` → `-32001 authentication required`; `X-API-Key: ma3dev` → rejected |
| 5 | pytest | Required: `healthz`, `client_bundle` (plus friendly login page when OIDC is off); with `MA3_API_KEY`, also full deploy suite (anonymous reject + doctor/context) |
| 6 | Report | Use the template below; explicitly note anything not tested (e.g. missing API key) |

LAN / regenerate (intranet staging) still uses `deploy/common/verify_ma3.sh` (may use `ma3dev`). Do not mix with the production checklist.

---

## Generic deploy script + local env configs

Only **one generic script** `deploy/deploy.sh` is in git; per-environment values live in **local, gitignored**
`*.env` files (real hosts/paths/instance names). The repo only commits `deploy/deploy.env.sample`.

```
deploy/
├── deploy.sh                 # generic deploy driver (in git)
├── deploy.env.sample         # config template (in git)
├── caddy/                    # blue-green Caddy snippets (in git)
│   ├── upstream.caddy.example
│   └── Caddyfile.ma3.io.example
├── common/verify_ma3.sh      # LAN/regenerate verify (in git)
├── common/verify_ma3_prod.sh # production/public verify (in git) — required on every prod deploy
├── common/bluegreen_remote.sh # Caddy blue-green cutover helpers (in git)
├── common/prepare_git_release.sh # remote Git cache + immutable release preparation
├── tests/test_prepare_git_release.sh # release preparation regression test
├── README.md                 # this file (in git)
├── .gitignore                # ignore local *.env and legacy scripts
├── deploy.<lan>.env          # local: LAN staging (not in git)
└── deploy.<prod>.env         # local: production (not in git)
```

Usage:

```bash
./deploy/deploy.sh deploy/deploy.<lan>.env     # deploy to LAN staging
./deploy/deploy.sh deploy/deploy.<prod>.env    # deploy to production
# or: DEPLOY_CONFIG=deploy/deploy.<lan>.env ./deploy/deploy.sh
```

New environment: copy `deploy.env.sample` to local `deploy.<name>.env` and fill in values.

### Two modes (`ENV_MODE` in config)

| | `regenerate` (LAN/dev staging) | `preserve` (production, e.g. ma3.io) |
|---|---|---|
| Remote `ma3.env` | Regenerated from `LEGACY_ENV_FILE` + config | **Keep remote env**; only inject `MA3_GIT_COMMIT` |
| Dev backdoor | `DEV_AUTH` may be `1` (LAN may use `ma3dev`) | Abort if `MA3_DEV_AUTH=1` |
| Legacy backfill | `RUN_MIGRATION=1` runs backfill | No migration |
| Source | `rsync` by default | **Remote Git fetch of one exact commit** by default |
| uvicorn bind | `0.0.0.0` (direct LAN) | `127.0.0.1` (Caddy reverse proxy on 443) |
| Restart | `pkill` → start on `MA3_PORT` | Default same; with `BLUE_GREEN=1` → idle port + Caddy upstream reload |
| Verify | `common/verify_ma3.sh` (pytest; often `ma3dev`) | remote loopback smoke + **`common/verify_ma3_prod.sh` (public URL)** |

### Production source: remote Git release (mandatory for preserve)

The operator machine no longer uploads its working tree. It resolves the local commit to a full
40-character SHA and sends only the trigger/helper over SSH. The server fetches the configured ref,
verifies that the exact SHA is reachable from that ref, and materializes an archive at:

```text
$REMOTE_DIR/
├── ma3.env                    # shared, host-owned, never in Git
├── data/                      # shared runtime and blue-green state
├── repo.git/                  # bare fetch cache
├── releases/<full-sha>/       # immutable application source + per-release .venv
├── current -> releases/<sha>  # updated only after successful cutover
└── previous -> releases/<sha> # prior successful release, when available
```

Required production config:

```bash
DEPLOY_SOURCE=git
GIT_REPO_URL=https://github.com/YOUR_ORG/ma3.git
GIT_REF=refs/heads/main
# Private repository only:
# GIT_DEPLOY_KEY=/root/.ssh/ma3_github_deploy
```

Repository access:

1. For a public repository, use its anonymous `https://github.com/...git` URL; no credential belongs
   on the host.
2. For a private repository, create a dedicated SSH key on the server and add its public half as a
   **read-only Deploy Key**. Never copy a developer's personal private key to the server.
3. For SSH Git URLs, pin GitHub's host key in the deploy user's `known_hosts`; deployment enforces
   `StrictHostKeyChecking=yes`. Keep the key outside `$REMOTE_DIR/releases` with restricted permissions.

Normal deploy and rollback:

```bash
# Deploy local HEAD after it has been pushed to GIT_REF.
./deploy/deploy.sh deploy/deploy.ma3.io.env

# Roll back by redeploying a previous commit that is still reachable from GIT_REF.
DEPLOY_GIT_COMMIT=<full-or-local-resolvable-sha> \
  ./deploy/deploy.sh deploy/deploy.ma3.io.env
```

The server refuses a missing/unfetched SHA, a SHA outside `GIT_REF`, or a reused release directory
whose commit marker does not match. `current` is moved only after the new process is healthy and the
blue-green cutover succeeds. Uncommitted and untracked files on the operator machine are never deployed.

### Caddy blue-green (optional, preserve only)

Default preserve deploys still briefly stop the old uvicorn before starting the new one. For near-zero downtime behind Caddy:

1. **One-time on the host**: make the site block `import` an upstream snippet (see `deploy/caddy/Caddyfile.ma3.io.example`). Seed `$REMOTE_DIR/data/bluegreen/upstream.caddy` from `deploy/caddy/upstream.caddy.example` if needed. Validate: `caddy validate --config /etc/caddy/Caddyfile`.
2. **In `deploy.<prod>.env`**: set `BLUE_GREEN=1`, `UVICORN_HOST=127.0.0.1`, ports A/B, `CADDY_UPSTREAM_FILE`, `CADDY_RELOAD_CMD`.
3. **Each deploy**: start new uvicorn on the idle port → wait `/healthz` → rewrite upstream snippet → `caddy reload` → public smoke (rollback Caddy on failure) → drain → stop old process. State: `$REMOTE_DIR/data/bluegreen/active_port`.

Status without deploying:

```bash
ssh user@host 'REMOTE_DIR=/opt/ma3_deploy CADDY_UPSTREAM_FILE=/opt/ma3_deploy/data/bluegreen/upstream.caddy bash /opt/ma3_deploy/current/deploy/common/bluegreen_remote.sh status'
```

Do **not** enable `BLUE_GREEN=1` until the live Caddyfile already imports the upstream file — otherwise reload will not move traffic and stopping the old port will outage the site.

### Guardrails against cross-environment mistakes

- **Host guard `ALLOWED_HOSTS`**: if `REMOTE_HOST` is not allowed → `exit 2`. A LAN config can never push to production.
- **preserve keeps host state outside releases**: Git archives contain code only; `ma3.env` and `data/` remain under `$REMOTE_DIR`. The script only updates `MA3_GIT_COMMIT` after invariant checks.
- **commit guard**: production deploys use a full SHA verified as reachable from `GIT_REF`; no floating `git pull` is used.
- **preserve pre-start asserts**: `MA3_DEV_AUTH≠1`, `MA3_INSTANCE_ID`, `MA3_PUBLIC_BASE_URL`, no LAN proxy vars.

### Env files (LAN staging runtime)

| File | Purpose |
|------|------|
| `<LEGACY_ENV_FILE>` (e.g. `~/ma3/ma3.env`) | Postgres, OIDC, HF cache paths (`LEGACY_ENV_FILE` for `regenerate`) |
| `<DEPLOY_DIR>/ma3.env` (e.g. `~/ma3_deploy/ma3.env`) | v1 runtime (generated by `deploy.sh` in `regenerate` mode) |

Production `ma3.io` `ma3.env` is maintained by hand, contains secrets, is not in git, and is left untouched by `preserve`.

---

## LAN verification (`verify_ma3.sh`)

Called automatically by `deploy.sh` in `regenerate` mode; can also be run manually:

```bash
export MA3_BASE_URL=http://127.0.0.1:8000
export MA3_API_KEY=ma3dev
export MA3_EXPECT_INSTANCE_ID=<your-instance-id>   # must match WRITE_INSTANCE_ID
export MA3_EXPECT_ROOT_REDIRECT=/ui/me/
export MA3_READY_TIMEOUT=180
bash deploy/common/verify_ma3.sh
```

### Post-deploy inventory (automatic in regenerate mode)

1. **Before deploy** — `scripts/db_inventory.py` snapshot  
2. **During deploy** — `MA3_MIGRATE_BACKFILL=1` upserts `legacy_records` into v1 `records`  
3. **After deploy** — inventory again; assert v1 count did not shrink  
4. **pytest gate** — `MA3_EXPECT_MIN_RECORDS` from post-deploy actual `v1_records`

### Optional manual checks

| Check | Command / expectation |
|--------|-----------|
| Browser Authing login + key creation | `code/server/scripts/e2e_authing_ui.py` (needs `AUTHING_TEST_USER/PASS`) |

### Known ignorable items

- `test_deploy_database_migration_state`: fails when DB is already migrated and `legacy_records` table is gone; does not affect production.

---

## Report template (to the user)

After a successful production deploy:

```
Deployed to https://ma3.io (commit <shortsha>, instance ma3-v1-hk)

Verification (verify_ma3_prod.sh):
- healthz OK: features include vector/oidc, no dev_auth; public_base_url=https://ma3.io
- UI: home 200; me/observatory/keys unauthenticated 302; /auth/login → Authing
- client bundle: onboarding + manifest + sync scripts 200
- MCP: tools/list≥13; anonymous context rejected; ma3dev rejected
- pytest: healthz + client_bundle [+ authed MCP if VERIFY_API_KEY set]

Notes: (list anything not tested, e.g. "VERIFY_API_KEY not set; skipped doctor/context")
```

---

## Related scripts

| Script | Status | Notes |
|------|------|------|
| `deploy/deploy.sh` | git | Generic deploy driver |
| `deploy/deploy.env.sample` | git | Config template |
| `deploy/common/prepare_git_release.sh` | git | Exact-SHA remote fetch and release preparation |
| `deploy/tests/test_prepare_git_release.sh` | git | Git release integrity/reachability tests |
| `deploy/tests/test_deploy_git_source.sh` | git | Deploy-driver bootstrap/reuse tests |
| `deploy/common/verify_ma3_prod.sh` | git | **Production public verify (required every prod deploy)** |
| `deploy/common/verify_ma3.sh` | git | LAN / regenerate verify |
| `deploy/deploy.*.env` | local | Per-env real config (not in git) |
| `code/server/scripts/e2e_authing_ui.py` | git | Browser-level Authing login/logout E2E |
