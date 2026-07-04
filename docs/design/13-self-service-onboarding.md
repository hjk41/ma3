# 13 — 自助注册与接入（Self-Service Onboarding）

> **ADR**：[ADR-011](../adr/011-kb-access-and-org-isolation.md)（Phase 5 的 personal-dev 切片）  
> **前置**：08-kb-access（api_keys/api_key_grants 已落库）、10-write-audit（report_kind/confirmation）  
> **驱动**：[v1-personal-developer-journey.md](../acceptance/v1-personal-developer-journey.md) friction #1（major）、#2、#3、#5  
> **状态**：设计定稿（2026-07-04）；作者 fable

---

## 1. 目标

| 目标 | 说明 |
|------|------|
| **零管理员注册** | 新个人开发者从「发现 ma3」到「持有可用 API key」全程自助，不再依赖管理员跑 `seed_personal_library_key.py` |
| **首登自动建库** | Authing 首次登录即拥有 personal library（`kind=personal`，`owner_principal_id=user:<sub>`），幂等 |
| **自助签发 key** | Observatory `/ui/keys/` 创建/列表/撤销 key；默认授权 = seed 脚本同款（personal writer + `lib_default` writer） |
| **明文一次性** | 明文 key 仅创建响应展示一次；库中只存 SHA-256 hash |
| **最小 diff** | 复用 `ensure_library` / `insert_api_key` / `resolve_api_key` 现有函数；不引入 entitlement service（Phase 3 仍缓期） |

**v1 切片 / v1.1 划分**（详见 §12）：

- **v1 切片（本文交付）**：首登自动建库 + `/api/keys` REST + `/ui/keys/` UI + friction #2/#3 快改 + 文档/部署更新
- **v1.1（显式缓期）**：`ma3_create_key`/`ma3_list_keys`/`ma3_revoke_key` MCP 工具、自定义 grants 选择 UI、org 成员路径（Phase 4）、entitlement 只读耦合（Phase 3）、Stripe（ADR-012）

---

## 2. 现状与差距

| 现状（代码，2026-07-04） | 差距 |
|--------------------------|------|
| `routes_auth.py` Authing login/callback 可用；callback 调 `ensure_user_principal(user)` upsert principal | callback 不建 personal library |
| `scripts/seed_personal_library_key.py`：principal + personal lib + 双 grant key，但需管理员在**源码 checkout** 里对生产 DB 执行 | 202 部署树无此脚本（friction #5）；明文 key 需带外传递 |
| `db.ensure_library(kind=, owner_principal_id=)` 幂等；`db.insert_api_key(grants=)`、`db.upsert_api_key_grant` 就绪 | 无「按 owner 查 personal lib」「按 principal 列 key」「revoke key」的 db helper |
| `api_key_service.resolve_api_key`：hash 查表、revoked/expired 拒绝、grants 展开能力集 | 无签发路径（除脚本/测试直插） |
| Observatory `/ui/observatory/` 有 Authing session（`resolve_session_user`） | `/ui/keys` 404；无任何 key 管理 REST |
| `api_keys` 表：`key_id, key_hash, principal_id, label, created_at, created_by, last_used_at, expires_at, revoked_at` | 缺 `key_prefix` 展示列（design-08 §4.2 规划过，未落地） |
| `client/agent-onboarding.md`：「生产由管理员发放」一句话 | 无自助获取 key 的流程描述 |
| acceptance friction #2：`confirmation` 缺省时 agent 误以为服务端强制用户确认，headless 写入死锁 | schema description / policy 未说明该字段非门禁 |
| acceptance friction #3：`ma3_report` 响应只回 `library_id`，不解释为何选中该库 | 需回显 `library_selection_reason` |

---

## 3. 决策

### D1 — 首登钩子放在 Authing callback，按 owner 查找实现幂等

`ensure_personal_library(principal_id, display_name)` 在 `auth_callback` 里紧跟
`ensure_user_principal` 之后调用（`code/server/app/api/routes_auth.py` L62）。

- **幂等键不是 library_id，而是 `(kind='personal', owner_principal_id)`**：先
  `db.find_personal_library(principal_id)`，命中即返回；未命中才 create。这样
  seed 脚本历史建的库（如 `lib_personal_nova`，id 非规范格式）会被复用，**不会重复建库**，
  也天然完成存量 principal 的 backfill（下次登录即补齐，无需批量迁移脚本，见 §9 迁移）。
