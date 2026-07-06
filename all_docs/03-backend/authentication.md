# 认证（Authentication）

> Session 用于 **Web UI**；MCP 数据路径见 [authorization-and-libraries.md](authorization-and-libraries.md)。

## 双轨认证

| 轨 | 凭证 | 用途 |
|----|------|------|
| **人（浏览器）** | Authing OIDC → session cookie | 门户、`/ui/keys/*`、Observatory |
| **Agent（MCP）** | `X-API-Key` header | 全部 MCP tools |

Bearer token **不**授予 MCP 数据访问。

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

- **拒绝启动**（与 misconfigured DB 同级）
- `ma3_doctor` 报 fail
- LAN `authing_enabled=False` **不受限**

## Dev break-glass

| 变量 | 用途 |
|------|------|
| `MA3_DEV_AUTH=1` | LAN 跳过 OIDC |
| `MA3_DEV_API_KEY` | 单 key admin bypass（MCP） |

## Display name 门控

未完成 [display-name-registration](../04-frontend/display-name-registration.md) 时：

- 门户路由 → 302 `/ui/me/setup/`
- `GET /api/keys` → 403

## 待补充

- [ ] Session cookie 名称、TTL、安全 flags
- [ ] Authing 用户属性 → principal 字段映射表
- [ ] 登出 / session 失效行为
