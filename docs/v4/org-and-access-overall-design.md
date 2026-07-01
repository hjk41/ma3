# ma3 v4 — Organization, Access Control & Agent Skill (Overall Design)

Status: **approved 2026-06-30** (rev 3.1 — IdP strategy locked)  
Author: chuntao.hong (with Cursor)  
Scope: **全新 v4**；对外多租户 SaaS；空库部署；不兼容 v2/v3。  
Prerequisite: 工程实施以本文为准（`client/AGENTS.md` 治理规则仍适用）。

**Rev 3.1：** 身份方案已确认 — **托管 OIDC IdP 聚合社交登录**（见 §5.0），体验对标 GitHub 多按钮登录；**不**自建密码库。

**Rev 3 相对 rev 2：** 删除 `auth.zhilicon.com`、LTP/CephFS；自助建 org；免费档 **1 席位**，增员付费。

---

## 1. Why

ma3 v4 作为 **对外 SaaS** 卖给国内外客户，需要：

| 问题 | v4 做法 |
|------|---------|
| 内部 SSO 已下线 | **标准 OIDC**（国际 + 国内各一套 Issuer，见 §5） |
| 无组织与商业边界 | `organization` + **席位（seat）配额** |
| Agent key 权限过粗 | `api_key_grants` 按库 `reader` / `writer` / `admin` |
| 历史部署绑定 CephFS/LTP | **公有云**：应用 VM + 托管 PostgreSQL + 对象存储备份 |
| Skill 与 server 版本漂移 | MCP 统一 `server` envelope + `ma3_skill` |

---

## 2. Goals

1. **对外多租户**：客户自助注册 → 自建 org → 建 library → 签 API key → Agent 调 MCP。
2. **身份**：OIDC 登录（人类）；API key（Agent）。**不**再集成已下线的 `auth.zhilicon.com`。
3. **组织 → 知识库 → 成员 → Token** 闭环；数据 **按 org 硬隔离**。
4. **免费档**：每个 org **默认 1 个成员**（创建者 = owner）；邀请第 2 人起需 **付费升席位**。
5. **国内外客户**：登录页支持 **Global / China** 两条 OIDC 线路（可配置为同一 Issuer 的两个 Client）。
6. **Key 可含 `admin`**，签发时安全确认；org owner/admin 对其 org 下 library **隐式 admin**。
7. **MCP** 每次返回 `server` 版本块；`ma3_skill` + `/skill/*` 升级 skill。
8. **UI**：GitHub 风格顶栏 + 表格；仅 v4，无回退。

## 3. Non-goals

- ma3 **不**自研密码库 / 邮箱验证 UI（交给 OIDC IdP）。
- v4 **不**实现按 org 绑定客户自有 SAML IdP（企业 SSO → v4.1）。
- v4 **不**实现完整计费平台；只做 **席位闸门** + webhook/结账 URL 挂钩点（Stripe 等接 v4.0.1）。
- record 级 ACL、跨 org 知识联邦。
- 兼容 v2/v3 API、legacy token、`/client/*`。
- **LTP 容器、CephFS、WAL 归档到 CephFS** 等内部部署路径（从文档与默认配置中删除）。

---

## 4. 概念模型

```text
                    ┌─────────────────┐     ┌─────────────────┐
                    │ OIDC (Global)   │     │ OIDC (China)    │
                    │ Clerk/Auth0/…   │     │ Authing/IDaaS/… │
                    └────────┬────────┘     └────────┬────────┘
                             │    Authorization Code + PKCE
                             ▼
                      ma3 /auth/oidc/callback
                             │
                             ▼
   principal (user:<sub>) ◄──┴──► organization_members ──► organization
        │                              │                      │
        │                              │                      ├── member_seat_limit (default 1)
        │                              │                      ├── plan_tier (free|paid|…)
        │                              │                      └── library (required org_id)
        │                              │                            └── library_access
        └── api_key ──► api_key_grants

   break-glass: MA3_API_KEY → admin:root（平台运维 only）
```

### 4.1 Principal

| kind | id 格式 | 用途 |
|------|---------|------|
| `user` | `user:<oidc_sub>` | 人类；OIDC 首登懒创建；`metadata_json.idp` 记录 global/china |
| `service` | `service:<name>` | 平台级自动化；仅 `admin:root` 可创建 |
| `admin` | `admin:root` | 合成；`MA3_API_KEY`；不持久化 |

`sso_user` 列保留为 **可读的登录名**（OIDC `preferred_username` 或 email），但 **主键身份是 `sub`**，避免 IdP 迁移时撞名。

### 4.2 Organization

