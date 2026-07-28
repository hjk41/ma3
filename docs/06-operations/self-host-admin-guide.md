# 自托管管理员手册

面向**实例管理员**：从 Compose 部署，到首次初始化（Web / Agent），再到邀请同事入组并用 MCP 接入。

**相关文档**

| 文档 | 用途 |
|------|------|
| [self-hosting.md](self-hosting.md) | Compose 参数、安全、OIDC、排障细节 |
| [self-host-first-run-guide.md](self-host-first-run-guide.md) | 首次引导状态机与设计说明 |
| [api-overview.md](../03-backend/api-overview.md) | MCP vs REST 全路由表 |
| 实例上 `GET {BASE}/client/agent-onboarding.md` | 给普通 Agent 的接入说明 |

**支持**：社区 best-effort，无 SLA。

---

## 0. 你要达成的结果

```text
部署实例
  → 创建管理员账号 + API Key
  → 创建团队组织（+ 可选库）
  → 发邀请链接给同事（可预设组织内别名）
  → 同事注册自动入组、自建 Key、配置 MCP
  → （建议）关闭开放注册
```

原则：**知识环走 MCP**（`ma3_context` / `ma3_report` / `ma3_feedback`）；**账号 / 组织 / 邀请走 REST 或 Web**。

---

## 1. 部署

### 1.1 环境要求

- Docker + Docker Compose
- 能访问镜像仓库；若需下载 embedding 模型，容器需能访问 Hugging Face（或配置 `HTTP_PROXY` / `HTTPS_PROXY`）
- 局域网访问时，在 `.env` 里把 `MA3_PUBLIC_BASE_URL` 设成同事能打开的地址（例如 `http://192.168.x.x:8010`）

### 1.2 一键启动

```bash
git clone https://github.com/hjk41/ma3.git
cd ma3/deploy/self-host
cp .env.example .env
```

编辑 `.env`，至少修改：

| 变量 | 说明 |
|------|------|
| `POSTGRES_PASSWORD` | 数据库密码 |
| `MA3_API_KEY_ENCRYPTION_SECRET` | 用于加密门户 API Key 的长随机串 |
| `MA3_PUBLIC_BASE_URL` | 对外访问根 URL（邀请链接会用到） |
| `MA3_PORT` | 宿主机映射端口（默认 `8000`） |

然后：

```bash
./up.sh
./verify.sh
# 健康检查
curl -fsS "http://127.0.0.1:${MA3_PORT:-8000}/healthz"
```

`./up.sh` 成功后，浏览器可打开 `MA3_PUBLIC_BASE_URL`；若尚无账号，会进入首次设置。

### 1.3 部署后立刻要知道的两样东西

1. **Bootstrap API Key**（容器内文件）— 只能用于 **MCP 知识工具**，**不能**管理用户 / 完成 setup / 建组织：

   ```bash
   docker compose exec ma3 cat /data/bootstrap_api_key.txt
   ```

2. **本地账号体系**（默认开启）— 未配置 OIDC 时 `MA3_LOCAL_AUTH=1`：第一个注册用户是**实例管理员**。

> 不要把 bootstrap key 当分发账号；管理员请注册本地账号并 mint 自己的 API Key。

### 1.4 常用运维命令

```bash
cd ma3/deploy/self-host
docker compose ps
docker compose logs -f ma3
docker compose restart ma3
# 危险：删除数据卷
# docker compose down -v
```

备份卷：`ma3_pgdata`（数据库）、`ma3_data`（bootstrap key、HF 缓存）。

---

## 2. 初始化：Web 页面

适合人工点几下完成首次配置。

### 2.1 创建管理员

1. 打开 `MA3_PUBLIC_BASE_URL`（或 `/ui/setup/`）。
2. **创建管理员账号**（用户名 + 密码 + 显示名）。首个本地账号自动成为 admin。
3. 登录后按设置清单：
   - 到 `/ui/keys/` **签发 API Key**（给自己的 Agent 用）
   - 决定是否保持开放注册（局域网建议稍后关闭）
   - 点击 **完成引导**

### 2.2 创建组织与库

