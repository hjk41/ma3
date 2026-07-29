# Observability (Phase 0+)

> Decision record: [25-metrics-slo-decisions.md](../../docs/09-engineering/design-archive/25-metrics-slo-decisions.md)  
> Ops doc: [monitoring-and-health.md](../../docs/06-operations/monitoring-and-health.md)

## Ratified defaults (2026-07-29)

| Topic | Choice |
|-------|--------|
| Metrics exposure | SaaS loopback / not public; **self-host metrics off by default** |
| Monitoring stack | Same-host Prometheus later + **mandatory off-host probe now** |
| Alerts | One webhook channel; tickets created manually |
| Internal SLOs | SLO-1–3 first (availability, reachability, `ma3_context` latency) |

## Phase 0 — off-host probe

Script: [`probe_ma3.sh`](probe_ma3.sh)

Every ~60s from a host **other than** the ma3.io app server:

1. `GET /healthz` — `status=ok`, expected `instance_id` / `public_base_url`, no `dev_auth`
2. Anonymous MCP `ma3_whoami` — valid JSON-RPC result envelope
3. Optional: authed `ma3_doctor` when `MA3_PROBE_DOCTOR=1` and `MA3_API_KEY` is set

After N consecutive failures (default 3), POST a JSON payload to `MA3_PROBE_WEBHOOK_URL`. On recovery after a notified streak, POST `ma3_probe_recover`.

### Quick test

```bash
export MA3_BASE_URL=https://ma3.io
export MA3_EXPECT_INSTANCE_ID=ma3-v1-hk
export MA3_PROBE_DRY_RUN=1
# optional: export MA3_PROBE_WEBHOOK_URL=https://hooks.example/…
bash deploy/observability/probe_ma3.sh
```

### systemd (example)

Copy and edit env in `/etc/ma3/probe.env` (not in git; contains webhook URL / optional API key):

```bash
# /etc/ma3/probe.env
MA3_BASE_URL=https://ma3.io
MA3_EXPECT_INSTANCE_ID=ma3-v1-hk
MA3_PROBE_WEBHOOK_URL=https://hooks.example/ma3
# MA3_PROBE_DOCTOR=1
# MA3_API_KEY=ma3k_…
```

Unit files (examples under `systemd/`):

```bash
sudo cp deploy/observability/systemd/ma3-probe.service /etc/systemd/system/
sudo cp deploy/observability/systemd/ma3-probe.timer /etc/systemd/system/
# point ExecStart at a checked-out clone or install probe_ma3.sh to /usr/local/bin
sudo systemctl daemon-reload
sudo systemctl enable --now ma3-probe.timer
```

### Forced-failure drill

1. Point `MA3_BASE_URL` at a closed port or wrong host.
2. Run the probe ≥ `MA3_PROBE_FAIL_THRESHOLD` times.
3. Confirm webhook receives `ma3_probe_fail`.
4. Restore URL; confirm `ma3_probe_recover`.

### Host 202 (LAN operator laptop) — live install

This machine (`192.168.31.202`) runs the off-host probe for SaaS `https://ma3.io`:

| Unit | Role |
|------|------|
| `ma3-alert-sink.service` | Local webhook on `127.0.0.1:8787` → `/var/log/ma3/probe-alerts.jsonl` |
| `ma3-probe.timer` | Every ~60s runs `ma3-probe.service` |
| `/etc/ma3/probe.env` | Target URL / instance / webhook (not in git) |
| `/usr/local/bin/ma3-probe.sh` | Installed copy of `probe_ma3.sh` |

Useful commands:

```bash
systemctl status ma3-probe.timer ma3-alert-sink.service
journalctl -u ma3-probe.service -n 50
sudo tail -f /var/log/ma3/probe-alerts.jsonl
```

To switch the webhook to Slack/Discord/Feishu later, change only `MA3_PROBE_WEBHOOK_URL` in `/etc/ma3/probe.env`.

## Later phases (not in this directory yet)

- Phase 1: `GET /metrics` (SaaS loopback; self-host `MA3_METRICS_ENABLED=0` by default) + Prometheus scrape compose
- Phase 2: Alertmanager rules
- Phase 3: SLO recording rules + Grafana for SLO-1–3