| 字段 | 说明 |
|------|------|
| `org_id` | `org_<id>` |
| `slug` | 唯一 URL 段 |
| `name`, `description` | 显示 |
| `plan_tier` | `free`（默认）\| `paid` \| `enterprise`（预留） |
| `member_seat_limit` | 整数，**默认 `1`**；付费后由 billing webhook 调高 |
| `created_at`, `created_by` | 创建者成为首任 `owner` |

**Org 角色**（`organization_members.org_role`）：

| org_role | 能力 |
|----------|------|
| `owner` | 全权、删 org、结账/升席位、转让 owner |
| `admin` | 管成员（在席位内）、建库、管 library ACL |
| `member` | 看 org 与库列表；库权限靠 `library_access` |

**席位规则（硬约束）：**

```text
COUNT(organization_members WHERE org_id = ?) <= organizations.member_seat_limit
```

- `POST /v4/orgs` 成功后自动插入创建者一条 `owner` 成员 → 占用 **1/1** 席位。
- `POST .../members` 在 `COUNT >= limit` 时返回 **`402 payment_required`**（body 含 `checkout_url` 或 `upgrade_path`）。
- `owner` 不能被「挤掉」；删 org 前须先处理数据。

**自助创建 org：**

- 任意已登录 `user` 可 `POST /v4/orgs`（限流：每 user 每天最多 N 个，防滥用，默认 N=5，可配置）。
- 创建后 `plan_tier=free`，`member_seat_limit=1`。
- 不自动创建 library；引导用户进入 org 设置页建第一个库。

### 4.3 Library

- **必须** `organization_id NOT NULL`。
- 默认 `is_public = false`（对外 SaaS **禁止**默认公开库）。
- Org `owner`/`admin` 对下属 library **隐式 `admin`**（resolver 计算，UI 标注 implicit）。

### 4.4 API Key

- Raw：`ma3v4_<base32>`。
- 权限 **仅** `api_key_grants`；签发时至少一行；`role ∈ {reader, writer, admin}`。
- Key 权限 ≤ principal 在该库的有效角色；`admin` grant 需 `acknowledge_admin_risk`。

### 4.5 有效权限

与 rev 2 相同：`effective = min(principal_role, key_grant)`；序 `reader < writer < admin`。

---

## 5. 认证（OIDC）

**删除** `MA3_AUTH_VERIFY_URL`、`gateway_token` 验票、`auth.zhilicon.com` 相关代码路径与文档。

### 5.0 已确认方案：托管 IdP + 多社交登录（对标 GitHub 登录页）

**不**自建用户名密码系统（不做 GitHub 级账号基建）。**不**把 Google/GitHub 逐个直连进 ma3，而是：

```text
ma3 只对接 1~2 个托管 OIDC Issuer（各区域一个）
    └── IdP 控制台里开启多种 Connection（Google、GitHub、邮箱 Magic Link、企微…）
    └── 用户点「Continue with Google」等 → IdP 处理 OAuth → ma3 收到统一 OIDC id_token / userinfo
    └── ma3 落库 principal_id = user:<sub>（sub 来自 IdP，全局唯一）
```

| 区域 | 托管 IdP（实施选型，二选一为主） | 登录页按钮（在 IdP 侧配置） |
|------|----------------------------------|-----------------------------|
| **Global** | **Clerk** 或 **Auth0**（首选） | Google、GitHub、Email（Magic Link / 密码less） |
| **China** | **Authing** 或 **阿里云 IDaaS** | 手机号、企微、钉钉（按 IdP 能力与合规选配） |

**产品体验：** `/auth/login` 展示 **International** / **中国大陆** 两个入口；每入口跳转到对应 IdP Hosted Login（或 ma3 嵌 IdP SDK 组件），**用户无需理解 IdP**。

**与 Agent 分工不变：** 人类 → OIDC session；Agent → `ma3v4_` API key。

**实施默认（若无另行指定）：**

- Global：**Clerk**（上线快、自带 Google/GitHub 开关）
- China：**Authing**（国内社交与手机号成熟）

### 5.1 流程

1. `GET /auth/login?region=global|china&next=/...` → 302 到对应 OIDC Issuer（Authorization Code + **PKCE**）。
2. `GET /auth/oidc/callback?code=...&state=...` → ma3 用 code 换 token → 读 `id_token`（验签 Issuer JWKS）→ upsert `user:<sub>` → 写 **HttpOnly session cookie**（存 session id，**不**把原始 id_token 长期塞 cookie）。
3. 后续请求：`session` cookie → 服务端 session 表 → `ResolvedPrincipal`。

