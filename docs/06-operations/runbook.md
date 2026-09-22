# Operations Runbook

> Chinese version: [runbook.zh.md](runbook.zh.md)

Handoff-ready steps for the operated SaaS instance (`https://ma3.io`).  
Full deploy mechanics: [deploy/README.md](../../deploy/README.md).  
Health / alerts / SLOs: [monitoring-and-health.md](monitoring-and-health.md).

**Operator rule:** after every production change, run verification yourself; only report success when it passes.

---

## 1. Contacts / on-call

| Role | Path |
|------|------|
| Primary operator | Repo maintainer (single-maintainer posture today) |
| Paging | Feishu via `ma3-alert-sink` (host 202 probe + app-host Alertmanager) |
| Tickets | Manual follow-up from Feishu / GitHub Issues |

There is no separate 24×7 rota. Treat Feishu pages as the on-call signal.

---

## 2. Release (production / `ENV_MODE=preserve`)

### Preconditions

- Local checkout on the commit to ship; CI green on that commit preferred.
- The commit is pushed to the configured `GIT_REF`.
- Gitignored config present: `deploy/deploy.ma3.io.env` (`REMOTE_HOST`, `ALLOWED_HOSTS`, `DEPLOY_SOURCE=git`, Git remote/ref/deploy-key path, `BLUE_GREEN=1`, `VERIFY_API_KEY` optional).
- SSH to the app host works (direct or via your usual proxy).
- The app host can anonymously fetch the public HTTPS repository; for a private repository, it has a repository-scoped, read-only Deploy Key and pinned GitHub SSH host key.
- Remote `/opt/ma3_deploy/ma3.env` already provisioned (secrets; never overwritten by deploy).

### Steps

```bash
# From repo root (activate .venv if you use local Python tools)
./deploy/deploy.sh deploy/deploy.ma3.io.env
```

What this does automatically:

1. Resolve local HEAD to a full SHA; on the host, **fetch** `GIT_REF`, verify the SHA is reachable, and prepare `releases/<sha>`.
2. **Assert** production env invariants (`MA3_DEV_AUTH≠1`, instance id, public URL, no LAN proxy vars).
3. **pip install** in that release's `code/server/.venv`.
4. Start the new process with **`MA3_GIT_COMMIT`**; persist it only after health/cutover succeeds.
5. **Restart** uvicorn:
   - With `BLUE_GREEN=1`: start idle port → `/healthz` → rewrite Caddy upstream → `caddy reload` → public smoke → drain → stop old port; update Prometheus `file_sd` target.
   - Without blue-green: `pkill` old process → start on `MA3_PORT`.
6. Atomically move `current` (and retain `previous`), then run **remote loopback smoke** + local **`verify_ma3_prod.sh`** against the public URL.

### If auto-verify was skipped or you only want to re-check

```bash
export MA3_BASE_URL=https://ma3.io
export MA3_EXPECT_INSTANCE_ID=ma3-v1-hk
export MA3_EXPECT_PUBLIC_BASE_URL=https://ma3.io
# export MA3_API_KEY=ma3k_...   # or VERIFY_API_KEY in deploy.ma3.io.env
bash deploy/common/verify_ma3_prod.sh
```

### Blue-green status (no deploy)

```bash
ssh root@<app-host> \
  'REMOTE_DIR=/opt/ma3_deploy \
   CADDY_UPSTREAM_FILE=/opt/ma3_deploy/data/bluegreen/upstream.caddy \
   bash /opt/ma3_deploy/current/deploy/common/bluegreen_remote.sh status'
```

---

## 3. Rollback

Prefer the lightest path that restores a known-good `/healthz` and public verify.

### A. Blue-green cutover failed mid-flight

`deploy.sh` / `bluegreen_cutover` already rolls **Caddy upstream** back to the previous port if public smoke fails, and stops the new idle process. Confirm with `bluegreen_remote.sh status`, then re-run `verify_ma3_prod.sh`.

### B. Bad commit already live (code regression)

```bash
DEPLOY_GIT_COMMIT=<known-good-sha> \
  ./deploy/deploy.sh deploy/deploy.ma3.io.env
```

That reuses or prepares the known-good release and performs another blue-green cutover. The SHA
must remain reachable from `GIT_REF`; no local checkout/reset or working-tree upload is required.

### C. Emergency: point Caddy at the other slot (only if old uvicorn still listening)

```bash
# On app host — only when the previous port is still healthy
REMOTE_DIR=/opt/ma3_deploy
# shellcheck: source helpers
source "${REMOTE_DIR}/current/deploy/common/bluegreen_remote.sh"
# write upstream to the healthy port, then:
#   bluegreen_write_upstream <port>
#   bluegreen_write_prometheus_targets <port>
#   eval "$CADDY_RELOAD_CMD"
```

If the old process was already killed after drain, use path **B** instead.

### D. Config-only mistake in `ma3.env`

Edit `/opt/ma3_deploy/ma3.env` on the host (never put secrets in Git), then restart via a normal deploy or a careful `pkill` + uvicorn start on the live port. Re-run verify.

---

## 4. Database schema / “migration”

Production **does not** run a separate Alembic/Flyway step in `preserve` mode.

| Mode | Behavior |
|------|----------|
| `preserve` (ma3.io) | App applies/ensures schema on startup (`code/server` storage layer, including optional pgvector helpers). No `RUN_MIGRATION` backfill. |
| `regenerate` (LAN) | May run legacy backfill when `RUN_MIGRATION=1` (see `deploy/deploy.sh`). |

### Verify after deploy