- 新建时 library_id 取**确定性 id**：`f"lib_personal_{sha256(principal_id).hexdigest()[:12]}"`，
  并发首登时第二个 INSERT 撞 PK 冲突则重查返回（try/except 后 re-find），仍幂等。
- 兜底：`GET /ui/keys/` 与 `POST /api/keys` 也各调一次 `ensure_personal_library`
  （lazy backfill，防 callback 之后才加此逻辑的旧 session）。

**为何不放 `resolve_session_user`**：那是每请求都走的热路径；callback 每次登录仅一次，
且已有 DB 写（principal upsert），加一次 SELECT 成本可忽略。

### D2 — v1 key 创建只走 Observatory（Bearer session），MCP `ma3_create_key` 缓期到 v1.1

理由（回应任务书第 3 点）：

1. **ADR-011 决策 2**：Bearer 仅用于 Observatory 人类登录与 key 管理；MCP 数据路径只认
   `X-API-Key`。若 v1 就给 MCP 加 `ma3_create_key`，则一把泄漏的 agent key 可**再造 key**
   （权限持久化攻击面），而「新 key grants ⊆ 调用者 entitlement」的校验依赖 Phase 3
   entitlement service——正是本切片显式排除的部分。
2. 接入的第一步本来就是**人**把明文 key 抄进 MCP 配置（agent-onboarding.md），
   自举场景里 agent 还没有 key，MCP 工具帮不上；UI 才是正确入口。
3. v1.1 加 `ma3_create_key` 时约束已明确：调用者须是 DB key（非 dev bypass 除外），
   owner 同 principal，新 key grants ⊆ 调用者现有 grants（无需 entitlement service 也可先做
   「⊆ 调用者 key grants」这一更严子集）。

### D3 — v1 不开放自定义 grants：固定「personal-dev 模板」

`POST /api/keys` 只接受 `label`（可选 `expires_at`）。grants 固定为：

```python
[
    {"library_id": personal_lib_id, "role": "writer"},
    {"library_id": settings.default_library_id, "role": "writer"},
]
```

与 `seed_personal_library_key.py` 默认行为完全一致（`--public-role writer`）。
不做勾选 UI ⇒ 不需要 entitlement/只读耦合校验（design-08 §5.1 属 Phase 3），
且天然满足「贡献优先」：社区库必带写。自定义 grants（org 库、reader 角色）留给 v1.1。

### D4 — 明文 key 只出现在 `POST /api/keys` 的直接响应里

- 响应体含 `plaintext_key`；UI 在 POST 的返回页渲染一次（**不做** POST-redirect-GET，
  刷新即失去明文，页面明示「离开本页后无法再次查看」）。
- `GET /api/keys` 与列表页永不含明文与 hash；仅 `key_prefix`（明文前 12 字符，
  如 `ma3k_a1b2c3`）、label、grants 摘要、created/last_used/revoked。
- 新增 `api_keys.key_prefix` 列（additive；旧行 NULL，UI 回退显示 `key_id`）。

### D5 — 撤销 = 置 `revoked_at`，owner-only，不删行

复用 `resolve_api_key` 已有的 revoked 拒绝逻辑；审计留痕（application log +
行保留）。不做恢复；误撤销就再建一把。

### D6 — friction #2/#3 作为本切片的顺手快改（quick wins）

行为极小 diff，见 §10：`confirmation` 缺省不再 400（补默认 `agent_judged`）+
schema description 明示「勿向用户索要」；`ma3_report` 响应回显
`library_selection_reason`。

---

## 4. 目标用户旅程（from zero）

```mermaid
flowchart TD
  A[访问 http://192.168.31.202:8000] --> B[/ui/keys/ 或 Observatory 导航]
  B -->|无 session| C[302 /auth/login?next=/ui/keys/]
  C --> D[Authing 注册/登录]
  D --> E[/auth/callback: ensure_user_principal + ensure_personal_library/]
  E --> F[/ui/keys/ 列表页: 0 keys/]
  F --> G[填 label 提交 POST /api/keys]
  G --> H[创建页: 明文 key 展示一次 + 复制按钮]
  H --> I[按 agent-onboarding.md 配 MCP X-API-Key]
  I --> J[ma3_whoami: 2 libraries; ma3_report 缺省写 personal]
```

