# ma3 off-host probe — Windows deployment reference

> **For agents:** this file is the canonical map for debugging production reachability paging.
> Secrets (`feishu.env`) are **not** in git.

## Current production layout (2026-08)

| Role | Host | Notes |
|------|------|-------|
| **Off-host probe (Phase 0)** | `192.168.31.200` (`hct-nas`) | Windows NAS, always on |
| **App metrics / SLO alerts (Phase 2)** | `47.84.49.254` (`ma3.io`) | Prometheus + Alertmanager on app host |
| **Legacy probe host** | `192.168.31.202` | Retired (systemd); do not use |
| **Dev laptop** | local Windows | Does **not** run `ma3-probe` |

SSH from dev machine:

```text
hct@192.168.31.200    # probe host (Windows)
root@47.84.49.254       # ma3.io app host (Linux)
```

`~/.ssh/config` aliases: `192.168.31.200`, `ma3-prod`.

### Local dev machine — boot VBS error cleanup

If the dev laptop shows a **Windows Script Host** error at logon mentioning `ma3-alert-sink.vbs`:

1. Delete `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ma3-alert-sink.vbs` (early installer wrote malformed VBS with broken `\"` escaping).
2. Optional: `schtasks /Delete /TN ma3-probe /F` and `schtasks /Delete /TN ma3-alert-sink /F` if tasks remain.
3. Probe production runs on **host 200 only** — local machine should have no Startup VBS and no `ma3-probe` task.

---

## Host 200 — live install

### Machine

| Field | Value |
|-------|-------|
| IP | `192.168.31.200` |
| Hostname | `hct-nas` |
| OS | Windows 10 (`10.0.22631`) |
| SSH user | `hct` |
| Python | `C:\python3\python.exe` |

### Paths on host 200