- Public `/healthz`: `status=ok`, expected `instance_id` / `public_base_url`, `vector` in features, **no** `dev_auth`.
- Authed `ma3_doctor` (with ops API key): `status=ok`, `database` / `pgvector_ready` as expected.
- Optional: `pytest` deploy suite via `verify_ma3_prod.sh` when `MA3_API_KEY` is set.

**Destructive DB changes** (manual SQL, restore from backup) are out of band: snapshot first, change in a maintenance window, then full verify. Keep Postgres backups per your host provider; this runbook does not replace backup policy.

---

## 5. Logs and common greps

### App host (`/opt/ma3_deploy`)

| Source | Location |
|--------|----------|
| uvicorn (classic) | `/tmp/ma3-v1-uvicorn.log` |
| uvicorn (blue-green) | `/tmp/ma3-v1-uvicorn-8000.log`, `/tmp/ma3-v1-uvicorn-8001.log` |
| Last healthz JSON | `/tmp/ma3-healthz.json` (and per-port `/tmp/ma3-healthz-<port>.json`) |
| Process pid file | `/opt/ma3_deploy/ma3.pid` |
| Runtime env | `/opt/ma3_deploy/ma3.env` (secrets — do not paste into tickets) |
| Blue-green state | `/opt/ma3_deploy/data/bluegreen/active_port`, `upstream.caddy`, `prometheus-targets.json` |
| Alert sink (if on app host) | `/var/log/ma3/probe-alerts.jsonl`, `journalctl -u ma3-alert-sink` |
| Prometheus / Grafana / AM | Docker: `ma3-prometheus`, `ma3-grafana`, `ma3-alertmanager` (UI loopback only) |

```bash
# Live port + recent errors
ss -ltn | grep -E '800[01]|9090|3000'
tail -n 80 /tmp/ma3-v1-uvicorn-8001.log   # adjust port
grep -E 'ERROR|Traceback|CRITICAL' /tmp/ma3-v1-uvicorn-*.log | tail

# Public vs loopback
curl -sf https://ma3.io/healthz | python3 -m json.tool
curl -sf http://127.0.0.1:$(cat /opt/ma3_deploy/data/bluegreen/active_port)/healthz | python3 -m json.tool
```

### Operator laptop / host 202 (off-host probe)

| Source | Location |
|--------|----------|
| Probe timer | `systemctl status ma3-probe.timer` |
| Probe logs | `journalctl -u ma3-probe.service -n 50` |
| Alert JSONL | `/var/log/ma3/probe-alerts.jsonl` |
| Feishu env | `/etc/ma3/feishu.env`, `/etc/ma3/probe.env` (not in git) |

```bash
sudo tail -f /var/log/ma3/probe-alerts.jsonl
# Manual sink test:
curl -s -X POST http://127.0.0.1:8787/ -H 'Content-Type: application/json' \
  -d '{"event":"ma3_probe_fail","base_url":"https://ma3.io","instance_id":"ma3-v1-hk","detail":"runbook-test","ts":"…"}'
```

### Observability UI (SSH tunnel)

```bash
ssh -L 3000:127.0.0.1:3000 -L 9090:127.0.0.1:9090 root@<app-host>
# Grafana http://127.0.0.1:3000  Prometheus http://127.0.0.1:9090
```

Restart app-host stack (if containers died):

```bash
ssh root@<app-host> 'REMOTE_DIR=/opt/ma3_deploy bash /opt/ma3_deploy/deploy/observability/run_saas_stack.sh'
```

---

## 6. Alert quick responses

| Signal | Meaning | First checks |
|--------|---------|----------------|
| `ma3_probe_fail` / Feishu probe FAIL | Public reachability from host 202 | `https://ma3.io/healthz`, Caddy, live uvicorn port, DNS |
| `ma3_probe_recover` | Probe recovered | Confirm no ongoing deploy blip |
| `Ma3ScrapeDown` | Prom cannot scrape `/metrics` | `prometheus-targets.json` vs live port; `MA3_METRICS_ENABLED=1` |
| `Ma3High5xx` / `Ma3AvailabilityFastBurn` | API 5xx / fast error-budget burn | uvicorn logs, recent deploy, DB, embeddings |
| `Ma3ContextSlow` | `ma3_context` p95 high | DB/pgvector, embedding service |

Details: [monitoring-and-health.md](monitoring-and-health.md), [deploy/observability/README.md](../../deploy/observability/README.md).

---

## 7. Common operations (quick reference)

| Scenario | Steps | Doc |
|------|------|------|
| First Authing deployment | console + env + verification curl | [deployment-authing.md](deployment-authing.md) |
| Add a product admin | update `MA3_AUTH_ADMIN_USERS` + restart | [authentication.md](../03-backend/authentication.md) |
| User cannot log in | check callback URL, issuer, cookies | deployment-authing |
| MCP 401 | key deleted/expired? `ma3_doctor` | [getting-started.md](../05-agent/getting-started.md) |
| Search has no vector | `MA3_DISABLE_EMBEDDINGS`, HF cache | [system-overview.md](../02-architecture/system-overview.md) |
| Startup fails on admin allowlist | set `MA3_AUTH_ADMIN_USERS` | portal-permissions |
| Public `/metrics` must stay closed | Caddy block; verify with `verify_ma3_prod.sh` | [monitoring-and-health.md](monitoring-and-health.md) |

---

## 8. Acceptance checklist (this runbook)

- [x] Release steps (exact-SHA Git release → restart/blue-green → smoke / `verify_ma3_prod.sh`)
- [x] Rollback procedure (Caddy auto-rollback, redeploy good SHA, emergency upstream)
- [x] Schema / migration notes for preserve vs regenerate + verification
- [x] Log locations and common greps
- [x] On-call / paging path (Feishu + maintainer)
- [x] Linked from [docs/README.md](../README.md) ops section