与 seed 脚本产物逐项等价：principal 行、`kind=personal` 库、双 writer grant key —
仅签发人由管理员变为用户本人。

---

## 5. 数据模型变更

**仅一处 additive 列**（沿用 `initialize_database()` 内 `_column_exists` + `ALTER TABLE` 既有模式，
参照 `libraries.kind` 的加列写法，SQLite/Postgres 通用）：

```sql
ALTER TABLE api_keys ADD COLUMN key_prefix TEXT;   -- 明文前 12 字符，仅展示用
```

无新表。personal library 复用 `libraries.kind/owner_principal_id`（已存在）。

**db.py 新增 helper**（`code/server/app/storage/db.py`）：

| 函数 | 签名 | 说明 |
|------|------|------|
| `find_personal_library` | `(owner_principal_id: str) -> dict \| None` | `SELECT ... FROM libraries WHERE kind='personal' AND owner_principal_id=? ORDER BY id LIMIT 1` |
| `list_api_keys_for_principal` | `(principal_id: str) -> list[dict]` | 含 grants 子查询聚合；**不含** `key_hash` |
| `revoke_api_key` | `(key_id: str, *, principal_id: str) -> bool` | `UPDATE api_keys SET revoked_at=now WHERE key_id=? AND principal_id=? AND revoked_at IS NULL`；返回是否命中 |
| `count_active_api_keys` | `(principal_id: str) -> int` | 配额检查（§9） |

`insert_api_key(...)` 增加可选参数 `key_prefix: str | None = None`。

---

## 6. 服务与 REST API

### 6.1 `app/services/onboarding_service.py`（新文件）

```python
PERSONAL_LIB_PREFIX = "lib_personal_"

def personal_library_id(principal_id: str) -> str:
    return PERSONAL_LIB_PREFIX + hashlib.sha256(principal_id.encode()).hexdigest()[:12]

def ensure_personal_library(principal_id: str, display_name: str) -> dict[str, Any]:
    """Idempotent: find by (kind=personal, owner) first; create deterministically otherwise."""
    existing = db.find_personal_library(principal_id)
    if existing:
        return existing
    try:
        return db.ensure_library(
            personal_library_id(principal_id),
            name=f"{display_name} 的个人库",        # design-10 §3 命名规范
            visibility="private",
            kind="personal",
            owner_principal_id=principal_id,
        )
    except Exception:                              # 并发首登 PK 冲突
        found = db.find_personal_library(principal_id)
        if found:
            return found
        raise

def create_personal_dev_key(principal_id: str, display_name: str, *, label: str) -> dict[str, Any]:
    """Personal-dev template key: writer on personal lib + writer on lib_default. Returns plaintext ONCE."""
    lib = ensure_personal_library(principal_id, display_name)
    if db.count_active_api_keys(principal_id) >= settings.max_keys_per_principal:
        raise HTTPException(status_code=400, detail="active key limit reached; revoke an old key first")
    plaintext = f"ma3k_{secrets.token_hex(16)}"
    key_id = f"key_{secrets.token_hex(6)}"
    db.insert_api_key(
        key_id=key_id,
        key_hash=api_key_service.hash_key(plaintext),
        key_prefix=plaintext[:12],
        principal_id=principal_id,
        label=label,
        created_by=principal_id,
        grants=[
            {"library_id": lib["library_id"], "role": "writer"},
            {"library_id": settings.default_library_id, "role": "writer"},
        ],
    )
    return {"key_id": key_id, "plaintext_key": plaintext, "key_prefix": plaintext[:12],
            "personal_library": lib, "grants": [...]}
```

配置新增：`Settings.max_keys_per_principal`（env `MA3_MAX_KEYS_PER_PRINCIPAL`，默认 **10**，
只数 `revoked_at IS NULL` 的）。

### 6.2 首登钩子（`routes_auth.py` 最小 diff）

```python
# auth_callback(), 现 L62 之后：
principal = ensure_user_principal(user)
ensure_personal_library(principal["principal_id"], user.display_name)
```

`ensure_user_principal` 已返回含 `principal_id` 的 dict（`db.upsert_user_principal`）。

