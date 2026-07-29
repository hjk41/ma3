# 25 — Continuous metrics, alerting, and internal SLOs (implementation plan)

> Status: **proposal** (design for GitHub issue #5 "ops: continuous metrics, alerting, and internal SLOs")
> Author: Fable (agent-drafted, pending product-owner review of open decisions D1–D6)
> Scope: runtime observability for the ma3 server. Not in scope: CI/test debt, public SLA wording (stays "no SLA today", per `CHANGELOG.md`; formal SLA is a v1.1+ item for paid tiers).

## 1. Background and current state

Today ma3 has **deploy-time verification only**:

- `GET /healthz` — liveness with version/commit/instance metadata (`code/server/app/api/routes_health.py`)
- MCP `ma3_doctor` / `ma3_whoami` — auth, DB, embedding, billing-schema checks; quota snapshot
- `deploy/common/verify_ma3_prod.sh` — one-shot public-URL checklist run after each preserve-mode deploy
- MCP responses may carry a `structuredContent.quota` / `storage_quota` block

There is **nothing continuous**: no metrics endpoint, no time series, no alerting, no SLO tracking. `docs/06-operations/monitoring-and-health.md` carries the TODO(v1.1) list this plan resolves.

Two deployment profiles must both be served:

- **SaaS (ma3.io)**: single instance (`ma3-v1-hk`), uvicorn bound to `127.0.0.1` behind Caddy, deployed via `deploy/deploy.sh` in preserve mode. We operate it; continuous monitoring is mandatory here.
- **Self-host (Compose)**: `deploy/self-host/docker-compose.yml`. Operators run it themselves; observability must be **optional, off by default, zero new required dependencies**.

## 2. Phased delivery

### Phase 0 — quick wins (shippable in days, no new server code paths)

Goal: know within minutes when ma3.io is down or degraded, using what already exists.

1. **External uptime probe (SaaS)**: a cron/systemd-timer script (new `deploy/observability/probe_ma3.sh`) on a machine *outside* the ma3.io host that every 60s:
   - `GET /healthz` and asserts `status=ok`, expected `instance_id`, no `dev_auth` feature;
   - POST `tools/call ma3_whoami` (anonymous) and asserts a valid MCP envelope;
   - optionally, with an ops API key, calls `ma3_doctor` every 15 min and asserts all checks `ok`.
   On N consecutive failures it notifies the chosen alert channel (see D4). This is effectively a scheduled, slimmed-down `verify_ma3_prod.sh`.
2. **Structured log field conventions**: document (in `monitoring-and-health.md`) the canonical JSON log fields — `ts`, `level`, `event`, `route`, `mcp_tool`, `principal_type`, `status`, `duration_ms`, `request_id`, `instance_id` — and ensure uvicorn access logs plus app logs land in journald/container logs where they can be grepped. No log-shipping stack yet.
3. **Doctor cron on the SaaS host**: a loopback `ma3_doctor` invocation every 15 min writing a one-line status to a local log, giving history for incident forensics even before Prometheus exists.

Phase 0 ships with zero changes to `code/server/` (except possibly log formatting) and no changes for self-hosters.

### Phase 1 — metrics endpoint and instrumentation

1. Add `prometheus-client` to `code/server/requirements.txt`.
2. New module `code/server/app/core/metrics.py` defining all metric objects (single source of truth for names/labels, § 4).
3. HTTP middleware in `app/main.py` recording request count / duration / in-flight per route template (route template, **not** raw path, to bound cardinality).
4. `GET /metrics` endpoint (new `app/api/routes_metrics.py`), gated by `MA3_METRICS_ENABLED` (default **on** — it is cheap and useful) and exposure-protected per D3 (loopback / not proxied by Caddy; token option for Compose users).
5. Domain instrumentation at the choke points: MCP tool dispatch (`app/services/mcp_tool_service.py`), search (`search_context_service.py`, `embedding_service.py`), auth (`api_key_service.py`, `routes_auth.py`, `local_auth_service.py`), write-buffer/publish (`buffer_service.py`, `report_store_service.py`), quota denials (`library_quota_service.py`, `org_quota_service.py`, `storage_quota_service.py`).
6. Unit tests: `/metrics` renders, counters increment on a fake request/tool call, label sets match this doc.
7. SaaS host: Prometheus (+ node_exporter) scraping `127.0.0.1:8000/metrics`, run from a small compose file in `deploy/observability/` (deployed manually, **not** through `deploy.sh` preserve flow — the app deploy stays untouched).

### Phase 2 — alerting

1. Alertmanager added to the SaaS observability compose; Phase 0 probe rewired as a Prometheus `blackbox_exporter` target (or kept as cron — D2/D4 dependent).
2. Alert rules file `deploy/observability/prometheus/alerts.yml` with the minimal set in § 6.
3. Runbook section in `monitoring-and-health.md`: for each alert, meaning + first three diagnostic commands (`ma3_doctor`, journalctl, `verify_ma3_prod.sh`).

### Phase 3 — SLO dashboard and docs

1. Prometheus recording rules for the SLIs in § 5 (`deploy/observability/prometheus/slo-rules.yml`).
2. One Grafana dashboard (JSON committed to `deploy/observability/grafana/ma3-slo.json`): SLI panels + 30-day error-budget burn.
3. Rewrite `docs/06-operations/monitoring-and-health.md` (+ `.zh.md`): endpoints, metric reference, alert runbook, internal SLOs, explicit "internal SLO ≠ public SLA" statement.
4. Optional `observability` profile in `deploy/self-host/docker-compose.yml` for Compose users (§ 7).

## 3. Stack recommendation

| Option | Pros | Cons |
|---|---|---|
| **A. Prometheus + `prometheus-client` pull (recommended)** | Boring, tiny dep, self-contained, standard for OSS self-hosters, no collector process, alerting/dashboards are commodity | Pull model needs a scraper; per-instance only (fine: one instance) |
| B. OpenTelemetry SDK + collector | Vendor-neutral traces+metrics+logs, future-proof | Heavy dep surface and config for a small team; needs a collector everywhere; self-hosters must run more infra; tracing is not the pain point today |
| C. Log-only + cron doctor | Zero new deps | No latency percentiles, no rate math, no dashboards; alert logic becomes bespoke shell; dead end for SLOs |

**Recommendation: A**, with C's cron-doctor as the Phase 0 stopgap (it is complementary, not competing). OTel can be revisited if ma3 becomes multi-service; metric names below are OTel-mappable later. Prefer hand-rolled ~50-line middleware over `prometheus-fastapi-instrumentator` to keep control of label sets (see D1).

## 4. Concrete metrics

All metrics prefixed `ma3_`. Cardinality rule: **no per-principal / per-org / per-library-id labels** on metrics (D6); per-tenant detail stays in structured logs and the DB.

### HTTP (middleware)

| Name | Type | Labels |
|---|---|---|
| `ma3_http_requests_total` | counter | `method`, `route` (template, e.g. `/mcp`, `/ui/home/`), `status` (class: `2xx`…`5xx`) |
| `ma3_http_request_duration_seconds` | histogram | `method`, `route` |
| `ma3_http_requests_in_flight` | gauge | — |
| `ma3_build_info` | gauge (=1) | `version`, `git_commit`, `instance_id` |

### MCP tools (dispatch in `mcp_tool_service.py`)

| Name | Type | Labels |
|---|---|---|
| `ma3_mcp_tool_calls_total` | counter | `tool` (e.g. `ma3_context`), `outcome` (`ok`, `error`, `auth_denied`, `invalid_args`, `quota_blocked`) |
| `ma3_mcp_tool_duration_seconds` | histogram | `tool` |

### Search / embedding

| Name | Type | Labels |
|---|---|---|
| `ma3_search_requests_total` | counter | `outcome` (`ok`, `empty`, `error`) |
| `ma3_search_duration_seconds` | histogram | `stage` (`embedding`, `db_query`, `total`) |
| `ma3_embedding_requests_total` | counter | `outcome` (`ok`, `error`, `timeout`) |

### Auth

| Name | Type | Labels |
|---|---|---|
| `ma3_auth_attempts_total` | counter | `method` (`api_key`, `oidc`, `local`), `outcome` (`ok`, `invalid`, `expired`, `revoked`) |

### Write-buffer / publish jobs

| Name | Type | Labels |
|---|---|---|
| `ma3_buffer_records` | gauge | `state` (`buffered`, `overdue`) — overdue = past `publish_at` but not yet published |
| `ma3_publish_actions_total` | counter | `action` (`auto_publish`, `manual_publish`, `patch`), `outcome` (`ok`, `error`) |
| `ma3_publish_lag_seconds` | gauge | — (age past `publish_at` of the oldest unpublished record; 0 when none) |

### Quotas

| Name | Type | Labels |
|---|---|---|
| `ma3_quota_denials_total` | counter | `quota_type` (`read`, `write`, `storage`, `org`) |
| `ma3_quota_warnings_total` | counter | `quota_type` (fired when a response carries a quota `warnings` block, e.g. 80% threshold) |

### DB (cheap, from pool)

| Name | Type | Labels |
|---|---|---|
| `ma3_db_pool_connections` | gauge | `state` (`in_use`, `idle`) |

## 5. Internal SLOs (explicitly NOT a public SLA)

Public posture is unchanged: community best-effort, **no customer SLA** (see `CHANGELOG.md`); these are internal targets to drive alerting and prioritization, and a dry run for a possible v1.1+ paid-tier SLA. Window is 30-day rolling unless noted; SLIs computed from Prometheus recording rules.

| # | Objective | SLI (measurement) | Target | Window |
|---|---|---|---|---|
| SLO-1 | API availability | share of `ma3_http_requests_total` on `/mcp` + `/healthz` + API routes that are non-5xx | ≥ 99.5% | 30d |
| SLO-2 | External reachability | blackbox/cron probe success against `https://ma3.io/healthz` from outside | ≥ 99.5% | 30d |
| SLO-3 | Retrieval latency | p95 of `ma3_mcp_tool_duration_seconds{tool="ma3_context"}` | ≤ 2.5 s | 30d |
| SLO-4 | Write acceptance | share of `ma3_mcp_tool_calls_total{tool=~"ma3_report|ma3_feedback"}` with outcome `ok` or a client-attributable outcome (`invalid_args`, `auth_denied`, `quota_blocked`) — i.e. non-server-fault | ≥ 99.9% | 30d |
| SLO-5 | Publish freshness | share of buffered records published within `publish_at` + 30 min (from `ma3_publish_lag_seconds` / publish counters) | ≥ 99% | 30d |

Error budget: when a 30d SLO is burning >2× budget rate, observability/reliability work preempts feature work — that is the whole point of making these internal-only first.

## 6. Alert rules (minimal starter set)

Severity: **page** = notify immediately on the D4 channel; **ticket** = next business day.

| Alert | Condition | Severity | Action |
|---|---|---|---|
| `Ma3InstanceDown` | external probe fails 3 consecutive times (≈3 min) | page | Runbook: SSH, `systemctl status`, journalctl, redeploy last-good |
| `Ma3High5xx` | 5xx ratio > 5% over 10 min (and >1 req/s) | page | Check recent deploy, DB, embedding backend via `ma3_doctor` |
| `Ma3DoctorFailing` | authed `ma3_doctor` reports any non-ok check for 15 min | page | Runbook per failing check (DB / embedding / billing schema) |
| `Ma3PublishLag` | `ma3_publish_lag_seconds` > 3600 for 30 min | ticket | Inspect buffer/publish job, `ma3_buffer_records{state="overdue"}` |
| `Ma3ContextSlow` | p95 `ma3_context` latency > 5 s over 30 min | ticket | Check embedding service and DB query plans |
| `Ma3QuotaDenialSpike` | `ma3_quota_denials_total` rate > 10× 7-day baseline for 1 h | ticket | Possible abuse or a mis-set quota; check logs for principal |
| `Ma3CertExpiry` | probe TLS cert expires < 14 days | ticket | Caddy should auto-renew; investigate why it didn't |

Deliberately excluded for now: per-route latency alerts, disk/CPU (covered by node_exporter defaults if enabled), log-volume anomaly detection.

## 7. Self-host vs SaaS

| Aspect | SaaS (ma3.io) | Self-host Compose |
|---|---|---|
| `/metrics` endpoint | On; loopback-only (Caddy does not proxy it) | On by default, protected per D3; operator may disable via `MA3_METRICS_ENABLED=0` |
| Prometheus/Alertmanager/Grafana | We run it (`deploy/observability/` compose on the ma3.io host) | **Optional** compose profile `observability` (`docker compose --profile observability up`); off by default |
| External uptime probe | Required (Phase 0), runs off-host | Not shipped; docs suggest Uptime Kuma / healthchecks.io pointing at `/healthz` |
| Alert channel | Team channel per D4 | Operator-configured; we only ship example Alertmanager config |
| SLOs | Tracked, reviewed monthly | Not applicable; dashboard JSON provided as convenience |
| Doctor cron | Yes (Phase 0) | Documented as an optional one-liner |

Hard requirement: a Compose user who ignores all of this gets exactly today's behavior — no new mandatory services, ports, or env vars.

## 8. Open decisions for the product owner

- **D1 — Instrumentation library.** (a) hand-rolled middleware + `prometheus-client`; (b) `prometheus-fastapi-instrumentator`; (c) OpenTelemetry SDK. **Recommend: (a)** — one small dep, full control of label cardinality, trivial to maintain.
- **D2 — Where the SaaS monitoring stack runs.** (a) same host as ma3.io via docker compose; (b) Grafana Cloud free tier (remote_write, hosted alerting); (c) separate small VM. **Recommend: (a)** for v1 simplicity, with the caveat that host-down also kills Prometheus — mitigated because the Phase 0 external probe (which must live off-host regardless) catches total outages; move to (b) if that dual setup annoys us.
- **D3 — `/metrics` exposure.** (a) bind-only: reachable on loopback, never proxied by Caddy; self-host docs say "scrape inside the compose network"; (b) bearer-token auth on the endpoint; (c) feature-flag off by default. **Recommend: (a)** with the `MA3_METRICS_ENABLED` flag kept as an escape hatch; add (b) later only if someone needs cross-network scraping.
- **D4 — Alert delivery channel.** (a) email; (b) Slack/Discord/webhook via Alertmanager; (c) GitHub issue auto-filed. **Recommend: (b)** webhook to the team channel for pages + (c) for tickets, so ticket-severity alerts leave a durable trail.
- **D5 — SLO tracking tooling.** (a) plain Prometheus recording rules + one Grafana dashboard; (b) generator like Sloth; (c) spreadsheet from monthly queries. **Recommend: (a)** — five SLOs do not justify a generator.
- **D6 — Metric cardinality policy.** (a) aggregate-only labels (no principal/org/library ids), per-tenant detail in logs; (b) allow `library_kind`-style coarse labels; (c) per-tenant metrics. **Recommend: (a)**, allowing (b) case-by-case; (c) is a cardinality time bomb on a single Prometheus.

## 9. Acceptance criteria for closing issue #5

- [ ] Phase 0: external probe running against ma3.io with a working alert path (verified by a forced failure drill); doctor cron logging on the host
- [ ] `GET /metrics` exposes all § 4 metrics with documented names/labels; gated per D3; unit tests cover render + increment + label sets
- [ ] MCP tool calls, search, auth, buffer/publish, and quota denials are instrumented at the service choke points (spot-checked in staging via curl → metric delta)
- [ ] Prometheus + Alertmanager running for SaaS with the § 6 rule set committed to git; each alert fired once in a drill or via `amtool`
- [ ] SLO recording rules + Grafana dashboard committed; 30-day panels render with live data
- [ ] `docs/06-operations/monitoring-and-health.md` (+ `.zh.md`) rewritten: TODO(v1.1) block removed, metric reference, alert runbook, SLO table, explicit "internal SLO, no public SLA" statement
- [ ] Self-host: optional `observability` compose profile + docs; default `docker compose up` behavior unchanged
- [ ] `verify_ma3_prod.sh` extended with a `/metrics` reachability check appropriate to D3 (e.g. asserts it is NOT publicly reachable through Caddy)
- [ ] `CHANGELOG.md` entry (support posture wording unchanged)

## 10. Files likely to touch

| Path | Change |
|---|---|
| `code/server/app/core/metrics.py` | **new** — metric definitions |
| `code/server/app/api/routes_metrics.py` | **new** — `/metrics` endpoint |
| `code/server/app/main.py` | HTTP middleware, router registration |
| `code/server/app/core/config.py` | `MA3_METRICS_ENABLED` (and token if D3=(b)) |
| `code/server/app/services/mcp_tool_service.py` | tool-call counters/histograms |
| `code/server/app/services/search_context_service.py`, `embedding_service.py` | search/embedding metrics |
| `code/server/app/services/buffer_service.py`, `report_store_service.py` | publish/buffer metrics |
| `code/server/app/services/library_quota_service.py`, `org_quota_service.py`, `storage_quota_service.py` | quota denial/warning counters |
| `code/server/app/services/api_key_service.py`, `app/api/routes_auth.py`, `local_auth_service.py` | auth attempt counters |
| `code/server/requirements.txt` | add `prometheus-client` |
| `code/server/tests/unit/test_metrics.py` | **new** |
| `deploy/observability/` | **new** — probe script, compose, `prometheus/{prometheus.yml,alerts.yml,slo-rules.yml}`, `grafana/ma3-slo.json`, README |
| `deploy/self-host/docker-compose.yml` | optional `observability` profile |
| `deploy/common/verify_ma3_prod.sh` | `/metrics` exposure check |
| `docs/06-operations/monitoring-and-health.md` (+ `.zh.md`) | rewrite per Phase 3 |
| `CHANGELOG.md` | Unreleased entry |