Session 表（或签名 session JWT，由 ma3 自己签发、短期有效）替代「把 IdP JWT 直接当 cookie」。

### 5.2 双区域 IdP 配置

| 线路 | 已确认 IdP | 环境变量前缀 |
|------|------------|--------------|
| **Global** | Clerk（默认）或 Auth0 | `MA3_OIDC_GLOBAL_*` |
| **China** | Authing（默认）或阿里云 IDaaS | `MA3_OIDC_CN_*` |

Social Login（Google、GitHub 等）**在 IdP 控制台配置**，ma3 **不**单独实现 `MA3_GOOGLE_CLIENT_ID` 等变量。

每条线路配置：

```bash
MA3_OIDC_GLOBAL_ISSUER_URL=https://xxx/.well-known/openid-configuration
MA3_OIDC_GLOBAL_CLIENT_ID=...
MA3_OIDC_GLOBAL_CLIENT_SECRET=...   # 或 PKCE public client 无 secret
MA3_OIDC_GLOBAL_REDIRECT_URI=https://ma3.example.com/auth/oidc/callback/global
```

登录页两个按钮：**Continue (International)** / **Continue (中国大陆)**。  
International 区 IdP Hosted UI 内展示 Google / GitHub / Email（与 GitHub.com 登录页类似的多选项，由 IdP 渲染）。

### 5.3 Agent 路径（不变）

- `X-API-Key` / `Bearer ma3v4_...` → `api_keys` + `api_key_grants`。
- **不**要求 Agent 走 OIDC。

### 5.4 平台运维

- `MA3_API_KEY` → `admin:root`（`/admin`、审计、手动调席位）。
- **删除** `MA3_AUTH_ADMIN_USERS`（原 zhilicon 用户名白名单）。

### 5.5 解析顺序

1. API key / admin key  
2. Session cookie  
3. `anonymous`（**无** public 库可读，除非平台显式创建公开示范库；对外 SaaS 默认匿名 **零库**）

---

## 6. 计费与席位（v4 闸门 + v4.0.1 支付）

### 6.1 产品规则（已确认）

| 档位 | `member_seat_limit` | 价格 |
|------|---------------------|------|
| **Free** | **1** | $0 |
| **Team** | 配置值，如 5 / 10 / 50 | 付费（Stripe 等，v4.0.1 接） |

- **API key 数量**、**library 数量** v4 可先软限制（配置默认），席位是 **硬限制**。
- 降配时：若当前成员数 > 新 limit，**拒绝降配** 直至 owner 移除多余成员。

### 6.2 API

| Method | Path | 说明 |
|--------|------|------|
| `GET` | `/v4/orgs/{org_id}/billing` | 当前 `plan_tier`、`member_seat_limit`、已用席位数、可用套餐 |
| `POST` | `/v4/orgs/{org_id}/billing/checkout` | 创建结账会话（Stripe Checkout URL）；owner only |
| `POST` | `/v4/webhooks/billing` | 支付成功 → 更新 `member_seat_limit`、`plan_tier` |

`POST .../members` 超额响应示例：

```json
{
  "error": "seat_limit_reached",
  "member_seat_limit": 1,
  "member_count": 1,
  "upgrade_url": "/orgs/acme/settings/billing"
}
```

HTTP 状态码：**402 Payment Required**。

### 6.3 Schema 增补

```sql
ALTER organizations ADD COLUMN plan_tier TEXT NOT NULL DEFAULT 'free';
ALTER organizations ADD COLUMN member_seat_limit INTEGER NOT NULL DEFAULT 1;

CREATE TABLE billing_events (
    event_id       TEXT PRIMARY KEY,
    org_id         TEXT NOT NULL REFERENCES organizations(org_id),
    provider       TEXT NOT NULL,          -- stripe | manual | ...
    event_type     TEXT NOT NULL,          -- checkout.completed | seat_limit.updated
    payload_json   JSONB NOT NULL DEFAULT '{}',
    created_at     TEXT NOT NULL
);
```

---

## 7. HTTP API（仅 `/v4/*`）

### 7.1 Organizations

| Method | Path | 权限 |
|--------|------|------|
| `POST` | `/v4/orgs` | 已登录 user；限流 |
| `GET` | `/v4/orgs` | 已登录 |
| `GET` | `/v4/orgs/{org_id}` | member+；含 `member_count`, `member_seat_limit` |
| `PATCH` | `/v4/orgs/{org_id}` | admin+ |
| `DELETE` | `/v4/orgs/{org_id}` | owner |

`POST /v4/orgs` body：`{slug, name, description?}` → 创建 org + 创建者 `owner`（占 1 席）。