### 6.3 `app/api/routes_keys.py`（新文件，`main.py` 注册 router）

鉴权统一走 `_require_session(request) -> SessionUser`：`resolve_session_user()` 为 None →
API 路径 401 JSON；UI 路径 302 到 `/auth/login?next=/ui/keys/`。**不接受 X-API-Key**（D2）。

| 方法/路径 | 请求 | 响应 | 说明 |
|-----------|------|------|------|
| `GET /api/keys` | — | `{"keys": [{key_id, key_prefix, label, grants, created_at, last_used_at, revoked_at}]}` | 仅本人的；含已撤销（标记） |
| `POST /api/keys` | `{"label": "my-laptop-agent"}` | 上表 + **`plaintext_key`（仅此一次）** | label 缺省 `"agent-key"`；配额超限 400 |
| `POST /api/keys/{key_id}/revoke` | — | `{"revoked": true}` | 非本人/不存在 → 404（不泄漏他人 key_id 存在性） |

撤销用 POST 而非 DELETE：UI 是无 JS 的服务端渲染表单（与 `/ui/observatory` 的 feedback
表单同款模式），HTML form 不支持 DELETE。

### 6.4 UI 页面（同文件 `routes_keys.py`，复用 routes_ui.py 的内联样式）

- `GET /ui/keys/` — 列表 + 内联创建表单
- `POST /ui/keys/create` — 表单端点，调 `create_personal_dev_key`，渲染一次性明文页
- `POST /ui/keys/{key_id}/revoke` — 表单端点，重定向回列表

`/ui/observatory/` 顶部导航加一个「API Keys」链接。

---

## 7. UI 线框

```text
┌─ /ui/keys/ ──────────────────────────────────────────────┐
│ ma3 · API Keys                    张三 (user:abc) · 退出登录 │
│                                                          │
│ 个人库：lib_personal_3f2a9c1b04d7 「张三 的个人库」(private) │
│                                                          │
│ ┌ 创建新 key ─────────────────────────────┐              │
│ │ Label: [my-laptop-agent      ] [创建]   │              │
│ │ 授权（固定）：个人库 writer + Community  │              │
│ │ Library writer                          │              │
│ └─────────────────────────────────────────┘              │
│                                                          │
│ Prefix        Label        Grants      Created    状态    │
│ ma3k_a1b2c3…  laptop-agent personal+   07-04     [撤销]  │
│                            community                     │
│ ma3k_ffee00…  old-key      personal+   07-01     已撤销   │
│                            community    (revoked 07-03)  │
└──────────────────────────────────────────────────────────┘

┌─ POST /ui/keys/create 响应页（一次性）────────────────────┐
│ ✔ Key 已创建                                             │
│                                                          │
│ ┌──────────────────────────────────────────────┐         │
│ │ ma3k_9f8e7d6c5b4a3210fedcba9876543210        │ [复制]  │
│ └──────────────────────────────────────────────┘         │
│ ⚠ 这是唯一一次显示明文。离开本页后只能看到前缀             │
│   ma3k_9f8e7d6c…；丢失请撤销后重建。                      │
│                                                          │
│ 下一步：打开 /client/agent-onboarding.md，把上面的 key     │
│ 填入你的 agent MCP 配置（X-API-Key）。                     │
│                                        [← 返回 key 列表] │
└──────────────────────────────────────────────────────────┘
```

登录跳转：无 session 访问 `/ui/keys/` → `302 /auth/login?next=/ui/keys/`（`auth_login`
已支持任意 `/` 开头的 `next`）。

---

## 8. MCP 变化

**v1 切片：不新增 MCP 工具**（D2）。相关的既有工具增强：

- `ma3_whoami`：无需改——新 key 解析后已自然返回双库能力与
  `library_selection.default_write_behavior`。
- `ma3_report`：响应增加 `library_selection_reason`（§10.2，friction #3）。
- `Ma3ReportPayload.confirmation` description 改写（§10.1，friction #2）。

**v1.1 预留**（写入 backlog，不在本切片验收）：`ma3_create_key`（payload：`label`,
可选 `expires_at`；grants ⊆ 调用者 key 的现有 grants；owner 同 principal；dev bypass 禁用此工具
以免造出无主 key）、`ma3_list_keys`、`ma3_revoke_key`。

---

## 9. 错误与边界

