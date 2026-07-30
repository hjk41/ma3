# Observability (Phase 0+)

> Decision record: [25-metrics-slo-decisions.md](../../docs/09-engineering/design-archive/25-metrics-slo-decisions.md)  
> Ops doc: [monitoring-and-health.md](../../docs/06-operations/monitoring-and-health.md)

## Ratified defaults (2026-07-29)

| Topic | Choice |
|-------|--------|
| Metrics exposure | SaaS loopback / not public; **self-host metrics off by default** |
| Monitoring stack | **Off-host probe on operator laptop** (not on Aliyun app host) |
| Alerts | Probe → local Feishu webhook; tickets created manually |
| Internal SLOs | Reachability via probe; app-metrics Prom stack is optional/local-lab only |

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
| `ma3-alert-sink.service` | Local webhook on `127.0.0.1:8787` → `/var/log/ma3/probe-alerts.jsonl` (+ optional Feishu forward) |
| `ma3-probe.timer` | Every ~60s runs `ma3-probe.service` |
| `/etc/ma3/probe.env` | Target URL / instance / webhook (not in git) |
| `/etc/ma3/feishu.env` | `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_CHAT_ID(S)` (not in git) |
| `/usr/local/bin/ma3-probe.sh` | Installed copy of `probe_ma3.sh` |

Useful commands:

```bash
systemctl status ma3-probe.timer ma3-alert-sink.service
journalctl -u ma3-probe.service -n 50
sudo tail -f /var/log/ma3/probe-alerts.jsonl
```

### Feishu (Open API app)

Probe still POSTs to `MA3_PROBE_WEBHOOK_URL=http://127.0.0.1:8787/`. The sink forwards to Feishu when `/etc/ma3/feishu.env` is present:

```bash
FEISHU_APP_ID=cli_...
FEISHU_APP_SECRET=...
FEISHU_CHAT_ID=oc_...          # primary
# optional: FEISHU_CHAT_IDS=oc_a,oc_b
```

List chats the bot can message (after `tenant_access_token`):

```bash
curl -s 'https://open.feishu.cn/open-apis/im/v1/chats?page_size=50' \
  -H "Authorization: Bearer $TOKEN"
```

Manual test:

```bash
curl -s -X POST http://127.0.0.1:8787/ -H 'Content-Type: application/json' \
  -d '{"event":"ma3_probe_fail","base_url":"https://ma3.io","instance_id":"ma3-v1-hk","detail":"test","ts":"…"}'
```

## Phase 1 — application metrics (optional)

`MA3_METRICS_ENABLED=1` may stay on for manual loopback curl on the app host. Public Caddy must **not** proxy `/metrics` (see `caddy-metrics-block.snippet`).

**Do not run Prometheus / Alertmanager / Grafana on the Aliyun ma3.io host.**  
That stack caused false `Ma3AvailabilityFastBurn` noise after blue-green and is retired there.  
`run_saas_stack.sh` now refuses to start on the app host.

## Phase 2 / 3 — optional local lab stack

SaaS production alerts = **Phase 0 probe on host 202** only (`ma3-probe.timer` → `ma3-alert-sink` → Feishu).

If you want a local Prometheus/Grafana lab on the **operator laptop** (not the app host):

```bash
bash deploy/observability/run_local_stack.sh
```

| Loopback port (local only) | Service |
|---------------|---------|
| `:9090` | Prometheus (optional lab) |
| `:9093` | Alertmanager → `http://127.0.0.1:8787/alertmanager` |
| `:3000` | Grafana |
| `:8787` | Webhook sink → Feishu (already used by the probe) |
