# ADR-016 — MCP Authorization Spec OAuth + API Key 双通道

## 状态

Accepted（2026-09-11）

## 背景

Cursor 等 MCP 客户端可走交互式 OAuth（RFC9728 PRM + OAuth 2.1 + PKCE + RFC8707 `resource`）。Agent/CI 仍需要非交互凭证。

既有 ADR 将人 UI（Authing/OIDC session）与 Agent MCP（`X-API-Key`）分离。代码另有一条窄路径：用**裸 Authing access token** 作 Bearer 进 MCP，仅映射 `lib_default`，存在无 `aud`/resource 绑定、与门户 Layer-1 entitlement 不一致、并与 ADR-011「Bearer 不是 MCP 数据凭证」冲突的问题。

## 决策

1. **协议**：ma3 同时作为 MCP 资源服务器与轻量 AS，实现 MCP Authorization Spec（PRM、AS metadata、PKCE S256 authorize、token 端点）。
2. **IdP**：Authing/OIDC（或 local auth）仅做人登录；authorize 复用现有 `/auth/*` session。
3. **MCP access token**：由 **ma3 签发** 的 opaque token，DB 存 SHA-256，`resource` 绑定公共 MCP URL；短 TTL，删行即可吊销。
4. **OAuth 权限（选项 A）**：将登录主体的 **Layer-1 entitlement** 投影为 `grant_readable` / `grant_writable` / `grant_maintainer`；交互客户端无需再造 Key。
5. **API Key 不变**：Agent/CI 主路径；解析顺序为 **DB API key**（含 Bearer-as-key）→ env/dev key → **ma3 MCP OAuth token**。**不再**用裸 Authing AT 授予 MCP 数据工具。OAuth 权限为严格 Layer-1（不投影 API Key grants）。
6. **401 挑战**：MCP 认证失败返回 `WWW-Authenticate: Bearer resource_metadata="…"` 与 JSON-RPC `-32001`。Public base 优先 `MA3_PUBLIC_BASE_URL`，否则用请求 Host（接受 localhost 别名）。

## 后果

### 正面

- Cursor 式弹窗登录，无需先造 Key
- OAuth 权限与门户可见库一致
- Agent/CI 路径不变
- resource 绑定关闭裸 Authing Bearer 旁路

### 负面

- OAuth token ≈ 会话能力，必须短 TTL + HTTPS + 可吊销
- 无门户登录的自托管实例不可用 OAuth；Key/bootstrap 仍可用
- CIMD/DCR 需真实客户端验证（首版先 redirect allowlist）

### 关联

- 修订 ADR-010：Agent 侧「MCP 不经 Authing」仅指不把 Authing AT 当 MCP 主凭证；交互 OAuth 仍经 Authing 做人登录，由 ma3 签发 MCP token
- 修订 ADR-011：裸 Authing Bearer 不进 MCP；**ma3 MCP OAuth token 可进**
- ADR-015：无 OIDC 时 authorize 可用 local auth
- 规格：[authentication.zh.md](../../03-backend/authentication.zh.md)、[authorization-and-libraries.zh.md](../../03-backend/authorization-and-libraries.zh.md)