| 场景 | 行为 |
|------|------|
| Authing 未配置（纯 LAN dev） | `/ui/keys/` 与 `/api/keys` 返回 **503** + 提示页：「本实例未启用自助注册；dev 环境用 `MA3_DEV_AUTH=1` + `MA3_DEV_API_KEY`（既有 break-glass），或由管理员跑 seed 脚本」。**不做** `ma3_ui_session` 匿名 cookie fallback（feedback 的那套仅适合低危投票，签 key 绝不行） |
| 已有 personal lib（seed 建的 / 上次登录建的） | `find_personal_library` 按 owner 命中即复用；不比对 id、不改名（用户可能已自定义） |
| 并发首登双写 | 确定性 id 撞 PK → except 后 re-find 返回（§6.1） |
| 超配额 | `count_active_api_keys >= max_keys_per_principal`（默认 10）→ 400 明确提示先撤销 |
| 撤销后 MCP 调用 | 既有行为：`resolve_api_key` 返回 None → 401 / -32001，无需改动 |
| 明文丢失 | 无找回；列表页文案引导撤销重建 |
| Authing callback 中 `ensure_personal_library` 抛异常 | **不阻断登录**：try/except + log error（登录成功比建库重要；`/ui/keys` 的 lazy 兜底会重试） |

### 迁移 / 存量数据

- **存量 principal 无 personal lib**：无批量脚本。下次 Authing 登录（callback 钩子）或首次访问
  `/ui/keys/`（lazy 兜底）自动补建。202 上现有 `user:nova-dev` / `user:eval-admin` 已有库，会被
  owner 查找直接复用。
- **存量 api_keys 行 `key_prefix` NULL**：不回填（明文已不可得）；UI 显示 `key_id` 代替。
- **schema**：仅 §5 的一条 additive ALTER，随 `initialize_database()` 幂等执行，SQLite/Postgres 双路径。

---

## 10. 顺手快改（acceptance friction #2 / #3）

### 10.1 `confirmation` 明确为「非门禁元数据」（friction #2）

问题：`write_audit_service.resolve_report_write_plan` 在**显式传了 `report_kind`（supplement/new）
但缺 `confirmation`** 时 400（L47–48）；加上字段无 description，驱动模型在 headless 会话里
停下来向用户索要确认，第一次写入直接丢失。

改动（两处，均最小 diff）：

1. `write_audit_service.py` L47–48：删除该 400，改为
   `confirmation = payload.confirmation or "agent_judged"`（与 `report_kind` 缺省时的既有
   默认路径对齐；`_VALID_CONFIRMATIONS` 白名单校验保留）。
2. `models/mcp_payloads.py` `Ma3ReportPayload.confirmation` 加 description：

   > "Optional audit metadata, never a gate: how the write was confirmed
   > (`user_confirmed` | `agent_judged`). Omit to default to `agent_judged`.
   > Do NOT stop to ask the user for this value."

   同步更新 `client/templates/ma3-agent-policy.mdc` §3 措辞（「confirmation 可省略，服务端不
   要求用户确认」）。policy/manifest 变更 → bump `skill_bundle_version`（Scheme B 常规流程）。

### 10.2 回显 `library_selection_reason`（friction #3）

`ReportWritePlan` 增加 slot `selection_reason: str`，`resolve_report_write_plan` 各分支填值：

| 分支 | reason |
|------|--------|
| verify/refute 跟随 target record 所在库 | `verify_target_library` |
| payload 显式 `library_id` | `explicit_library_id` |
| DB key 单一 personal 库缺省 | `default_owned_personal_library` |
| legacy/dev bypass 走 `lib_default` | `legacy_default_library` |

`mcp_tool_service.py` 的 `ma3_report` 三个响应分支（dry_run L447、replay L497、正常 L536）统一加：

```python
"library_selection_reason": write_plan.selection_reason,
```

Agent（和它背后的人）由此能立即发现「本想投社区却进了私库」或反向错置。

---

## 11. 文档与部署更新

### 11.1 `code/client/agent-onboarding.md`

「API Key」小节（现 L219–224）重写为：