### 7.2 Members

| Method | Path | 权限 |
|--------|------|------|
| `GET` | `/v4/orgs/{org_id}/members` | member+ |
| `POST` | `/v4/orgs/{org_id}/members` | admin+；**受席位限制** |
| `PATCH` | `/v4/orgs/{org_id}/members/{principal_id}` | admin+ |
| `DELETE` | `/v4/orgs/{org_id}/members/{principal_id}` | admin+；不可删唯一 owner |

邀请 body：`{email, org_role}` → 若 email 对应用户不存在，写 **待接受邀请**（v4.0.1）或要求对方先注册 OIDC 后再加 `principal_id`。

**v4 MVP 简化**：只支持 `{principal_id}` 或 `{email}` 搜索已注册用户；未注册用户显示「让对方先注册 ma3」。

### 7.3 Libraries / Access / Keys

与 rev 2 §6.3–6.5 相同；所有库操作校验调用者对 `library.organization_id` 的访问权。

### 7.4 Skill HTTP

| Method | Path |
|--------|------|
| `GET` | `/skill` |
| `GET` | `/skill/manifest.json` |
| `GET` | `/skill/files/{path}` |

**删除** `/client/*`。

### 7.5 Auth HTTP

| Method | Path |
|--------|------|
| `GET` | `/auth/login` |
| `GET` | `/auth/oidc/callback/{region}` |
| `GET` | `/auth/logout` |
| `GET` | `/v4/auth/whoami` |

---

## 8. Database schema（v4 仅）

在 rev 2 §7.1 基础上：

- `organizations.plan_tier`、`organizations.member_seat_limit`
- `principals.sso_user` 存展示用登录名；`metadata_json.idp_region`
- `sessions` 表（或等价）：`session_id`, `principal_id`, `expires_at`, `idp_region`
- `billing_events`（§6.3）
- **不创建**：`tokens`, `invite_codes`, `library_acl`, `role_assignments`, CephFS 相关配置表

知识表：`records`, `cases`, `relations`, `record_embeddings`, `search_*` 等同 rev 2。

---

## 9. MCP（envelope + ma3_skill）

与 rev 2 §8 相同；补充：

- `ma3_whoami` 返回 `organizations[].member_seat_limit` 与 `member_count`（便于 agent 提示用户升级）。
- `structuredContent.server` **不含**任何 zhilicon 域名。

---

## 10. 前端（GitHub 风格）

### 10.1 登录 / 注册

- 未登录 Dashboard：双按钮 OIDC（International / 中国大陆）。
- 注册即 OIDC 首登，**无**独立注册表单。

### 10.2 Org 与计费 UI

| 路径 | 说明 |
|------|------|
| `/orgs/new` | 自助建 org |
| `/orgs/:slug/settings/members` | 成员表；满员时「Invite」→ 计费页 |
| `/orgs/:slug/settings/billing` | 当前计划、席位数、升级 CTA |

满员邀请时展示：**「Free plan includes 1 member. Upgrade to invite teammates.」**

### 10.3 路由

与 rev 2 §9.2 相同；`/admin` 仅 `MA3_API_KEY` 平台运维。

---

## 11. 部署（公有云，无 CephFS / LTP）

对外 SaaS **默认拓扑**：

```text
[Cloud LB + TLS]
       │
[ma3 app: 4 vCPU / 8 GiB × 1~2]  ──embedding 开启──► sentence-transformers in-process
       │
       ├── [Managed PostgreSQL: 2~4 vCPU / 4~8 GiB / 50~100 GiB]
       ├── [Object storage: pg_dump + 日志归档]   ← 替代 CephFS 备份
       └── [OIDC: Clerk/Auth0 + 国内 IdP]       ← 独立 SaaS，不占 ma3 机器内存
```

| 组件 | 早期推荐 | 说明 |
|------|----------|------|
| 应用 | **4C8G** × 1（后加 LB + 副本） | `uvicorn --workers 2`；embedding 约占 1~1.5GiB |
| 数据库 | 托管 PG，与应用 **同区域** | 国内外客户若需合规，**数据区选客户主市场**或后期多区域部署 |
| 身份 | IdP **托管** | 不要把 Keycloak 和 embedding 挤在同一台 4C8G |
| 备份 | 云厂商 PG 自动备份 + 每日 `pg_dump` 到对象存储 | **删除** WAL→CephFS、op_log→CephFS 脚本依赖 |
| 密钥 | 环境变量 / 密钥管理服务 | `MA3_API_KEY`、OIDC secret、PG URL |

**删除的部署产物（代码清理项）：**

