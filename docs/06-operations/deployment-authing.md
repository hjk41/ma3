# Deploy Profile — Authing Human Login (Observatory)

> Chinese version: [deployment-authing.zh.md](deployment-authing.zh.md)

Runs in parallel with `profile-lan.md` (202 dev_auth): enable Authing for public internet or staging; LAN may skip it.

## 1. Authing Console

1. Sign up at the [Authing console](https://console.authing.cn/) and create a **B2C user pool**.
2. **Applications → Self-built application → Create** (type: Web).
3. **Authentication configuration**:
   - Grant type: `authorization_code`
   - Response type: `code`
   - Callback URLs (examples):
     - `https://ma3.io/auth/callback` (production)
     - `http://192.168.1.100:8000/auth/callback` (intranet staging; replace with your LAN host IP)
4. **Login control → Sign-up/login methods**:
   - Enable **WeChat** (requires a WeChat Open Platform website app + an ICP-registered domain)
   - Enable **phone number verification code** (with Aliyun/Tencent Cloud SMS or Authing SMS)
5. Record:
   - **Issuer**: `https://<your-domain>.authing.cn/oidc` (visible in app details)
   - **App ID**, **App Secret**

## 2. ma3 Environment Variables

```bash
# Enable the Observatory login gate
export MA3_AUTHING_ENABLED=1

# Authing OIDC (copy from the console)
export MA3_AUTHING_ISSUER=https://your-subdomain.authing.cn/oidc
export MA3_AUTHING_APP_ID=your_app_id
export MA3_AUTHING_APP_SECRET=your_app_secret

# External URL (used to build the callback; must match the Authing callback whitelist exactly)
export MA3_PUBLIC_BASE_URL=https://ma3.io

# Optional: explicit callback (defaults to ${MA3_PUBLIC_BASE_URL}/auth/callback)
# export MA3_AUTHING_REDIRECT_URI=https://ma3.io/auth/callback

# Optional: Observatory admins (sub / phone / email, comma-separated)
export MA3_AUTH_ADMIN_USERS=13800138000,admin@example.com

# Deployment version (Observatory shows the git short hash; unset = no commit pill)
export MA3_GIT_COMMIT=$(git rev-parse --short HEAD)

# MCP Agents still use the dev key (LAN only; MUST be off for public SaaS)
# export MA3_DEV_AUTH=1
# export MA3_DEV_API_KEY=...
```

Write into `ma3.env`, then restart uvicorn.

## 3. Verification

```bash
# Unauthenticated Observatory access → should 302 to /auth/login
curl -sI "$MA3_PUBLIC_BASE_URL/ui/observatory/" | head -5

# After completing WeChat/SMS login in the browser
curl -s "$MA3_PUBLIC_BASE_URL/auth/whoami" -b cookies.txt | jq .

# MCP is unaffected by Authing
curl -s -H "X-API-Key: ma3dev" "$MA3_PUBLIC_BASE_URL/mcp" ...
```

## 4. Relationship with 202 LAN

| Scenario | MA3_DEV_AUTH | MA3_AUTHING_ENABLED |
|------|--------------|---------------------|
| Pure dev (current 202) | `1` | unset / `0` |
| Trying Authing + MCP | `1` | `1` |
| Public SaaS | `0` | `1` |

## 5. Cost Notes

- Authing **free tier is roughly 8000 MAU** (see the [pricing page](https://www.authing.cn/pricing))
- **SMS** is billed separately (cloud SMS or an Authing plan)
- Agent API keys do **not** count toward Authing MAU

## 6. Troubleshooting

| Symptom | Check |
|------|------|
| `redirect_uri mismatch` | `MA3_PUBLIC_BASE_URL` must match the Authing callback exactly |
| Still redirected to login after logging in | cookie domain/HTTPS; `Secure` is auto-disabled over http |
| `/auth/whoami` 401 | cookie name `MA3_AUTH_SESSION_COOKIE`; token expired? |
| WeChat unavailable | Open Platform website app, authorized callback domain, ICP registration |