1. 打开 `/ui/orgs/` → **新建组织**（需实例管理员或付费计划允许；本地首管理员一般可建）。
2. 进入组织 → 可创建 **组织库**（默认 private）。
3. 打开 **成员** 页：可手动加人，或生成邀请（见 §4）。

### 2.3 管理员常用入口

| 页面 | 用途 |
|------|------|
| `/ui/setup/` | 首次引导 |
| `/ui/keys/` | 自己的 API Key |
| `/ui/orgs/` | 组织 / 库 / 成员 / 邀请 |
| `/ui/observatory/` | 观测台（产品管理员） |
| `/ui/observatory/local-users/` | 本地账号、开/关注册 |

---

## 3. 初始化：Agent / REST（无浏览器）

适合用 Cursor / 脚本把实例拉到「可邀请同事」状态。以下假设：

```bash
BASE=http://192.168.x.x:8010   # 改成你的 MA3_PUBLIC_BASE_URL
```

### 3.1 注册管理员并拿到 Key

```bash
curl -fsS "$BASE/api/setup/status" | jq

REGISTER=$(curl -fsS -X POST "$BASE/api/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{
    "username":"admin",
    "password":"change-me-long-password",
    "display_name":"Instance Admin",
    "api_key":{"label":"admin-agent"}
  }')
ADMIN_KEY=$(jq -r '.api_key.plaintext_key' <<<"$REGISTER")
echo "ADMIN_KEY=$ADMIN_KEY"
```

### 3.2 完成 setup

```bash
# 若暂时要靠「开放注册」拉人，可先 open:true；更推荐用邀请链接（§4），然后关闭注册
curl -fsS -X PATCH "$BASE/api/setup/registration" \
  -H "X-API-Key: $ADMIN_KEY" -H 'Content-Type: application/json' \
  -d '{"open":false}' | jq

curl -fsS -X POST "$BASE/api/setup/complete" \
  -H "X-API-Key: $ADMIN_KEY" | jq
```

### 3.3 创建组织与库

```bash
ORG=$(curl -fsS -X POST "$BASE/api/orgs" \
  -H "X-API-Key: $ADMIN_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"Acme Team"}')
ORG_ID=$(jq -r '.id' <<<"$ORG")

LIB=$(curl -fsS -X POST "$BASE/api/orgs/$ORG_ID/libraries" \
  -H "X-API-Key: $ADMIN_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"Eng Notes","visibility":"private"}')
LIB_ID=$(jq -r '.library_id' <<<"$LIB")
echo "ORG_ID=$ORG_ID LIB_ID=$LIB_ID"
```

### 3.4 把 Key 交给管理员自己的 Agent

配置 MCP（示例）：

- `MA3_BASE_URL=$BASE`
- `X-API-Key=$ADMIN_KEY`

验证：`ma3_whoami` → `ma3_context`（可先空查）→ 需要时再 `ma3_report`。

详细工具约定见实例 `GET $BASE/client/agent-onboarding.md`。

---

## 4. Onboard 其他成员（推荐：邀请链接）

**推荐路径**：邀请码/链接（关闭开放注册也能用）+ 可选**组织内别名**。

### 4.1 Web：生成邀请

1. 打开 `/ui/orgs/{组织}/members/`
2. 在 **邀请链接** 卡片中填写：
   - **组织内别名**（可选，例如「小明」— 对方入组后成员列表即显示）
   - 角色、可用次数（默认 1 次）、有效期（默认 168 小时）
3. **生成邀请**，复制页面上的 URL，发给同事（明文 token **只显示一次**）。

同事打开：

`{MA3_PUBLIC_BASE_URL}/auth/register?invite=ma3inv_…`

注册成功后会自动加入该组织；若设了别名，成员页立刻可见。

### 4.2 Agent / REST：生成邀请

```bash
INV=$(curl -fsS -X POST "$BASE/api/orgs/$ORG_ID/invites" \
  -H "X-API-Key: $ADMIN_KEY" -H 'Content-Type: application/json' \
  -d '{
    "role":"member",
    "max_uses":1,
    "expires_in_hours":168,
    "member_alias":"小明"
  }')
jq '{invite_url, token, member_alias, expires_at}' <<<"$INV"
```

把 `invite_url` 发给同事即可。

预览（公开）：

