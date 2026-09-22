# 运维 Runbook

> 英文版：[runbook.md](runbook.md)

面向已运营 SaaS 实例（`https://ma3.io`）的可交接步骤。  
部署机制详见 [deploy/README.zh.md](../../deploy/README.zh.md)（或英文 [deploy/README.md](../../deploy/README.md)）。  
健康检查 / 告警 / SLO：[monitoring-and-health.zh.md](monitoring-and-health.zh.md)。

**运维原则：** 每次生产变更后亲自跑验收；全部通过再向他人报告成功。

---

## 1. 联系人 / 值班

| 角色 | 路径 |
|------|------|
| 主运维 | 仓库维护者（当前单人） |
| 寻呼 | 飞书（202 站外探活 + 应用主机 Alertmanager → sink） |
| Ticket | 飞书 / GitHub Issues 人工跟进 |

无独立 24×7 排班；飞书告警即 on-call 信号。

---

## 2. 发版（生产 / `ENV_MODE=preserve`）

### 前置

- 本地 checkout 为待发布 commit；建议该 commit CI 已绿。
- 该 commit 已 push 到配置的 `GIT_REF`。
- 存在 gitignore 配置：`deploy/deploy.ma3.io.env`（含 `REMOTE_HOST`、`ALLOWED_HOSTS`、`DEPLOY_SOURCE=git`、Git remote/ref/deploy-key 路径、`BLUE_GREEN=1`，可选 `VERIFY_API_KEY`）。
- 能 SSH 到应用主机（直连或常用代理）。
- 公共仓库可由应用主机匿名 HTTPS 拉取；若改为私有仓库，则需仓库级 GitHub 只读 Deploy Key，并固定 GitHub SSH host key。
- 远端已有 `/opt/ma3_deploy/ma3.env`（含密钥；deploy **不会**覆盖）。

### 步骤

```bash
# 仓库根目录
./deploy/deploy.sh deploy/deploy.ma3.io.env
```

脚本自动完成：

1. 把本地 HEAD 解析成完整 SHA；服务器 **fetch** `GIT_REF`、验证 SHA 可到达，并准备 `releases/<sha>`
2. **断言**生产 env（`MA3_DEV_AUTH≠1`、instance id、公网 URL、无局域网代理变量）
3. 在该 release 的 `code/server/.venv` 中 **pip install**
4. 新进程使用 **`MA3_GIT_COMMIT`**；仅在健康检查和切流成功后持久化
5. **重启** uvicorn：
   - `BLUE_GREEN=1`：idle 端口启动 → `/healthz` → 改写 Caddy upstream → `caddy reload` → 公网 smoke → drain → 停旧端口；并更新 Prometheus `file_sd`
   - 非蓝绿：`pkill` 后在 `MA3_PORT` 启动
6. 原子更新 `current`（并保留 `previous`），再做**远端 loopback smoke** + 本地公网 **`verify_ma3_prod.sh`**

### 仅复验（不重新部署）

```bash
export MA3_BASE_URL=https://ma3.io
export MA3_EXPECT_INSTANCE_ID=ma3-v1-hk
export MA3_EXPECT_PUBLIC_BASE_URL=https://ma3.io
# export MA3_API_KEY=ma3k_...
bash deploy/common/verify_ma3_prod.sh
```

### 查看蓝绿状态（不部署）

```bash
ssh root@<app-host> \
  'REMOTE_DIR=/opt/ma3_deploy \
   CADDY_UPSTREAM_FILE=/opt/ma3_deploy/data/bluegreen/upstream.caddy \
   bash /opt/ma3_deploy/current/deploy/common/bluegreen_remote.sh status'
```

---

## 3. 回滚

优先用最小代价恢复已知良好的 `/healthz` 与公网验收。

### A. 蓝绿切换中途失败

`bluegreen_cutover` 在公网 smoke 失败时会把 **Caddy upstream** 滚回旧端口并停掉新进程。用 `status` 确认后重跑 `verify_ma3_prod.sh`。

### B. 错误 commit 已上线

```bash
DEPLOY_GIT_COMMIT=<known-good-sha> \
  ./deploy/deploy.sh deploy/deploy.ma3.io.env
```

脚本会复用或重新准备该旧 release 并再次蓝绿切流；SHA 必须仍可从 `GIT_REF` 到达，
无需切换/重置本机工作区，也不会上传工作区。

### C. 紧急：Caddy 指回另一槽位（仅当旧 uvicorn 仍在监听）

在应用主机上对健康端口调用 `bluegreen_write_upstream` / `bluegreen_write_prometheus_targets` 并 `caddy reload`。若 drain 后旧进程已杀，改走 **B**。

### D. 仅 `ma3.env` 配错

在主机上编辑 `/opt/ma3_deploy/ma3.env`（密钥不得进 Git），再正常发版或谨慎重启 live 端口，并复验。

---

## 4. 数据库 schema /「migration」

生产 **preserve** 模式**没有**独立的 Alembic/Flyway 发版步骤。

| 模式 | 行为 |
|------|------|
| `preserve`（ma3.io） | 应用启动时 ensure schema（含可选 pgvector）；无 `RUN_MIGRATION` 回填 |
| `regenerate`（局域网） | `RUN_MIGRATION=1` 时可跑 legacy 回填（见 `deploy/deploy.sh`） |

