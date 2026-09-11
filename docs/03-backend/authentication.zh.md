# 认证（Authentication）

> Session 用于 **Web UI**；MCP 数据凭证为 API key 或 ma3 签发的 MCP OAuth token — 见 [authorization-and-libraries.zh.md](authorization-and-libraries.zh.md) 与 [ADR-016](../02-architecture/decisions/016-mcp-oauth-plus-api-keys.zh.md)。

## 认证轨道

| 轨 | 凭证 | 用途 |
|----|------|------|
| **人（浏览器）** | Authing OIDC / local auth → session cookie | 门户、`/ui/keys/*`、Observatory；并完成 MCP OAuth authorize |
| **交互式 MCP 客户端**（Cursor 等） | MCP Authorization Spec OAuth → **ma3 MCP access token** | MCP tools，Layer-1 entitlement 投影 |
| **Agent / CI（MCP）** | `X-API-Key`（或 Bearer-as-key） | MCP tools，Layer-2 `api_key_grants` |

**裸 Authing / OIDC access token 不授予 MCP 数据访问。** 仅 ma3 签发的 `ma3mcp_…`（绑定 resource）或 API key 可以。

## MCP OAuth（规范登录）

```text
POST /mcp（无凭证）
  → 401 + WWW-Authenticate: Bearer resource_metadata="…/.well-known/oauth-protected-resource"
GET /.well-known/oauth-protected-resource
  → resource, authorization_servers
GET /oauth/authorize（PKCE S256）→ 必要时 /auth/login → 带 code 重定向
POST /oauth/token → ma3 access_token（audience = {PUBLIC_BASE_URL}/mcp）
POST /mcp Authorization: Bearer ma3mcp_…
```

**Public base URL（生产 / 反代必配）：** 设置 `MA3_PUBLIC_BASE_URL` 为客户端使用的外部源（如 `https://ma3.io`）。PRM、`WWW-Authenticate`、authorize/token 的 `resource`、以及门户「贴给 agent」块优先用该值。未配置时回退到请求 `Host`（便于 LAN/dev）——**不要**在公网裸暴露该模式；应在可信反代 / Host allowlist 之后，否则伪造 `Host` 会污染 OAuth metadata。

环境变量：`MA3_MCP_OAUTH_ACCESS_TOKEN_TTL_SEC`（默认 3600）、`MA3_MCP_OAUTH_AUTH_CODE_TTL_SEC`、`MA3_MCP_OAUTH_REDIRECT_URI_ALLOWLIST`（localhost / `cursor://` 始终允许）。

## Authing 登录流

```text
GET /ui/me/ (无 session)
  → 302 /auth/login?next=...
  → 302 Authing authorize
  → GET /auth/callback?code=...
  → ensure_user_principal + ensure_personal_library
  → 若 display_name_locked=0 → 302 /ui/me/setup/
  → 否则 302 next（默认 /ui/me/）
```

配置见 [../06-operations/deployment-authing.md](../06-operations/deployment-authing.md)。

## Session 用户模型

```python
SessionUser:
  principal_id: str      # user:{authing_sub}
  display_name: str
  is_admin: bool         # MA3_AUTH_ADMIN_USERS 匹配
```

## 启动校验

当 `settings.authing_configured and not settings.auth_admin_users`：

- **拒绝启动**（与 DB 配错同级）
- `ma3_doctor` 报告失败
- LAN `authing_enabled=False` **不受限**

## Dev break-glass

| 变量 | 用途 |
|------|------|
| `MA3_DEV_AUTH=1` | LAN 跳过 OIDC |
| `MA3_DEV_API_KEY` | 单 key admin bypass（MCP） |

## 显示名门禁

完成 [display-name-registration](../04-frontend/display-name-registration.md) 前：

- 门户路由 → 302 `/ui/me/setup/`
- `GET /api/keys` → 403

## TODO

- [ ] Session cookie 名、TTL、安全标志
- [ ] Authing 用户属性 → principal 字段映射表
- [ ] Logout / session 失效行为
- [ ] 可选 refresh token / Dynamic Client Registration
