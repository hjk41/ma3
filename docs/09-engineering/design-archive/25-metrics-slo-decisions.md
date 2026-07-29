# 25 — Continuous metrics, alerting, and internal SLOs (decision summary)

> Status: **ratified 2026-07-29** (product owner: all options **A**).  
> Issue: https://github.com/hjk41/ma3/issues/5  
> This summary is the contractual decision record for implementation. The Fable plan and GPT-5.6 review are historical drafts.

## Background

ma3 had deploy-time verification only (`healthz`, `ma3_doctor`, `verify_ma3_prod.sh`) and no continuous metrics, alerts, or internal SLOs. A phased plan was drafted and reviewed; two blocking design faults were fixed by the decisions below (enforceable `/metrics` exposure; defer SLOs that lack measurements).

## Ratified decisions

| ID | Topic | Choice | Meaning |
|----|-------|--------|---------|
| **D-exp** | Metrics exposure | **A** | SaaS: `/metrics` loopback / not proxied by Caddy. **Self-host: metrics disabled by default** (`MA3_METRICS_ENABLED=0`). |
| **D-place** | Monitoring placement | **A** | Same-host Prometheus + persistent volumes for SaaS, plus a **mandatory off-host** paging probe. |
| **D-alert** | Paging workflow | **A** | One owned webhook/paging channel; **ticket-severity items are created manually** (no auto GitHub issues). |
| **D-slo** | Internal reliability policy | **A** | Ship **SLO-1–SLO-3** first (API availability, external reachability, `ma3_context` p95). Defer write-acceptance and publish-freshness SLOs until measurements exist. |

Implementation defaults (accepted with the plan, not re-voted):

- Instrumentation: `prometheus-client` + small hand-rolled middleware (not OTel).
- Cardinality: aggregate labels only (no principal/org/library ids).
- SLO tooling: Prometheus recording rules + one Grafana dashboard (later phase).

## Explicit non-goals / deferred

- Public / contractual SLA (unchanged: community best-effort).
- SLO-4 (write acceptance) and SLO-5 (publish freshness) until publish-delay / outcome metrics exist.
- Auto-filing GitHub issues from Alertmanager.
- Default-on `/metrics` for Compose self-host.
- Full structured-log rewrite in Phase 0 (document conventions only).

## Landing locations

| Artifact | Path |
|----------|------|
| Off-host probe (Phase 0) | `deploy/observability/probe_ma3.sh` |
| Ops docs | `docs/06-operations/monitoring-and-health.md` (+ `.zh.md`) |
| Later: metrics module | `code/server/app/core/metrics.py`, `routes_metrics.py` |
| Later: SaaS scrape stack | `deploy/observability/` compose + Prometheus rules |

## Historical drafts

| Draft | Role |
|-------|------|
| [25-metrics-slo-plan-fable.md](25-metrics-slo-plan-fable.md) | Implementation plan (Fable) |
| [25-metrics-slo-review-gpt56.md](25-metrics-slo-review-gpt56.md) | Review, REQUEST-CHANGES (GPT-5.6) |
