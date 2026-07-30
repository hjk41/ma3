# Monitoring and Health Checks

> Chinese version: [monitoring-and-health.zh.md](monitoring-and-health.zh.md)

> **Decision record (ratified 2026-07-29):** [25-metrics-slo-decisions.md](../09-engineering/design-archive/25-metrics-slo-decisions.md) · Issue [#5](https://github.com/hjk41/ma3/issues/5)

## Posture

- **Public SLA:** none today (community best-effort). See root `CHANGELOG.md`.
- **Internal SLOs:** operational targets for the operated SaaS instance (`ma3.io`). They do **not** create a customer commitment.
- **Self-host:** observability is optional; default Compose behavior stays unchanged. Application metrics will be **off by default** when Phase 1 ships.

## Existing endpoints / tools

| Endpoint / tool | Purpose |
|-------------|------|
| `GET /healthz` | Liveness; version, commit, instance, features |
| MCP `ma3_doctor` | Auth, DB, embedding, legacy keys, billing schema |
| MCP `ma3_whoami` | Key / principal / quota snapshot |
| `deploy/common/verify_ma3_prod.sh` | One-shot public URL checklist after each production deploy |

## Phase 0 — continuous off-host probe (shipped)

Script and install notes: [`deploy/observability/`](../../deploy/observability/README.md).

| Check | Cadence | Notes |
|-------|---------|------|
| `GET /healthz` | ~60s | Assert `status=ok`, expected `instance_id` / `public_base_url`, no `dev_auth` |
| Anonymous `ma3_whoami` | ~60s | Valid MCP result envelope |
| Authed `ma3_doctor` | optional | Enable with `MA3_PROBE_DOCTOR=1` + `MA3_API_KEY` |

**Alerting (decision A):** on N consecutive failures (default 3), POST JSON to `MA3_PROBE_WEBHOOK_URL`. Ticket-severity follow-ups are **manual** (no auto-filed GitHub issues). Run a forced-failure drill when enabling a new webhook.

**Ownership:** the probe must run on a host **other than** the ma3.io application server. Env file (webhook URL, optional API key) stays off git (e.g. `/etc/ma3/probe.env`).

## Internal SLOs (SaaS) — first tranche

| # | Objective | Measurement (intent) | Target | Window |
|---|---|---|---|---|
| SLO-1 | API availability | Non-5xx share on `/mcp`, `/healthz`, and `/api/*` | ≥ 99.5% | 30d |
| SLO-2 | External reachability | Off-host probe success rate against public `/healthz` (+ whoami) | ≥ 99.5% | 30d |
| SLO-3 | Retrieval latency | p95 of `ma3_context` tool duration | ≤ 2.5 s | 30d |

Exact PromQL recording rules ship with Phase 1–3. **Deferred:** write-acceptance and publish-freshness SLOs until the required metrics exist.

## Phase 1 — application metrics

| Item | Policy |
|------|--------|
| Library | `prometheus-client` + hand-rolled middleware |
| Endpoint | `GET /metrics` when `MA3_METRICS_ENABLED=1` |
| Self-host default | **OFF** (`MA3_METRICS_ENABLED` unset/0) |
| SaaS | Enable on loopback uvicorn; **do not** proxy `/metrics` via Caddy |
| Series | `ma3_http_*`, `ma3_mcp_tool_*`, `ma3_build_info` |

App-host `/metrics` stays loopback-only for manual inspection. `verify_ma3_prod.sh` asserts the **public** URL does not serve Prometheus exposition text at `/metrics`.

**Do not run Prometheus on the Aliyun app host.** Production reachability alerts are the off-host probe on the operator laptop (host 202).

## Phase 2 — alerting (operator laptop)

| Item | Location |
|------|----------|
| Production channel | `ma3-probe.timer` → `ma3-alert-sink` → Feishu (`/etc/ma3/feishu.env`) |
| Optional lab rules | `deploy/observability/prometheus/alerts.yml` via `run_local_stack.sh` (local only) |
| Ticket follow-up | **manual** |

Retired on app host: `Ma3ScrapeDown` / `Ma3AvailabilityFastBurn` from same-host Prometheus (caused deploy-related false pages).

## Phase 3 — optional local Grafana lab

Internal SLO dashboards remain available as a **local lab** (`bash deploy/observability/run_local_stack.sh` on the operator machine). They are not the SaaS paging path.

| Port (loopback, local lab) | Service |
|----------------------|---------|
| `:9090` | Prometheus (optional) |
| `:9093` | Alertmanager (optional) |
| `:3000` | Grafana (optional) |
| `:8787` | Feishu webhook sink (probe) |

## Log field conventions (document first)

Prefer these keys when adding structured application logs (Phase 0 does **not** require a full access-log rewrite):

`ts`, `level`, `event`, `route`, `mcp_tool`, `principal_type`, `status`, `duration_ms`, `request_id`, `instance_id`

Do **not** put secrets or raw API keys in logs. Per-tenant detail stays in logs/DB; metrics stay aggregate-only (no principal/org/library id labels).

## Roadmap on this issue

| Phase | Status | Deliverable |
|-------|--------|-------------|
| 0 | **Done** (host 202) | Off-host probe + webhook/Feishu + docs |
| 1 | **Done** (ma3.io) | `/metrics`, HTTP + MCP series, Prometheus scrape |
| 2 | **Done** | Alertmanager + Feishu webhook + starter alerts |
| 3 | **Done** | SLO-1–3 recording rules + Grafana dashboard |

## Doctor target checks (unchanged intent)

- `anonymous_mcp_enabled: false` for Community record reads without a key
- `api_keys_table: ok`
- `auth_admin_configured: ok` (when Authing/OIDC is on)
- `billing_schema_ok` / `usage_rollup_lag` (when billing phases apply)
- `legacy_env_writer_keys: deprecated` if still set
