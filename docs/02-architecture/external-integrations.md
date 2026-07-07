# 外部系统集成

> **状态**：部分定稿 — 部署细节见 [../06-operations/deployment-authing.md](../06-operations/deployment-authing.md)

## 系统上下文

```text
                    ┌─────────────┐
  Agent (MCP) ─────►│             │◄───── Authing OIDC（人登录）
  X-API-Key         │  ma3 server │       session cookie
                    │             │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         PostgreSQL    HF embeddings   HTTP client bundle
         (or SQLite)   (optional off)   manifest/policy/sync
```

## 集成清单

| 外部系统 | 用途 | 协议 | 文档 |
|----------|------|------|------|
| **Authing** | 用户注册/登录；Observatory/门户 session | OIDC authorization_code | [deployment-authing.md](../06-operations/deployment-authing.md) |
| **PostgreSQL** | 生产数据、FTS、pgvector | SQL | [deployment.md](../06-operations/deployment.md) |
| **SQLite** | 测试 / 本地 dev | SQL | — |
| **Hugging Face** | sentence-transformers 缓存 | 本地 HF_HOME；生产 offline | [system-overview.md](system-overview.md) §7 |
| **Agent IDE** | Cursor / Claude Code / Codex 等 | MCP JSON-RPC over HTTP | [../05-agent/getting-started.md](../05-agent/getting-started.md) |
| **Stripe** | 支付（v1.1） | Webhook stub | [../03-backend/billing-and-quotas.md](../03-backend/billing-and-quotas.md) §8 |

## 边界约定

| 面 | 凭证 | 能力 |
|----|------|------|
| **MCP 数据路径** | `X-API-Key` only | 读/写 record、search、feedback |
| **Web UI** | Authing session cookie | 门户、key 管理、Observatory（admin） |
| **Bearer on MCP** | — | **不授予**数据访问（已废止匿名/ bearer 读） |

## 待补充

- [ ] 生产域名 / TLS / 反向代理拓扑图
- [ ] 备份与恢复（Postgres）
- [ ] 多实例部署与会话粘性（若需要）
