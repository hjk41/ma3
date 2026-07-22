# 监控与健康检查

> **状态**：待补充

## 已有端点

| 端点 / 工具 | 用途 |
|-------------|------|
| `GET /healthz` | 存活；暴露 version、commit、instance |
| MCP `ma3_doctor` | auth、DB、embedding、legacy keys、billing schema（Phase B） |
| MCP `ma3_whoami` | 运行时 key/principal/quota 快照 |

## doctor 应报告项（目标）

- `anonymous_mcp_enabled: false`（无 API key 时 `tools/call` 除 `ma3_whoami` 外返回 authentication required；匿名无 Community 记录可读权）
- `api_keys_table: ok`
- `auth_admin_configured: ok`（Authing on 时）
- `billing_schema_ok`（Phase B）
- `usage_rollup_lag`（Phase B）
- `legacy_env_writer_keys: deprecated`（若仍设置）

## MCP quota 块

成功读响应可选 `structuredContent.quota` — Agent policy 可要求转告 `warnings`。

## 待补充

- [ ] Prometheus metrics（若有）
- [ ] 告警阈值（read quota 80%、publish job lag）
- [ ] 日志结构化字段约定
- [ ] SLO / SLA 定义