```bash
curl -fsS "$BASE/api/invites/preview?token=ma3inv_…" | jq
```

吊销：

```bash
curl -fsS -X DELETE "$BASE/api/orgs/$ORG_ID/invites/{invite_id}" \
  -H "X-API-Key: $ADMIN_KEY"
```

### 4.3 同事侧要做什么

1. 打开邀请链接 → 注册账号（关闭开放注册时，**只有有效邀请**能注册）。
2. 登录后到 `/ui/keys/` **创建自己的 API Key**（或注册时用 REST 带 `api_key`）。
3. 把 `MA3_BASE_URL` + 自己的 Key 配进 MCP。
4. 若需要写某个**私有组织库**，管理员还需授库权限（见下）。

已有账号也可兑换邀请（不新建账号）：

```bash
curl -fsS -X POST "$BASE/api/invites/redeem" \
  -H "X-API-Key: $USER_KEY" -H 'Content-Type: application/json' \
  -d '{"token":"ma3inv_…"}'
```

### 4.4 组织内别名

| 操作 | 方式 |
|------|------|
| 邀请时预设 | `member_alias` / 邀请表单「组织内别名」 |
| 事后修改 | `PATCH /api/orgs/{id}/members/{principal_id}` `{"alias":"…"}` |
| 查看 | `GET /api/orgs/{id}/members` 或成员页表格 |

别名只在**该组织内**显示，与全局显示名无关；同组织内别名不可重复。

### 4.5 给组织库授权（可选）

入组 ≠ 自动可写每个 private 库。需要时：

**Web**：库详情 → Grants。

**REST**：

```bash
curl -fsS -X POST "$BASE/api/libraries/$LIB_ID/grants" \
  -H "X-API-Key: $ADMIN_KEY" -H 'Content-Type: application/json' \
  -d '{"username":"alice","role":"writer"}'
```

### 4.6 备选：开放注册 + 手动加人

不推荐作为默认（局域网易被随意注册），但可用：

1. `PATCH /api/setup/registration` `{"open":true}` 或观测台打开注册。
2. 同事自行 `/auth/register`。
3. 管理员在成员页添加，或 `POST /api/orgs/{id}/members`（可带 `alias`）。
4. 人齐后 **关闭注册**。

---

## 5. 分工速查（避免用错 Key）

| 凭证 | 能做什么 | 不能做什么 |
|------|----------|------------|
| Bootstrap key | MCP 知识读写（若授权允许） | 管理用户、完成 setup、建 org、发邀请 |
| 管理员用户 API Key | Setup、本地用户、组织、邀请、库授权、自己的 keys | — |
| 普通用户 API Key | 自己的 keys、MCP（按其 grants）、兑换邀请 | 管理他人 / 发 org 邀请（非 org admin） |

---

## 6. 建议的安全清单

- [ ] `.env` 中密码与加密密钥已改成强随机值  
- [ ] `MA3_PUBLIC_BASE_URL` 指向真实可访问地址（邀请链接才正确）  
- [ ] 管理员已 mint **非 bootstrap** API Key  
- [ ] 主要用**邀请链接**拉人，人齐后 **关闭开放注册**  
- [ ] 未在公网裸奔：公网请上 TLS 反代（见 `deploy/self-host/Caddyfile.example`）  
- [ ] **不要**在公网开启 `MA3_DEV_AUTH`  
- [ ] 定期备份 `ma3_pgdata` / `ma3_data`

---

## 7. 故障速查

| 现象 | 排查 |
|------|------|
| `/healthz` 不通 | `docker compose ps` / `logs`；端口与防火墙 |
| 注册 403 | 开放注册已关且无有效邀请 |
| 邀请 410 | 过期、用尽或已吊销；重新生成 |
| 邀请链接域名不对 | 修正 `MA3_PUBLIC_BASE_URL` 后重新生成邀请 |
| bootstrap 调管理 API 403 | 换管理员用户 Key |
| 入组后 MCP 看不到某库 | 检查 library grants / key grants |
| embedding 卡住 | 代理、`MA3_DISABLE_EMBEDDINGS=1`（弱机器） |

更细的 Compose / OIDC 说明见 [self-hosting.md](self-hosting.md)。
