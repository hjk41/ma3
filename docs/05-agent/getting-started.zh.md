# 自助注册与接入（Self-Service Onboarding）

> **ADR**：[ADR-011](../02-architecture/decisions/011-kb-access-and-org-isolation.md)（personal-dev 切片）  
> **前置**：[authorization-and-libraries.md](../03-backend/authorization-and-libraries.md)、[writes-audit-and-deletion.md](../03-backend/writes-audit-and-deletion.md)  
> **状态**：设计定稿（2026-07-04）；key 生命周期见 [api-keys-ui-and-api.md](../04-frontend/api-keys-ui-and-api.md)  
> **验收**：[acceptance-criteria.md](../08-quality/acceptance-criteria.md)（`v1-self-service-onboarding` 待迁入）

---

## 1. 目标

| 目标 | 说明 |
|------|------|
| **零管理员注册** | 新个人开发者从「发现 ma3」到「持有可用 API key」全程自助 |
| **首登自动建库** | Authing 首次登录即拥有 personal library（`kind=personal`），幂等 |
| **自助签发 key** | `/ui/keys/` 创建/列表/**删除** key；默认授权 = personal writer + `lib_default` writer |
| **明文可重展示** | 明文 key 加密存储（`key_ciphertext`），owner 可在列表/详情重复复制（见 design/14） |
| **最小 diff** | 复用 `ensure_library` / `insert_api_key` / `resolve_api_key`；v1 不引入完整 entitlement service |

**v1 切片 / v1.1 划分**：

- **v1**：首登自动建库 + `/api/keys` REST + `/ui/keys/` UI + friction #2/#3 快改 + 文档/部署更新
- **v1.1**：`ma3_create_key`/`ma3_list_keys` MCP 工具、自定义 grants 选择 UI、org 成员路径、entitlement 只读耦合、Stripe

---

## 2. 决策

### D1 — 首登钩子放在 Authing callback，按 owner 查找实现幂等

`ensure_personal_library(principal_id, display_name)` 在 `auth_callback` 里紧跟 `ensure_user_principal` 之后调用。

- **幂等键**：`(kind='personal', owner_principal_id)` — 先 `find_personal_library`，命中即返回
- 新建时 library_id：`lib_personal_{sha256(principal_id).hexdigest()[:12]}`
- 并发首登 PK 冲突 → except 后 re-find
- 兜底：`GET /ui/keys/` 与 `POST /api/keys` 也各调一次（lazy backfill）

### D2 — v1 key 创建只走 Observatory（Bearer session），MCP 签发缓期 v1.1

理由：Bearer 仅用于 UI；MCP 数据路径只认 `X-API-Key`；自举场景本来就需要人操作 UI；泄漏 key 的权限持久化攻击面需 entitlement 校验（Phase 3）。

### D3 — v1 grants：personal-dev 模板 + grant picker（design/14 演进）

创建 key 时默认 grants：

```python
[
    {"library_id": personal_lib_id, "role": "writer"},
    {"library_id": settings.default_library_id, "role": "writer"},
]
```

免费档 **Community Library writer 锁定**；付费 principal 可自定义 Community 为 reader。自定义 org 库 grants v1.1。

### D4 — 明文 key 存储与展示（design/14 修订）

- 创建时生成 plaintext，存 `key_hash` + Fernet `key_ciphertext`
- **列表/详情可重复展示** plaintext（decrypt 成功时）+ 复制按钮
- 无 ciphertext 的 legacy 行：只显示 prefix，引导「创建新 key 后删除旧 key」
- `GET /api/keys` 不含 hash/ciphertext 字段

### D5 — 删除 = 硬删行（design/14 覆盖早期「撤销」设计）

- 用户侧统一 **删除**，非「撤销/已撤销」
- `DELETE /api/keys/{key_id}` + `POST /ui/keys/{key_id}/delete`（SSR form）
- 删除 `api_key_grants` 后删除 `api_keys` 行；`write_audit_log` **不** cascade
- legacy `revoked_at` 行：列表过滤（`revoked_at IS NULL`），不参与配额，不可再认证
- **无** revoke 路由 410 bridge（未公网 launch）

### D6 — friction #2/#3 快改

- `confirmation` 缺省 → `agent_judged`，不再 400；schema description 明示「勿向用户索要」
- `ma3_report` 响应回显 `library_selection_reason`

---

## 3. 用户旅程

```mermaid
flowchart TD
  A[访问 ma3] --> B[/ui/keys/ 或顶栏 API Keys]
  B -->|无 session| C[302 /auth/login?next=/ui/keys/]
  C --> D[Authing 注册/登录]
  D --> E[/auth/callback: ensure_user_principal + ensure_personal_library]
  E --> F{display_name_locked?}
  F -->|否| G[/ui/me/setup/ 设定显示名]
  F -->|是| H[/ui/keys/ 列表]
  G --> H
  H --> I[创建 key → 复制 plaintext]
  I --> J[配置 MCP X-API-Key]
  J --> K[ma3_whoami + ma3_report]
```

---

## 4. 数据模型变更

**additive 列**：

```sql
ALTER TABLE api_keys ADD COLUMN key_prefix TEXT;
ALTER TABLE api_keys ADD COLUMN key_ciphertext TEXT;
```

**db.py helper**：

| 函数 | 说明 |
|------|------|
| `find_personal_library(owner_principal_id)` | 按 owner 查 personal 库 |
| `list_api_keys_for_principal(principal_id)` | 含 grants；**`AND revoked_at IS NULL`**；不含 hash |
| `delete_api_key(key_id, *, principal_id)` | 硬删 grants + key 行 |
| `update_api_key_label(...)` | 仅改 label |
| `count_active_api_keys(principal_id)` | 配额（`revoked_at IS NULL`） |

配置：`MA3_MAX_KEYS_PER_PRINCIPAL`，默认 **10**。

---

## 5. REST API

鉴权：Authing session（`_require_session`）；mutating 路由 same-origin；**不接受 X-API-Key**。

| 方法/路径 | 说明 |
|-----------|------|
| `GET /api/keys` | 列表；含 `plaintext_key`（decrypt 成功时） |
| `POST /api/keys` | 创建；响应含 `plaintext_key` |
| `PATCH /api/keys/{key_id}` | 改 label；JSON 超 120 字符 → **422**（SSR form 仍 truncate） |
| `DELETE /api/keys/{key_id}` | 硬删；非本人 → 404 |
| `POST /ui/keys/create` | SSR 创建 → 303 `/ui/keys/` |
| `POST /ui/keys/{key_id}/edit` | SSR 改 label + grants（详情页统一表单） |
| `POST /ui/keys/{key_id}/delete` | SSR 删除 → **始终** 303 `/ui/keys/`（无论 rowcount） |

---

## 6. MCP 变化（v1）

**不新增 MCP 签发工具**（D2）。既有工具增强：

- `ma3_report`：`library_selection_reason` + confirmation 默认化
- `ma3_whoami`：自然返回双库能力

**v1.1 预留**：`ma3_create_key`（grants ⊆ 调用者 key grants；dev bypass 禁用）、`ma3_list_keys`。

---

## 7. 错误与边界

| 场景 | 行为 |
|------|------|
| Authing 未配置 | `/ui/keys/`、`/api/keys` → **503**；dev 用 `MA3_DEV_AUTH=1` |
| 已有 personal lib（seed 建的） | 按 owner 复用，不改名 |
| 超配额 | 400：`active key limit reached; delete an old key first` |
| 删除后 MCP | `resolve_api_key` → None → 401 / -32001 |
| callback 建库失败 | **不阻断登录**；log error；`/ui/keys/` lazy 兜底 |
| **不做** `ma3_ui_session` 匿名 cookie 签 key | onboarding 安全约束 |

---

## 8. 文档与部署

`code/client/agent-onboarding.md`「API Key」小节重写为自助流程（浏览器 `/ui/keys/` → Authing → 复制 key → MCP 配置）。

deploy bundle **必须包含** `server/scripts/seed_personal_library_key.py`（Authing 不可用时的管理员兜底）。

---

## 9. 相关文档

| 文档 | 关系 |
|------|------|
| [api-keys-ui-and-api.md](../04-frontend/api-keys-ui-and-api.md) | key 删除/改名/布局真源 |
| [display-name-registration.md](../04-frontend/display-name-registration.md) | 首登 setup 门控 |
| [authorization-and-libraries.md](../03-backend/authorization-and-libraries.md) | ACL 全貌 |
| [writes-audit-and-deletion.md](../03-backend/writes-audit-and-deletion.md) | confirmation 语义 |
