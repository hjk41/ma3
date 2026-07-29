# Review — Metrics, Alerting, and Internal SLO Plan

> Review target: `25-metrics-slo-plan-fable.md` (GitHub issue #5)  
> Evidence checked: current monitoring documentation, FastAPI route mounting, repository search, and deployment layouts.  
> Note: ma3 MCP was unavailable in this review environment, so this review is based on repository evidence only.

## Verdict

**REQUEST-CHANGES**

## Summary

The proposal has a sound incremental shape: an external probe first, then Prometheus-compatible application metrics, alerting, and finally SLO reporting. It correctly distinguishes the operated SaaS instance from optional self-host observability, and its aggregate-label policy is appropriate. However, the recommended `/metrics` exposure model cannot be enforced by a route inside the existing single FastAPI listener and would expose metrics publicly for the current Compose default. In addition, the proposed publish-freshness metrics cannot calculate SLO-5 as written. Resolve those two design inconsistencies, define the SLI/error-budget queries precisely, and reduce Phase 1 before implementation.

## What is strong

- The plan starts with an independent, off-host availability signal. That is the highest-value protection against a complete host, reverse-proxy, DNS, or certificate failure.
- Prometheus pull metrics plus a small explicit `prometheus-client` integration is proportionate for a single-process, single-instance service. The repository currently has no `/metrics`, Prometheus client, or Prometheus deployment, so this is a clean addition rather than competing instrumentation.
- Avoiding principal, organization, and library identifiers in labels is the right default. The listed HTTP, MCP-tool, outcome, and coarse quota labels are bounded and operationally useful.
- The planned route-template label is preferable to raw URLs. `app/main.py` centrally constructs the FastAPI app and includes routers, so it is a suitable location for shared HTTP instrumentation.
- The plan is honest that internal objectives are not a customer-facing SLA and keeps the self-host stack optional.
- Running a small same-host Prometheus stack is a reasonable early operational compromise because the independent probe covers the main blind spot: loss of that host.

## Risks / gaps

### Blocking

1. **D3's recommended “bind-only” protection is not implementable by a FastAPI route alone.** The current application has one Uvicorn listener; `app.include_router(...)` only chooses URL paths, not network bindings. SaaS preserve deployments can bind Uvicorn to `127.0.0.1`, but the current self-host Compose file publishes `"${MA3_PORT:-8000}:8000"` and the container listens on `0.0.0.0`. Adding `/metrics` with `MA3_METRICS_ENABLED` default-on therefore makes it publicly reachable on a typical self-host installation. “Caddy does not proxy it” protects only a particular SaaS proxy configuration, not the listener or Compose deployment.

   The design must choose an enforceable model before implementation: default metrics off for self-host; authenticated metrics; a dedicated metrics listener/sidecar with an internal-only Compose network; or a changed default host-port binding. The public-reachability verification must test the selected model, rather than merely assume Caddy configuration.

2. **SLO-5 cannot be computed from the proposed metrics.** `ma3_publish_lag_seconds` is one aggregate gauge for the oldest currently overdue record, and `ma3_publish_actions_total` has no “published within 30 minutes of `publish_at`” label or observation. Neither permits calculating the percentage of buffered records published within the target. Emit a publish-delay histogram or counter at each publish transition (for example, `ma3_buffer_publish_delay_seconds`), define the denominator explicitly, and retain the lag gauge only as an operational alert signal.

3. **The SLI definitions are not yet executable PromQL contracts.** Each SLO needs an exact numerator, denominator, exclusion policy, zero-traffic behavior, and recording-rule/query window. In particular, “non-5xx” needs a defined eligible route set and treatment of cancellations, 4xx, 429, and failed requests before an HTTP response exists; p95 must be calculated from histogram buckets over a rate window, not from an aggregate percentile; and SLO-4 must define which tool outcomes are server-attributable. Without these definitions, the dashboard, error budget, and alert behavior can disagree.

### Non-blocking

1. **Phase 0 has an operational ownership gap.** A script committed under `deploy/observability/` does not establish an independent execution location, timer, secret storage for the optional doctor key, failure persistence, or notification ownership. Supply a documented systemd timer/service (or selected external monitor configuration) and a failure drill.

2. **The plan overstates “zero server code paths” for structured logs.** Uvicorn access logs do not automatically contain the proposed application fields such as `request_id`, `mcp_tool`, or `principal_type`. Define which fields are emitted by access logging versus application events, how a request ID is generated/propagated, and which events are intentionally absent.

3. **HTTP route labeling needs a fallback rule.** Use the matched FastAPI route template after routing; for 404s, malformed requests, redirects, and exceptions before a route is resolved, use a finite value such as `unmatched` or `internal`, never `request.url.path`.

4. **Metric lifecycle and process model are unspecified.** Define registry ownership, duplicate-registration behavior in tests/reloads, histogram buckets, and the supported Uvicorn worker count. The stated one-instance assumption is sufficient only while the service remains one process; Prometheus Python multiprocess mode needs explicit treatment if workers are ever enabled.

5. **Several alerts need guardrails.** Add an absolute request floor and no-data semantics to ratio/baseline alerts; a 10× seven-day quota baseline is unstable when the baseline is zero or tiny. Alert rules should also include short/long burn-rate windows for availability SLOs rather than only an end-state 30-day panel.

6. **Storage and retention are omitted.** Same-host Prometheus needs a persistent volume, retention duration/size, backup/restore expectations, and a resource budget. Grafana and Alertmanager state/config persistence should be explicit as well.

## Per-decision review

### D1 — Instrumentation library

**Agree with recommendation (A), with a boundary.** Use `prometheus-client` plus a small local metrics module and middleware. Avoid a broad auto-instrumentator because this service needs precise route fallback, outcome taxonomy, and cardinality control. The human decision is not really the library; it is whether tracing is needed now, and repository evidence does not justify OTel in this issue.

### D2 — SaaS monitoring-stack location

**Agree with recommendation (A) for the first release.** Same-host Prometheus is adequate if the off-host probe is an independently operated paging path and Prometheus data/state uses persistent volumes. A separate VM or hosted service buys monitoring continuity and history during host loss, but is not necessary to obtain the first reliable outage signal. Revisit B/C if retention, multi-instance deployment, or incident requirements grow.

### D3 — `/metrics` exposure

**Do not agree with recommendation (A) as currently described.** “Loopback only” is a listener/deployment property, not a FastAPI route property; current self-host Compose publishes the same listener publicly. Prefer a split policy: SaaS may use an unproxied loopback listener, while self-host must either default metrics disabled or use an authenticated/internal-network metrics endpoint. If a common endpoint is required, bearer authentication plus explicit documentation is more enforceable than the proposed route-only bind claim.

### D4 — Alert delivery channel

**Partially agree with recommendation (B + C).** Webhook delivery is appropriate for pages and durable tickets can be useful, but auto-filing GitHub issues is often noisy and lacks an acknowledgement/escalation model. Start with one owned paging/webhook channel and Alertmanager grouping/inhibition; add GitHub ticket creation only after the team defines deduplication, ownership, and closure rules.

### D5 — SLO tracking tooling

**Agree with recommendation (A), after the SLI contracts are fixed.** Plain recording rules and one dashboard are easier to review for five objectives. Sloth is not needed until the team needs standardized multi-window burn-rate rule generation across multiple services.

### D6 — Metric cardinality policy

**Agree with recommendation (A), retaining the stated narrow B exception.** Aggregate labels are correct for the present deployment. Permit a documented allowlist of bounded dimensions (for example, `library_kind`) only after specifying values and an upper bound; do not make case-by-case additions without that registry.

## Missing decisions

### D7 — Enforceable metrics network model

Choose the concrete exposure model separately for SaaS and self-host, including listener bindings, Docker networks/ports, authentication if any, and the public/inside-network verification tests. This is required to make D3 real.

### D8 — SLI and error-budget specification

Approve an appendix of exact PromQL/recording rules, eligible traffic, outcome classification, zero-traffic semantics, and short/long burn-rate alert windows. This is required before calling the targets SLOs.

### D9 — Phase-0 probe operations

Choose the off-host executor, timer/monitoring service, credential source, alert owner, retry/backoff, and forced-failure drill. A repository script alone is not an independently running monitor.

### D10 — Data retention and resource budget

Set Prometheus/Alertmanager/Grafana persistent storage, retention, expected scrape interval, disk cap, and upgrade/backup responsibility. This determines whether the proposed 30-day objectives can actually be observed.

### D11 — Metric schema governance

Approve the fixed label vocabulary, route fallback behavior, histogram buckets, registry/test pattern, and policy for future Uvicorn workers. This prevents accidental schema/cardinality changes after the first release.

## Scope cuts

### Phase 0

- Keep only the external `/healthz` probe plus anonymous MCP discovery/`ma3_whoami` envelope check, an owned notification path, and a forced-failure drill.
- Make the authenticated doctor check a separate, lower-frequency best-effort diagnostic until secret handling and alert ownership are decided.
- Document existing logs first; defer a full canonical structured-logging implementation and request-ID propagation unless incident evidence shows they are immediately needed.

### Phase 1

- Deliver the secure metrics exposure model, build info, HTTP request/error/duration/in-flight metrics, MCP tool call/duration metrics, and Prometheus scraping with persistent storage.
- Instrument search/embedding only if `ma3_context` latency cannot already be diagnosed from MCP duration; defer auth, quota, buffer/publish, DB-pool, Grafana, and the optional self-host observability profile.
- Add SLO-1, SLO-2, and SLO-3 only after D8. Defer SLO-4 and SLO-5 until their outcome and publish-delay measurements exist.

## Revised decision list for the product owner

Only these items require a product-owner call; the implementation choices in D1, D5, and D6 can follow the recommendations above.

1. **Metrics exposure model (D3/D7)**
   - **A.** SaaS loopback-only endpoint; self-host metrics disabled by default.
   - **B.** SaaS loopback-only endpoint; self-host endpoint enabled with bearer-token authentication.
   - **C.** Dedicated internal-only metrics listener/network for both profiles.
   - **Stake:** Determines whether metrics can leak service topology/usage data from a default self-host deployment.

2. **Monitoring placement and durability (D2/D10)**
   - **A.** Same-host Prometheus with persistent local volumes plus mandatory off-host paging probe.
   - **B.** Hosted monitoring/alerting with remote write.
   - **C.** Separate monitoring VM.
   - **Stake:** Balances operational cost against visibility and history during a total application-host outage.

3. **Paging and ticketing workflow (D4/D9)**
   - **A.** One owned webhook/paging channel with Alertmanager grouping and manual ticket creation.
   - **B.** Webhook paging plus auto-created GitHub tickets for ticket alerts.
   - **C.** Email-only notifications.
   - **Stake:** Sets who is expected to respond and whether lower-severity alerts create durable work automatically.

4. **Internal reliability policy (D8)**
   - **A.** Approve SLO-1–SLO-3 first, with explicit PromQL and burn-rate policy; defer write/publish SLOs.
   - **B.** Approve all five only after adding the required publish-delay and outcome measurements.
   - **C.** Use alerts/dashboards only for now; defer formal error budgets.
   - **Stake:** Determines whether error-budget burn can preempt feature work and which measurements must ship now.