| Path | Purpose |
|------|---------|
| `C:\Users\hct\.ma3\probe\` | **Runtime root** (installed files, env, logs, state) |
| `C:\Users\hct\.ma3\probe\probe.env` | Probe target + webhook (no secrets except optional API key) |
| `C:\Users\hct\.ma3\probe\feishu.env` | Feishu app credentials (**not in git**) |
| `C:\Users\hct\.ma3\probe\probe_ma3.py` | Cross-platform probe logic |
| `C:\Users\hct\.ma3\probe\local_webhook_sink.py` | `127.0.0.1:8787` → Feishu |
| `C:\Users\hct\.ma3\probe\run_probe.ps1` | Wrapper (loads env, starts sink, runs Python probe) |
| `C:\Users\hct\.ma3\probe\run_probe_hidden.vbs` | Hidden launcher for scheduled task |
| `C:\Users\hct\.ma3\probe\state\` | Consecutive-fail counter + notified flag |
| `C:\Users\hct\.ma3\probe\logs\probe.log` | Aggregated probe output |
| `C:\Users\hct\.ma3\probe\logs\probe-alerts.jsonl` | Webhook sink log (incl. Alertmanager forwards if any) |
| `C:\Users\hct\ma3-obs-deploy\` | Staging copy of repo scripts (safe to overwrite on redeploy) |

### Scheduled tasks (host 200)

| Task | Schedule | Command |
|------|----------|---------|
| `ma3-probe` | Every 1 minute | `wscript.exe C:\Users\hct\.ma3\probe\run_probe_hidden.vbs` |
| `ma3-alert-sink` | At logon (`hct`) | Hidden PowerShell → `start_sink.ps1` |

`run_probe.ps1` also calls `start_sink.ps1` each minute, so the sink recovers within 60s even if the logon task did not run.

### probe.env (host 200)

Template in repo: [`probe.env.host200`](probe.env.host200)

```ini
MA3_BASE_URL=https://ma3.io
MA3_EXPECT_INSTANCE_ID=ma3-v1-hk
MA3_EXPECT_PUBLIC_BASE_URL=https://ma3.io
MA3_PROBE_FAIL_THRESHOLD=3
MA3_PROBE_WEBHOOK_URL=http://127.0.0.1:8787/
MA3_PROBE_STATE_DIR=C:\Users\hct\.ma3\probe\state
MA3_PROBE_DOCTOR=0
```

### feishu.env

Copy from prod (preferred) or dev machine — **never commit**:

```powershell
# From dev machine
scp root@47.84.49.254:/etc/ma3/feishu.env hct@192.168.31.200:C:/Users/hct/.ma3/probe/feishu.env
# or
scp $env:USERPROFILE\.ma3\probe\feishu.env hct@192.168.31.200:C:/Users/hct/.ma3/probe/feishu.env
```

Required keys: `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_CHAT_ID` (optional `FEISHU_CHAT_IDS`).

---

## Deploy / redeploy from dev machine

From repo root (`C:\doc\ma3`):

```powershell
powershell -ExecutionPolicy Bypass -File deploy/observability/windows/deploy-host-200.ps1
```

Manual steps (what the script does):

1. `scp` `probe_ma3.py`, `local_webhook_sink.py`, and `windows/*` → `C:\Users\hct\ma3-obs-deploy\`
2. Ensure `C:\Users\hct\.ma3\probe\probe.env` and `feishu.env` exist on target
3. Run `install_probe.ps1` → copies into `C:\Users\hct\.ma3\probe\`, registers `ma3-probe`
4. Run `install_sink_task.ps1` → registers `ma3-alert-sink` ONLOGON

---

## Debug playbook (agents)

### 1. SSH + task status

```powershell
ssh hct@192.168.31.200 "schtasks /Query /TN ma3-probe /FO LIST /V"
ssh hct@192.168.31.200 "schtasks /Query /TN ma3-alert-sink /FO LIST /V"
```

### 2. Sink health (on host 200)

```powershell
ssh hct@192.168.31.200 "powershell -Command Invoke-RestMethod http://127.0.0.1:8787/"
```

Expected: `feishu_configured: true`.

### 3. Manual probe tick (foreground on 200)

```powershell
ssh hct@192.168.31.200 "powershell -ExecutionPolicy Bypass -File C:\Users\hct\.ma3\probe\run_probe.ps1"
ssh hct@192.168.31.200 "type C:\Users\hct\.ma3\probe\logs\probe-last.out"
```

Expected line: `OK healthz+whoami instance=ma3-v1-hk`.

### 4. Recent logs

```powershell
ssh hct@192.168.31.200 "powershell -Command Get-Content C:\Users\hct\.ma3\probe\logs\probe.log -Tail 20"
ssh hct@192.168.31.200 "powershell -Command Get-Content C:\Users\hct\.ma3\probe\logs\probe-alerts.jsonl -Tail 10"
```

### 5. Forced-failure drill

Temporarily set wrong `MA3_EXPECT_INSTANCE_ID` in `probe.env`, run probe 3+ times, confirm Feishu `ma3_probe_fail`, restore, confirm `ma3_probe_recover`.

### 6. Do not confuse with app-host alerts

| Alert | Source | Host |
|-------|--------|------|
| `ma3_probe_fail` / `ma3_probe_recover` | Phase 0 probe | **200** |
| `Ma3AvailabilityFastBurn`, `Ma3High5xx`, … | Prometheus on app host | **47.84.49.254** |

App-host FastBurn false-positive fix (traffic floor): `deploy/observability/prometheus/alerts.yml`.

---

## Repo scripts (source of truth)

| File | Role |
|------|------|
| [`../probe_ma3.py`](../probe_ma3.py) | Probe logic (Linux + Windows) |
| [`../probe_ma3.sh`](../probe_ma3.sh) | Linux launcher → `python3 probe_ma3.py` |
| [`../local_webhook_sink.py`](../local_webhook_sink.py) | Feishu webhook sink |
| [`install_probe.ps1`](install_probe.ps1) | Install probe + minute task |
| [`install_sink_task.ps1`](install_sink_task.ps1) | Install sink ONLOGON task |
| [`deploy-host-200.ps1`](deploy-host-200.ps1) | Push + install to host 200 from dev |
| [`probe.env.host200`](probe.env.host200) | Host 200 `probe.env` template |

---

## Related docs

- [../README.md](../README.md) — observability overview
- [../../../docs/06-operations/monitoring-and-health.zh.md](../../../docs/06-operations/monitoring-and-health.zh.md) — SLO + paging model
- [../../../docs/06-operations/runbook.zh.md](../../../docs/06-operations/runbook.zh.md) — alert triage
