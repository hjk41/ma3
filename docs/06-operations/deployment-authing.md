# Deploy profile — Authing 人登录（Observatory）

与 `profile-lan.md`（202 dev_auth）并行：公网或 staging 打开 Authing；LAN 可不配。

## 1. Authing 控制台

1. 注册 [Authing 控制台](https://console.authing.cn/)，创建 **B2C 用户池**。
2. **应用 → 自建应用 → 创建**（类型：Web）。
3. **认证配置**：
   - 授权模式：`authorization_code`
   - 返回类型：`code`
   - 回调 URL（示例）：
     - `https://ma3.io/auth/callback`（生产）
     - `http://192.168.31.202:8000/auth/callback`（内网 staging）
4. **登录控制 → 注册/登录方式**：
   - 开启 **微信**（需微信开放平台网站应用 + 备案域名）
   - 开启 **手机号验证码**（配阿里云/腾讯云短信或 Authing 短信）
5. 记录：
   - **Issuer**：`https://<你的域名>.authing.cn/oidc`（应用详情可见）
   - **App ID**、**App Secret**

## 2. ma3 环境变量

```bash
# 启用 Observatory 登录门禁
export MA3_AUTHING_ENABLED=1

# Authing OIDC（从控制台复制）
export MA3_AUTHING_ISSUER=https://your-subdomain.authing.cn/oidc
export MA3_AUTHING_APP_ID=your_app_id
export MA3_AUTHING_APP_SECRET=your_app_secret

# 对外 URL（用于拼回调；必须与 Authing 回调白名单一致）
export MA3_PUBLIC_BASE_URL=https://ma3.io

# 可选：显式指定回调（默认 ${MA3_PUBLIC_BASE_URL}/auth/callback）
# export MA3_AUTHING_REDIRECT_URI=https://ma3.io/auth/callback

# 可选：Observatory 管理员（sub / 手机 / 邮箱，逗号分隔）
export MA3_AUTH_ADMIN_USERS=13800138000,admin@example.com

# 部署版本（Observatory 显示 git 短 hash；不设则不显示 commit pill）
export MA3_GIT_COMMIT=$(git rev-parse --short HEAD)

# MCP Agent 仍用 dev key（仅 LAN；公网 SaaS 必须关闭）
# export MA3_DEV_AUTH=1
# export MA3_DEV_API_KEY=...
```

写入 `ma3.env` 后重启 uvicorn。

## 3. 验证

```bash
# 未登录访问 Observatory → 应 302 到 /auth/login
curl -sI "$MA3_PUBLIC_BASE_URL/ui/observatory/" | head -5

# 浏览器完成微信/短信登录后
curl -s "$MA3_PUBLIC_BASE_URL/auth/whoami" -b cookies.txt | jq .

# MCP 不受 Authing 影响
curl -s -H "X-API-Key: ma3dev" "$MA3_PUBLIC_BASE_URL/mcp" ...
```

## 4. 与 202 LAN 的关系

| 场景 | MA3_DEV_AUTH | MA3_AUTHING_ENABLED |
|------|--------------|---------------------|
| 纯开发（当前 202） | `1` | 不设 / `0` |
| 试 Authing + MCP | `1` | `1` |
| 公网 SaaS | `0` | `1` |

## 5. 费用提示

- Authing **免费档约 8000 MAU**（见 [定价页](https://www.authing.cn/pricing)）
- **短信**另计（云短信或 Authing 套餐）
- Agent API key **不计入** Authing MAU

## 6. 故障排查

| 现象 | 检查 |
|------|------|
| `redirect_uri mismatch` | `MA3_PUBLIC_BASE_URL` 与 Authing 回调完全一致 |
| 登录后仍跳登录 | cookie 域名/HTTPS；`Secure` 在 http 下已自动关闭 |
| `/auth/whoami` 401 | cookie 名 `MA3_AUTH_SESSION_COOKIE`；token 是否过期 |
| 微信不可用 | 开放平台网站应用、授权回调域、备案 |