### 发版后验证

- 公网 `/healthz`：`status=ok`、期望 `instance_id` / `public_base_url`、features 含 `vector`、**无** `dev_auth`
- 带运维 API key 的 `ma3_doctor`：`status=ok`，数据库 / pgvector 状态符合预期
- 设置了 `MA3_API_KEY` 时，`verify_ma3_prod.sh` 会跑相关 pytest

破坏性手工 SQL / 从备份恢复：先快照，维护窗口操作，再全量验收。备份策略由主机/云厂商侧负责，本 runbook 不替代备份制度。

---

## 5. 日志与常用 grep

### 应用主机（`/opt/ma3_deploy`）

| 来源 | 位置 |
|------|------|
| uvicorn（经典） | `/tmp/ma3-v1-uvicorn.log` |
| uvicorn（蓝绿） | `/tmp/ma3-v1-uvicorn-8000.log`、`…-8001.log` |
| healthz JSON | `/tmp/ma3-healthz.json`、`/tmp/ma3-healthz-<port>.json` |
| pid | `/opt/ma3_deploy/ma3.pid` |
| 运行 env | `/opt/ma3_deploy/ma3.env`（密钥，勿贴进工单） |
| 蓝绿状态 | `data/bluegreen/active_port`、`upstream.caddy`、`prometheus-targets.json` |
| 告警 sink | `/var/log/ma3/probe-alerts.jsonl`，`journalctl -u ma3-alert-sink` |
| Prom / Grafana / AM | Docker：`ma3-prometheus` 等（仅 loopback UI） |

```bash
ss -ltn | grep -E '800[01]|9090|3000'
tail -n 80 /tmp/ma3-v1-uvicorn-8001.log
grep -E 'ERROR|Traceback|CRITICAL' /tmp/ma3-v1-uvicorn-*.log | tail
curl -sf https://ma3.io/healthz | python3 -m json.tool
```

### 运维本机 / 主机 202（站外探活）

| 来源 | 位置 |
|------|------|
| 探活 timer | `systemctl status ma3-probe.timer` |
| 探活日志 | `journalctl -u ma3-probe.service -n 50` |
| 告警 JSONL | `/var/log/ma3/probe-alerts.jsonl` |
| 飞书 / 探活 env | `/etc/ma3/feishu.env`、`/etc/ma3/probe.env`（不进 git） |

### 观测 UI（SSH 隧道）

```bash
ssh -L 3000:127.0.0.1:3000 -L 9090:127.0.0.1:9090 root@<app-host>
```

栈挂了可重拉：

```bash
ssh root@<app-host> 'REMOTE_DIR=/opt/ma3_deploy bash /opt/ma3_deploy/deploy/observability/run_saas_stack.sh'
```

---

## 6. 告警速查

| 信号 | 含义 | 先查 |
|------|------|------|
| `ma3_probe_fail` | 202 看公网不可达 | healthz、Caddy、live 端口、DNS |
| `ma3_probe_recover` | 探活恢复 | 是否刚发版闪断 |
| `Ma3ScrapeDown` | Prom 刮不到 `/metrics` | `prometheus-targets.json` vs live 端口；`MA3_METRICS_ENABLED` |
| `Ma3High5xx` / `Ma3AvailabilityFastBurn` | 5xx / 错误预算快烧 | uvicorn 日志、刚发版、DB、embeddings |
| `Ma3ContextSlow` | `ma3_context` p95 高 | DB/pgvector、embedding |

详见 [monitoring-and-health.zh.md](monitoring-and-health.zh.md)。

---

## 7. 常见操作速查

| 场景 | 步骤 | 文档 |
|------|------|------|
| 首次部署 Authing | 控制台 + env + 验证 curl | [deployment-authing.md](deployment-authing.md) |
| 添加产品管理员 | 更新 `MA3_AUTH_ADMIN_USERS` + 重启 | [authentication.md](../03-backend/authentication.md) |
| 用户无法登录 | 检查 callback、issuer、cookie | deployment-authing |
| MCP 401 | key 是否删除/过期；`ma3_doctor` | [getting-started.md](../05-agent/getting-started.md) |
| 搜索无 vector | `MA3_DISABLE_EMBEDDINGS`、HF 缓存 | [system-overview.md](../02-architecture/system-overview.md) |
| 启动失败 admin 白名单 | 设置 `MA3_AUTH_ADMIN_USERS` | portal-permissions |
| 公网 `/metrics` 必须关闭 | Caddy 拦截；`verify_ma3_prod.sh` | [monitoring-and-health.zh.md](monitoring-and-health.zh.md) |

---

## 8. 本 runbook 验收

- [x] 发版步骤（精确 SHA Git release → 重启/蓝绿 → smoke / `verify_ma3_prod.sh`）
- [x] 回滚（Caddy 自动回滚、重发好 commit、紧急切 upstream）
- [x] preserve / regenerate 的 schema 说明与验证
- [x] 日志位置与常用 grep
- [x] 值班 / 寻呼路径（飞书 + 维护者）
- [x] 已从 [docs/README.md](../README.md) / [docs/README.zh.md](../README.zh.md) 链出
