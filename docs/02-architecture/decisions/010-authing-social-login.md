# ADR-010 — Authing B2C 社交登录（Observatory）

## 状态

Accepted（2026-07-01）

## 背景

v1 需要「普通人友好」的登录方式（微信、手机验证码），Agent 仍用 API key。ADR-001 已定 SaaS 首要形态；ADR-005 定 Observatory 使用 OIDC session。

经选型，**Authing 公有云 B2C 免费档（8000 MAU）** 作为首期人登录网关；202 LAN 继续 `MA3_DEV_AUTH`，不强制 Authing。

## 决策

1. **Observatory / 人维护者 UI** 通过 **Authing OIDC 授权码模式** 登录。
2. **MCP / Agent** 继续使用 `X-API-Key` / library key，**不经过 Authing**。
3. 登录成功后 ma3 **upsert `principals`**（`kind=user`），`sso_user` = Authing `sub`。
4. Session：**HttpOnly cookie** 存 `access_token`，请求时用 Authing **userinfo** 校验并带短期内存缓存。
5. 启用条件：`MA3_AUTHING_ENABLED=1` 且配置 `MA3_AUTHING_ISSUER`、`MA3_AUTHING_APP_ID`、`MA3_AUTHING_APP_SECRET`。
6. **管理员**：`MA3_AUTH_ADMIN_USERS`（逗号分隔 sub / 手机 / 邮箱 / 用户名）→ Observatory 显示 admin 标记；library ACL 仍走 `library_access`（v1.1 完善）。

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `MA3_AUTHING_ENABLED` | 启用时 `1` | 打开 Observatory 登录门禁 |
| `MA3_AUTHING_ISSUER` | ✅ | 如 `https://<pool>.authing.cn/oidc` |
| `MA3_AUTHING_APP_ID` | ✅ | Authing 应用 ID |
| `MA3_AUTHING_APP_SECRET` | ✅ | 应用密钥（仅服务端） |
| `MA3_PUBLIC_BASE_URL` | 推荐 | 生成回调 URL，如 `https://ma3.example.com` |
| `MA3_AUTHING_REDIRECT_URI` | 可选 | 默认 `{PUBLIC_BASE_URL}/auth/callback` |
| `MA3_AUTH_SESSION_COOKIE` | 可选 | 默认 `ma3_session` |
| `MA3_AUTH_ADMIN_USERS` | 可选 | 管理员标识列表 |
| `MA3_DEV_AUTH` | LAN | `1` 时 MCP dev key 仍可用；与 Authing 可并存 |

## Authing 控制台配置

1. 创建 **B2C 用户池** + **自建应用**（Web）。
2. 授权模式：勾选 **authorization_code**，返回类型 **code**。
3. 登录回调 URL：`{MA3_PUBLIC_BASE_URL}/auth/callback`
4. 登出回调 URL：`{MA3_PUBLIC_BASE_URL}/ui/observatory/`
5. 登录方式：开启 **微信**、**手机号验证码**（按控制台指引配短信）。
6. Scope：`openid profile phone email`（按需）。

## ma3 路由

| 路由 | 说明 |
|------|------|
| `GET /auth/login` | 跳转 Authing 授权页 |
| `GET /auth/callback` | 授权码换 token，写 cookie，重定向 `next` |
| `POST /auth/logout` | 清 cookie，跳转 Authing 登出（可选） |
| `GET /auth/whoami` | 当前登录用户 JSON |

Observatory：`MA3_AUTHING_ENABLED=1` 时未登录访问 `/ui/observatory/*` → 302 `/auth/login`。

## 后果

### 正面

- 用户只见微信/短信按钮（Authing 托管登录页）
- 免费档可支撑早期 MAU
- Agent 路径零改动

### 负面

- 依赖 Authing 可用性；需单独配短信/微信开放平台
- 海外社交（Google/Apple）后续可加 Authing 连接器或第二 issuer（v1.1）

### 关联

- ADR-001、005、008
- [deployment-authing.md](../../06-operations/deployment-authing.md)