- `deploy/ltp/` 中 CephFS mount、PG archive 到 CephFS、`MA3_CEPHFS_*`、`MA3_OP_LOG_REALTIME_CEPHFS` 等 **不再作为 v4 官方路径**（目录可标 deprecated 或移除）。
- `AGENTS.md` LTP cutover 长清单 **由 v4 公有云部署文档替代**（实施时另写 `docs/v4/deploy-public-cloud.md`）。

**环境变量（认证相关，示例）：**

```bash
MA3_DATABASE_URL=postgresql://...
MA3_PUBLIC_BASE_URL=https://ma3.example.com
MA3_API_KEY=<platform-admin>

MA3_OIDC_GLOBAL_ISSUER_URL=...
MA3_OIDC_GLOBAL_CLIENT_ID=...
MA3_OIDC_GLOBAL_CLIENT_SECRET=...

MA3_OIDC_CN_ISSUER_URL=...
MA3_OIDC_CN_CLIENT_ID=...
MA3_OIDC_CN_CLIENT_SECRET=...

MA3_ORG_CREATE_RATE_LIMIT_PER_USER_PER_DAY=5
MA3_FREE_MEMBER_SEAT_LIMIT=1
```

**不设置** `MA3_AUTH_VERIFY_URL`、`MA3_AUTH_LOGIN_URL`（zhilicon）、`MA3_CEPHFS_*`。

---

## 12. 配置摘要

| 变量 | 默认 | 说明 |
|------|------|------|
| `MA3_FREE_MEMBER_SEAT_LIMIT` | `1` | 新 org 默认席位数 |
| `MA3_ORG_CREATE_RATE_LIMIT_PER_USER_PER_DAY` | `5` | 自助建 org 限流 |
| `MA3_OIDC_GLOBAL_*` / `MA3_OIDC_CN_*` | 必填（至少一条） | OIDC |
| `MA3_API_KEY` | 空 | 平台 break-glass |
| `MA3_ORG_SLUG_RESERVED` | `admin,api,...` | 保留 slug |

---

## 13. 实施顺序

1. Schema（含 org 席位、billing_events、sessions）  
2. OIDC 登录 + session；**删除** zhilicon verify 路径  
3. `/v4/orgs` 自助创建 + 席位 enforced `POST members`  
4. Resolver、library、api_key_grants  
5. MCP envelope + `ma3_skill` + `/skill/*`；删 `/client/*`  
6. 计费页 + checkout webhook 挂钩（可先 `manual` 提席位供内测）  
7. GitHub 风 UI + 双区登录  
8. E2E：单席 org 拒绝第二成员、付费后允许  
9. 清理：`deploy/ltp` CephFS 文档、zhilicon 测试 mock、v3 路由  

---

## 14. 风险

| 风险 | 缓解 |
|------|------|
| 双 IdP 维护成本 | MVP 可 Global 一条线 + China 稍后；登录页可隐藏未配置线路 |
| 单席 org 误以为是 bug | UI 与 402 文案明确「Free plan」 |
| 跨境数据合规 | 首期单区域 PG + 隐私政策；后期多区域再议 |
| embedding 内存 | 4C8G + workers=2 监控 OOM |

---

## 15. 成功标准

- 国外/国内用户均可 OIDC 登录、自助 `POST /v4/orgs`、建 library、签 key、MCP 读写。
- 免费 org **无法**添加第二名成员（402）；手动或 webhook 提高 `member_seat_limit` 后可加。
- 无 `auth.zhilicon.com`、无 CephFS 必需步骤的部署文档。
- MCP 每次返回 `server` 版本；`ma3_skill` 可升级 skill。
- 跨 org 搜索零泄漏（e2e）。

---

## 附录 A — `GET /v4/auth/whoami` 示例

```json
{
  "principal": {"principal_id": "user:auth0|abc123", "kind": "user", "display_name": "Alice"},
  "via": "session",
  "organizations": [
    {
      "org_id": "org_abc",
      "slug": "acme",
      "name": "Acme",
      "org_role": "owner",
      "plan_tier": "free",
      "member_seat_limit": 1,
      "member_count": 1
    }
  ],
  "libraries": [],
  "api_key": null
}
```

## 附录 B — 版本修订记录

| Rev | 变更 |
|-----|------|
| 1 | org + key grants + GitHub UI |
| 2 | 无兼容、admin key、删 `/client/*` |
| 3 | **对外 SaaS**；OIDC 双区；**席位计费**；删 zhilicon + CephFS/LTP |
| 3.1 | **IdP 锁定**：Clerk(Global) + Authing(China)；社交登录由 IdP 聚合 |
