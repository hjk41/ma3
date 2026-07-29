# HTTP / MCP API 总览

## 原则：MCP 管知识，REST 管其余

| 通道 | 用途 | 鉴权 |
|------|------|------|
| **MCP** `POST /mcp` | 知识环：查询、上报、点赞/点踩、draft/publish/delete、whoami/doctor/validate | `X-API-Key` |
| **REST** `/api/*` | 部署后运营：注册/setup、账号、API key、组织、成员、库与授权、Observatory 管理 | `X-API-Key`（推荐）或门户 session（浏览器；写操作需 same-origin） |
| **Shell / Compose** | 装机、`./up.sh`、bootstrap 文件轮换 | 宿主机运维（**不**提供 HTTP） |
| **OIDC 浏览器跳转** | SaaS / 自建 IdP 登录 | 交互式例外（agent 无法替代浏览器 OAuth） |

Self-host **bootstrap** API key：可走 MCP 知识工具；**不能**调用门户管理类 REST（用户、组织、setup 完成等）。

Agent 完整链路（Compose 起好之后）应可仅用 **REST + MCP** 完成，无需打开浏览器。见 [self-hosting.md](../06-operations/self-hosting.md#agent-surface-mcp--rest)。

## 路由面

| 前缀 | 鉴权 | 消费者 |
|------|------|--------|
| `POST /mcp` | `X-API-Key` | Agent（知识） |
| `GET /client/*` | 公开 | Agent bootstrap（manifest、policy、sync） |
| `/api/auth/*`, `/api/setup/*`, `/api/local-users` | 公开或部分需 local admin key | Agent day-0 / 本地账号 |
| `/api/me`, `/api/keys`, `/api/orgs`, `/api/libraries`, `/api/principals` | 用户 API key 或 session | Agent / 浏览器 |
| `/api/admin/*` | 产品管理员 API key 或 session | Agent / Observatory |
| `/auth/*` | OIDC / local HTML | 浏览器 |
| `/ui/*` | session 或匿名 | 浏览器 SSR（与 REST 同服务，非必须） |
| `/healthz` | 公开 | 运维 |

## MCP Tools（知识环）

| Tool | 读/写 | 说明 |
|------|-------|------|
| `ma3_context` | 读 | 上下文搜索 |
| `ma3_case` | 读 | case 展开 |
| `ma3_locate_by_id` | 读 | 按 ID 定位 |
| `ma3_report` | 写 | 上报 record |
| `ma3_feedback` | 写 | 点赞 / 点踩 / clear |
| `ma3_validate` | — | dry-run |
| `ma3_doctor` | — | 诊断 |
| `ma3_whoami` | — | 身份 + 库能力 |
| `ma3_list_my_writes` | 读 | 本人写入 |
| `ma3_list_drafts` / `ma3_review_record` | 读/写 | maintainer |
| `ma3_publish_record` / `ma3_patch_record` / `ma3_delete_record` / `ma3_restore_record` | 写 | 记录生命周期 |

完整参数见 MCP `tools/list` 与 [../05-agent/mcp-tools-reference.md](../05-agent/mcp-tools-reference.md)（若存在）。

## REST（运营面）

### 身份与 day-0

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/setup/status` | Setup 状态 |
| PATCH | `/api/setup/registration` | 开/关注册（local admin） |
| POST | `/api/setup/registration/ack` | 确认保持开放 |
| POST | `/api/setup/complete` | 完成引导 |
| POST | `/api/auth/register` | 注册（可选 mint API key；可选 `invite` 自动入组织） |
| POST | `/api/auth/login` | 登录并 mint API key |
| GET/PATCH | `/api/local-users` | 本地账号列表 / 升降管理员 |
| GET/PATCH | `/api/me` | 当前主体；首次设定显示名 |
| GET | `/api/principals?q=` | 按显示名搜索（加成员用） |

### API keys

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/keys` | 列表 / 创建（`X-API-Key` 或 session） |
| PATCH/DELETE | `/api/keys/{key_id}` | 改 label/grants；删除（不可删当前调用 key） |

详见 [../04-frontend/api-keys-ui-and-api.md](../04-frontend/api-keys-ui-and-api.md)。

### 组织与库

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/orgs` | 列出 / 创建 team org |
| GET | `/api/orgs/creation-quota` | 建 org 配额 |
| GET | `/api/orgs/{id}` | 详情 + 库列表 |
| GET | `/api/orgs/{id}/settings` | 账单标签等只读设置 |
| GET/POST | `/api/orgs/{id}/members` | 成员列表 / 添加（可选 `alias`） |
| PATCH/DELETE | `/api/orgs/{id}/members/{principal_id}` | 改角色 / 别名 / 移除 |
| POST | `/api/orgs/{id}/invites` | 创建邀请；可选 `member_alias`；返回 `token` + `invite_url` |
| GET/DELETE | `/api/orgs/{id}/invites`… | 列表 / 吊销 |
| GET | `/api/invites/preview?token=` | 预览邀请（公开，含别名） |
| POST | `/api/invites/redeem` | 已有账号兑换入组织 |
| POST | `/api/orgs/{id}/libraries` | 创建 org library |
| GET | `/api/libraries` | 当前主体可见库 |
| GET | `/api/libraries/{id}` | 详情 + stats |
| GET | `/api/libraries/{id}/records` | 库内记录分页（maintainer） |
| GET/POST/DELETE | `/api/libraries/{id}/grants`… | 库级授权 |
| GET/PATCH | `/api/libraries/{id}/settings` | 写入缓冲期 |
| GET | `/api/libraries/{id}/storage` | 用量 |

### 管理（产品管理员）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/observatory/stats` | 系统统计 |
| GET | `/api/admin/billing/overview` | 付费概况 |
| GET | `/api/admin/users` | 用户列表 |
| PATCH | `/api/admin/users/{principal_id}/plan` | 设 free/pro |
| GET | `/api/admin/orgs` | 全部组织 |

## 错误格式

MCP：JSON-RPC 2.0；**`error.message` 必须可自纠** — [error-handling.md](../05-agent/error-handling.md)。

REST：FastAPI 标准 `{"detail": "..."}`；403/404 不泄密。

## 版本

- `service_version`、`tool_schema_version`、`skill_bundle_version` — [policy-and-client-sync.md](../05-agent/policy-and-client-sync.md)
- MCP 响应 `structuredContent.server` 升级标志
