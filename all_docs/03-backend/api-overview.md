# HTTP / MCP API 总览

## 路由面

| 前缀 | 鉴权 | 消费者 |
|------|------|--------|
| `POST /mcp` | `X-API-Key` | Agent |
| `GET /client/*` | 公开 | Agent bootstrap（manifest、policy、sync） |
| `/auth/*` | — | Authing OIDC |
| `/api/keys` | session | 浏览器 / 脚本（带 cookie） |
| `/ui/*` | session 或匿名（public stats） | 浏览器 SSR |
| `/healthz`, `/doctor` | 公开 / 受限 | 运维 |

## MCP Tools（v1）

| Tool | 读/写 | 说明 |
|------|-------|------|
| `ma3_context` | 读 | 上下文搜索；billable read units |
| `ma3_case` | 读 | case 展开 |
| `ma3_report` | 写 | 写 record；不计 read quota |
| `ma3_validate` | — | dry-run |
| `ma3_doctor` | — | 诊断 |
| `ma3_whoami` | — | 身份 + 库能力 |
| `ma3_list_my_writes` | 读 | 本人写入审计 |
| `ma3_delete_record` | 写 | owner 删除 |
| `ma3_publish_record` | 写 | owner 提前发布 buffered |
| `ma3_feedback` | 写 | 投票 |
| `ma3_list_drafts` | 读 | maintainer |
| `ma3_review_record` | 写 | maintainer |

完整参数见 [../05-agent/mcp-tools-reference.md](../05-agent/mcp-tools-reference.md)（待补充）。

## REST（用户面）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/keys` | 列表 / 创建 |
| PATCH | `/api/keys/{id}` | 改 label |
| DELETE | `/api/keys/{id}` | 硬删 key |

详见 [../04-frontend/api-keys-ui-and-api.md](../04-frontend/api-keys-ui-and-api.md)。

## 错误格式

MCP：JSON-RPC 2.0；**`error.message` 必须可自纠** — [error-handling.md](../05-agent/error-handling.md)。

REST：FastAPI 标准 `{"detail": "..."}`；403/404 不泄密。

## 版本

- `service_version`、`tool_schema_version`、`skill_bundle_version` — [policy-and-client-sync.md](../05-agent/policy-and-client-sync.md)
- MCP 响应 `structuredContent.server` 升级标志

## 待补充

- [ ] OpenAPI / MCP `tools/list` 自动生成快照流程
- [ ] REST 完整路由表（Observatory admin API）
- [ ] Webhook 契约（Stripe v1.1）
