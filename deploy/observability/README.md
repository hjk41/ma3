# Observability (Phase 0+)

> Decision record: [25-metrics-slo-decisions.md](../../docs/09-engineering/design-archive/25-metrics-slo-decisions.md)  
> Ops doc: [monitoring-and-health.md](../../docs/06-operations/monitoring-and-health.md)

## Ratified defaults (2026-07-29)

| Topic | Choice |
|-------|--------|
| Metrics exposure | SaaS loopback / not public; **self-host metrics off by default** |
| App-host stack | Prometheus / Alertmanager / Grafana on ma3.io (loopback only) |
| Reachability paging | **Off-host probe on host 200** (`hct-nas`) → Feishu |
| Aliyun managed Prom | **Do not** `remote_write` — TSDB stays on the app host |
| Internal SLOs | App-host Prom + Grafana; probe covers public reachability |

## Phase 0 — off-host probe

Script: [`probe_ma3.py`](probe_ma3.py) (cross-platform; [`probe_ma3.sh`](probe_ma3.sh) is a thin launcher)

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
# or: python3 deploy/observability/probe_ma3.py
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

### Windows NAS (host 200) — **production probe**

See **[windows/DEPLOYMENT.md](windows/DEPLOYMENT.md)** for the full agent debug map (paths, tasks, redeploy, triage).

Redeploy from dev machine:

```powershell
powershell -ExecutionPolicy Bypass -File deploy/observability/windows/deploy-host-200.ps1
```

### Windows dev laptop (optional local install)

Run on a machine **other than** the ma3.io app server (Python 3 only; no WSL):

```powershell
powershell -ExecutionPolicy Bypass -File deploy/observability/windows/install_probe.ps1
```

| Component | Role |
|-----------|------|
| Scheduled task `ma3-probe` | Every 60s: `probe_ma3.py` via hidden launcher |
| Startup `ma3-alert-sink.vbs` | `127.0.0.1:8787` sink → Feishu |
| `%USERPROFILE%\.ma3\probe\probe.env` | Target URL / instance / webhook (not in git) |
| `%USERPROFILE%\.ma3\probe\feishu.env` | Feishu app credentials (not in git) |

Useful commands:

```powershell
schtasks /Query /TN ma3-probe /FO LIST /V
powershell -File $env:USERPROFILE\.ma3\probe\run_probe.ps1
Get-Content $env:USERPROFILE\.ma3\probe\logs\probe-alerts.jsonl -Tail 20
```

### Host 202 (LAN operator laptop) — legacy Linux install

Previously `192.168.31.202` ran the off-host probe via systemd. Prefer the Windows setup above on your daily laptop when 202 is powered off.

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

## Phase 1 — application metrics + app-host Prom/Grafana

`MA3_METRICS_ENABLED=1` on the app host. Public Caddy must **not** proxy `/metrics` (see `caddy-metrics-block.snippet`).

On the **ma3.io app host**, start the stack (host network, loopback UI):

```bash
# as root / deploy user on 47.84.49.254
cd /opt/ma3_deploy
bash code/deploy/observability/run_saas_stack.sh
```

| Loopback port (app host) | Service |
|---------------|---------|
| `:9090` | Prometheus (file_sd → live blue-green uvicorn) |
| `:9093` | Alertmanager → local Feishu sink `:8787` |
| `:3000` | Grafana |
| `:8787` | Webhook sink → Feishu |

Scrape target is `data/bluegreen/prometheus-targets.json`, rewritten on each blue-green cutover so Prom follows `:8000` / `:8001`. Access UI via SSH tunnel, e.g. `ssh -L 3000:127.0.0.1:3000 …`.

**Do not** configure Prometheus `remote_write` to Aliyun-managed Prometheus (or any external TSDB) unless that is an explicit future decision.

## Phase 2 / 3 — reachability + optional laptop lab

Public reachability paging remains **Phase 0 probe on host 202** (`ma3-probe.timer` → Feishu). That path is independent of app-host Prom.

Optional laptop lab (not required for production):

```bash
bash deploy/observability/run_local_stack.sh
```