```markdown
## API Key（自助获取）

1. 浏览器打开 `http://<ma3-host>:8000/ui/keys/`，用 Authing 注册/登录
2. 首次登录自动获得个人库；填 label 点「创建」
3. **立即复制**明文 key（只显示一次），填入你的 MCP 配置 `X-API-Key`
4. 默认授权：你的个人库 writer + Community Library writer
   - `ma3_report` 不带 `library_id` → 写入你的个人库
   - 写社区库 → 显式 `library_id: "lib_default"`
- LAN dev 实例仍可用 `ma3dev`（`MA3_DEV_AUTH=1` break-glass）
- key 丢失/泄漏：回 `/ui/keys/` 撤销并重建
```

「给用户的简短说明」段同步把「提供 API key」改为「或引导用户到 `/ui/keys/` 自助创建」。

### 11.2 部署（friction #5）

- deploy bundle（202 的发布产物）**必须包含 `server/scripts/`**（至少
  `seed_personal_library_key.py`，作为 Authing 不可用时的管理员兜底），消除「注册代码与运行
  服务版本漂移」。落点：打包脚本/部署 profile 文档加一行 include；本设计验收时在 202 上
  `ls /home/hct/ma3/server/scripts/` 应能看到脚本。
- `healthz` / doctor 无需新字段；`/ui/keys/` 本身就是可探测的注册端点。

---

## 12. 分阶段实现

### Phase O1 — 建库钩子与存储（v1 切片）

1. `db.py`：`key_prefix` 加列 + 4 个 helper（§5）；`insert_api_key` 加 `key_prefix` 参数
2. `services/onboarding_service.py`：`personal_library_id` / `ensure_personal_library` / `create_personal_dev_key`
3. `routes_auth.py` callback 钩子（try/except 不阻断登录）
4. `config.py`：`max_keys_per_principal`

**验收**：unit tests 过（§13）；重复登录不重复建库；对既有 seed 库幂等。

### Phase O2 — REST + UI（v1 切片）

1. `api/routes_keys.py`：`/api/keys` 三端点 + `/ui/keys/` 三页面；`main.py` 注册
2. `/ui/observatory/` 导航加链接
3. 撤销/创建写 application log（who/key_id/grants）

**验收**：无 session → 401/302；创建→明文一次；列表无明文/hash；撤销后 MCP 401。

### Phase O3 — 快改 + 文档（v1 切片）

1. §10.1 confirmation 默认化 + description + policy 措辞（bump skill_bundle_version）
2. §10.2 `library_selection_reason` 回显
3. §11 onboarding 文档改写 + deploy bundle 含 scripts
4. 更新 `05-doc-code-mapping.md`

**验收**：全 suite 绿；`ma3_report` 无 confirmation 无 library_id 直接成功且 reason=`default_owned_personal_library`。

### v1.1（缓期，另立任务）

- `ma3_create_key` / `ma3_list_keys` / `ma3_revoke_key` MCP（约束见 §8）
- 创建 key 时自定义 grants（勾选库、reader 角色）→ 依赖 Phase 3 entitlement
- org 成员/org 库路径（Phase 4）、`expires_at` UI、key 轮换

---

## 13. 测试计划

**Unit**（`tests/unit/test_onboarding_service.py` 新增）：

- `ensure_personal_library` 两次调用 → 同一 library_id，libraries 表恰 1 行
- 已存在 seed 风格库（非规范 id，owner 匹配）→ 复用，不新建、不改名
- `create_personal_dev_key` → api_keys 1 行 + api_key_grants 2 行（personal writer、lib_default writer）；`key_prefix == plaintext[:12]`；hash 可被 `resolve_api_key` 解析出双库 writable
- 配额：建到 max 后第 max+1 次 400；撤销一把后可再建
- `revoke_api_key` 他人 principal → False/404 语义

**Integration**（`tests/integration/test_self_service_onboarding.py` 新增；沿用
`test_mcp_integration.py` 的 isolated DB fixture + FastAPI TestClient，Authing 用
session/`resolve_session_user` monkeypatch 模拟登录态）：

1. 模拟 callback（直接调 `ensure_user_principal` + 钩子）→ principal + personal lib 存在
2. 无 session `GET /api/keys` → 401；`GET /ui/keys/` → 302 login
3. 有 session `POST /api/keys` → 200 含 `plaintext_key`；随后 `GET /api/keys` 响应体 **grep 无明文、无 hash**
4. 用返回明文走 MCP：`ma3_whoami` readable/writable = {personal, lib_default}；`ma3_report`（无 library_id、无 confirmation）→ 落 personal lib、`confirmation=agent_judged`、`library_selection_reason=default_owned_personal_library`；显式 `lib_default` → reason=`explicit_library_id`
5. `POST /api/keys/{id}/revoke` → 后续 MCP 调用 401/-32001
6. Authing 未配置 → `/api/keys` 503
7. 既有全 suite（155+）保持绿；friction #2 回归：显式 `report_kind=new` 且无 confirmation 不再 400

---

## 14. 验收标准（fable 后续 acceptance run，from-zero 版）

在 202 部署（Postgres + Authing）上，用一个**全新** Authing 账号，全程不动用管理员：

| # | 步骤 | 通过条件 |
|---|------|----------|
| A1 | 浏览器 `/ui/keys/` → Authing 注册新账号 → 回跳 | 登录成功回到 `/ui/keys/`；`principals` 有新行 |
| A2 | DB 校验 | `libraries` 恰 1 行 `kind=personal, owner_principal_id=user:<sub>`；再次登出登录后行数不变 |
| A3 | UI 创建 key | 明文 `ma3k_` 前缀展示一次；刷新后仅剩 prefix；`api_keys` 1 行（有 `key_prefix`）+ `api_key_grants` 2 行 writer |
| A4 | 用该 key 走 agent-onboarding.md bootstrap | `tools/list` 正常；`ma3_whoami` 双库 |
| A5 | `ma3_report` 无 `library_id` 无 `confirmation`（headless） | 一次成功；落 personal lib；响应含 `confirmation: agent_judged` 与 `library_selection_reason: default_owned_personal_library`；audit 行归属正确 |
| A6 | `ma3_report` 显式 `lib_default` | 落社区库；reason=`explicit_library_id` |
| A7 | UI 撤销该 key → 重试 MCP | 401 / -32001 |
| A8 | 配额 | 建满 10 把后第 11 把被 400 拒绝 |
| A9 | 隔离复核 | 另一账号的 key 读不到新账号 personal lib（复刻上轮 acceptance §5 探针） |
| A10 | 部署树 | `/home/hct/ma3/server/scripts/seed_personal_library_key.py` 存在（管理员兜底可用） |

全部通过 ⇒ acceptance friction #1、#2、#3、#5 关闭；journey 首步不再依赖管理员。

---

## 15. 开放问题（v1.1+）

| 项 | 说明 |
|----|------|
| email 验证 / 反滥用 | 现在「能过 Authing 即可发 key」；公网部署需 Authing 侧开启邮箱验证 + 服务端限速（每 principal 每小时 N 次创建） |
| key 过期策略 | `expires_at` 列已在，UI 不暴露；是否默认 90 天轮换 |
| `ma3_create_key` 的 dev bypass 语义 | bypass 是无 principal 的 admin，全禁還是允许指定 owner？倾向 v1.1 直接禁 |
| personal lib 命名冲突 | display_name 重名导致库名相同（id 不同）；仅展示层问题，是否加后缀 |
| 配额与 ADR-012 | `max_keys_per_principal` 迁移为 plan 维度配额（09-billing Phase B） |
| 首登欢迎页 | callback 后直接 302 `/ui/keys/`（带「创建第一把 key」引导）还是保持 next 语义不变（v1 选后者） |

---

## 16. 相关文档

| 文档 | 关系 |
|------|------|
| [ADR-011](../adr/011-kb-access-and-org-isolation.md) | Phase 5 key 管理决策；本文是其 personal-dev 切片 |
| [08-kb-access-and-org-isolation.md](08-kb-access-and-org-isolation.md) | api_keys/grants schema、Phase 3/4/5 全貌 |
| [10-write-audit-and-delete.md](10-write-audit-and-delete.md) | confirmation 语义、personal 库命名 |
| [11-mcp-error-contract.md](11-mcp-error-contract.md) | 结构化错误（library_selection 400 已遵循） |
| [acceptance/v1-personal-developer-journey.md](../acceptance/v1-personal-developer-journey.md) | friction #1/#2/#3/#5 驱动本设计 |
| [ADR-012](../adr/012-billing-and-quotas.md) | 缓期：付费/配额 |
| `client/agent-onboarding.md` | §11.1 改写对象 |
