# 监控与健康检查

> English default: [monitoring-and-health.md](monitoring-and-health.md)

> **决策记录（2026-07-29 已拍板）：** [25-metrics-slo-decisions.md](../09-engineering/design-archive/25-metrics-slo-decisions.md) · Issue [#5](https://github.com/hjk41/ma3/issues/5)

## 姿态

- **对外 SLA：** 目前无（社区 best-effort）。见根目录 `CHANGELOG.md`。
- **内部 SLO：** 仅针对我方运营的 SaaS（`ma3.io`），**不构成**对客户的承诺。
- **自托管：** 可观测性可选；默认 Compose 行为不变。Phase 1 落地时应用 metrics **默认关闭**。

## 已有端点 / 工具

| 端点 / 工具 | 用途 |
|-------------|------|
| `GET /healthz` | 存活；版本、commit、实例、features |
| MCP `ma3_doctor` | 鉴权、DB、embedding、legacy key、billing schema |
| MCP `ma3_whoami` | Key / principal / 配额快照 |
| `deploy/common/verify_ma3_prod.sh` | 每次生产部署后的一次性公网验收 |

## Phase 0 — 持续站外探活（已交付脚本）

脚本与安装说明：[`deploy/observability/`](../../deploy/observability/README.md)。

| 检查 | 节奏 | 说明 |
|-------|---------|------|
| `GET /healthz` | ~60s | `status=ok`、期望 `instance_id` / `public_base_url`、无 `dev_auth` |
| 匿名 `ma3_whoami` | ~60s | 合法 MCP result 信封 |
| 鉴权 `ma3_doctor` | 可选 | `MA3_PROBE_DOCTOR=1` + `MA3_API_KEY` |

**告警（决策 A）：** 连续失败 N 次（默认 3）后向 `MA3_PROBE_WEBHOOK_URL` POST JSON。ticket 级跟进 **人工** 建单（不自动开 GitHub Issue）。启用新 webhook 时做一次强制失败演练。

**归属：** 探活必须跑在 **非** ma3.io 应用主机上。含 webhook / API key 的 env 不进 git（例如 `/etc/ma3/probe.env`）。

## 内部 SLO（SaaS）— 第一批

| # | 目标 | 度量（意图） | 目标值 | 窗口 |
|---|---|---|---|---|
| SLO-1 | API 可用性 | `/mcp`、`/healthz`、`/api/*` 非 5xx 占比 | ≥ 99.5% | 30d |
| SLO-2 | 外网可达 | 站外探活对公网 `/healthz`（+ whoami）成功率 | ≥ 99.5% | 30d |
| SLO-3 | 检索延迟 | `ma3_context` 工具耗时 p95 | ≤ 2.5 s | 30d |

精确 PromQL 随 Phase 1–3 提交。**推迟：** 写入接受率、发布新鲜度 SLO（待指标就绪）。

## Metrics 暴露（Phase 1，已决策）

| 形态 | 策略 |
|---------|--------|
| SaaS | `/metrics` 仅 loopback / 不经 Caddy 反代 |
| 自托管 | 默认 `MA3_METRICS_ENABLED=0` |

## 日志字段约定（先文档化）

新增结构化应用日志时优先使用：

`ts`、`level`、`event`、`route`、`mcp_tool`、`principal_type`、`status`、`duration_ms`、`request_id`、`instance_id`

禁止把 secret / 原始 API key 打进日志。租户细节留在日志/DB；metrics 仅聚合标签。

## 本 Issue 路线图

| Phase | 状态 | 交付 |
|-------|--------|-------------|
| 0 | **脚本已落地** | 站外探活 + webhook + 文档 |
| 1 | 计划中 | `prometheus-client`、`/metrics`、HTTP+MCP 埋点、SaaS scrape |
| 2 | 计划中 | Alertmanager 最小规则 |
| 3 | 计划中 | SLO-1–3 recording rules + Grafana |
