# 14 — API Key 生命周期管理

> **ADR**：[ADR-011](../02-architecture/decisions/011-kb-access-and-org-isolation.md)  
> **前置**：[13-self-service-onboarding.md](../05-agent/getting-started.md)  
> **状态**：定稿（2026-07-04）；验收见 [acceptance-criteria.md](../08-quality/acceptance-criteria.md)（`v1-api-key-lifecycle` 待迁入）

---

## 1. 目标与非目标

### 目标

| 目标 | v1 决定 |
|------|---------|
| 自助管理 | Authing 登录后在 `/ui/keys/` 管理自己的 key |
| **删除** 替代撤销 | UI/REST 统一 **删除**；用户视角 key 立即失效且不可恢复 |
| Grants 可理解 | 创建时 grant picker：personal + Community，各 `reader`/`writer`/`none`；免费档 Community writer 锁定 |
| 复制便利 | 列表/详情展示完整 key（`key_ciphertext` decrypt 成功时）+ 复制按钮 |
| 安全边界 | mutating 路由须 Authing session + same-origin；MCP/API-key auth **不能** 管理 key |
| 小 diff | 复用现有表结构 + SSR 路由模式 |

### 非目标（v1）

- Org admin key 管理（v1.1+）
- Key 轮换工作流（v1：建新 key → 更新配置 → 删旧 key）
- 过期策略 UI（`expires_at` 列在，UI 不暴露）
- 创建后改 grants（v1：建新 key 再删旧 key）
- 删除后恢复

---

## 2. 操作目录

| 操作 | v1 | UI | REST |
|------|-----|-----|------|
| Create | ✅ | `/ui/keys/` 表单 + grant picker | `POST /api/keys` |
| View/List | ✅ | 表格 | `GET /api/keys` |
| Copy | ✅ | `ma3CopyFrom` + hidden/offscreen input | 列表响应 `plaintext_key` |
| **Delete** | ✅ | 行内 `删除` + confirm | `DELETE /api/keys/{key_id}` + `POST /ui/keys/{id}/delete` |
| Rename | ✅ | 详情页统一表单 | `PATCH /api/keys/{key_id}` |
| Edit grants | ✅（仅创建时 + 详情页统一保存） | 详情页 grant picker | 详情 `POST /ui/keys/{id}/edit` |
| Rotate / Expire | ❌ | — | — |

---

## 3. 删除 vs 撤销（已定稿）

**v1 使用硬删除**：

1. `DELETE /api/keys/{key_id}` 删除 `api_keys` 行
2. 同事务删除 `api_key_grants`
3. 列表不再显示；无「已撤销」状态 badge
4. **不** cascade / 改写 `write_audit_log`（`api_key_id` 保留为历史字符串）
5. **删除** `POST /api/keys/{id}/revoke` 等 revoke 路由（无 410 bridge）

`api_keys.revoked_at` 列保留给 legacy/admin 行；自助 UI **不写** 此列。列表 SQL：`AND revoked_at IS NULL`。

应用日志：

```text
api_key_deleted principal_id=user:... key_id=key_... key_prefix=ma3k_...
```

---

## 4. API 契约

所有 `/api/keys` 路由要求：Authing session、Authing 已配置（否则 503）、mutating 路由 same-origin、owner-only（他人/不存在 → 404）、**不接受 X-API-Key**。

### `GET /api/keys`

```json
{
  "keys": [
    {
      "key_id": "key_4f9c1d20ab30",
      "key_prefix": "ma3k_9f8e7",
      "label": "my-laptop-agent",
      "plaintext_key": "ma3k_9f8e7d6c5b4a3210fedcba9876543210",
      "grants": [
        {"library_id": "lib_personal_abc123", "library_name": "Alice 的个人库", "role": "writer"},
        {"library_id": "lib_default", "library_name": "Community Library", "role": "writer"}
      ],
      "created_at": "2026-07-04T09:00:00+00:00",
      "last_used_at": null,
      "expires_at": null
    }
  ]
}
```

- 不含 `key_hash` / `key_ciphertext` / 已删除 key
- `plaintext_key` 可为 `null`（legacy 无 ciphertext 或 decrypt 失败）

### `POST /api/keys`

Request：`{"label": "...", "grants": [...]}`（grants 可选，缺省 personal+Community writer）

| Case | Status | Detail |
|------|--------|--------|
| Missing/blank label | 200 | 归一化为 `agent-key` |
| Label over 120 chars（**JSON API**） | **422** | Pydantic `max_length=120` |
| Label over 120 chars（SSR form） | 200 | truncate |
| Free tier 去掉 Community writer | 400 | `free tier requires Community Library writer grant` |
| Quota reached | 400 | `active key limit reached; delete an old key first` |

### `PATCH /api/keys/{key_id}`

仅改 `label`；blank → `agent-key`；JSON 超 120 → 422。

### `DELETE /api/keys/{key_id}`

Response：`{"deleted": true, "key_id": "..."}`；非 owner → 404。

### SSR 路由

| 路由 | 方法 | 行为 |
|------|------|------|
| `/ui/keys/` | GET | 列表 + 创建表单 |
| `/ui/keys/create` | POST | 创建 → 303 `/ui/keys/` |
| `/ui/keys/{key_id}` | GET | 详情 |
| `/ui/keys/{key_id}/edit` | POST | label + grants 统一保存 → 303 详情或列表 |
| `/ui/keys/{key_id}/delete` | POST | 删除 → **始终** 303 `/ui/keys/` |

---

## 5. UI 布局

### 5.1 列表页 `/ui/keys/`

```
┌─ Key 管理 ──────────────────────────────────────────────────────────┐
│ Name          Prefix      Grants           Last used   Actions      │
│ my-laptop     ma3_ab12…   个人库(读写),…   2026-07-03   [复制] [删除] │
│ ─────────────────────────────────────────────────────────────────── │
│ Label [my-laptop-agent      ] [创建新 key]                          │
│ (grant picker: Community + personal)                                │
└─────────────────────────────────────────────────────────────────────┘
```

- **Actions 列**：复制（hidden/offscreen `.copy-src` input **紧贴**按钮前，适配 `ma3CopyFrom` 的 `previousElementSibling`）+ 删除（行内 form + `confirm`）
- 无 plaintext 的旧 key：**不渲染**复制按钮（非 disabled）
- 删除文案：`删除`；title：`删除后此 key 将立即失效，无法恢复。`

### 5.2 详情页 `/ui/keys/{key_id}`

```
API Keys / my-laptop                        ← breadcrumb

┌─ my-laptop ─────────────────────────────────────────────┐
│ Key  [ma3_xxxxxxxx...        ] [复制]                    │  ← 只读，表单外
│ Prefix / Created / Last used                             │
│ ─────────────────────────────────────────────────────── │
│ <form POST .../edit>                                     │
│   Label [my-laptop              ]                        │
│   知识库权限 (grant picker)                               │
│   [← 返回列表]                          [保存]            │  ← .form-footer
│ </form>                                                  │
│ ─────────────────────────────────────────────────────── │
│ ┌─ 危险操作 ────────────────────────────────┐             │
│ │ 删除后此 key 立即失效。        [删除 key]  │  ← 独立 form │
│ └───────────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────┘
```

- **单一 `<form>`** 保存 label + grants；删除在独立 `danger-zone` form（禁止嵌套）
- 旧 `/label`、`/grants` 端点已合并为 `/edit`

### 5.3 CSS 增量

`.btn.sm`、`.cell-actions`、`.copy-src`（offscreen）、`.form-footer`、`.danger-zone`

---

## 6. DB helper

```python
def delete_api_key(key_id: str, *, principal_id: str) -> bool:
    with connect() as conn:
        cur = _execute(
            conn,
            "DELETE FROM api_keys WHERE key_id = ? AND principal_id = ? AND revoked_at IS NULL",
            (key_id, principal_id),
        )
        if not getattr(cur, "rowcount", 0):
            return False
        _execute(conn, "DELETE FROM api_key_grants WHERE key_id = ?", (key_id,))
    return True
```

配额：

```sql
SELECT COUNT(*) FROM api_keys WHERE principal_id = ? AND revoked_at IS NULL;
```

---

## 7. 错误与边界

| 状态 | UI | API |
|------|-----|-----|
| Authing 未配置 | 503 说明页 | 503 JSON |
| 无 session | 302 login | 401 |
| 缺 Origin/Referer（mutation） | 错误提示 | 403 |
| 删他人 key | 303 回列表（无差异） | 404 |
| legacy revoked 行 | 不出现在列表 | 不出现在 GET |
| decrypt 失败 | prefix + 重建引导 | `plaintext_key: null` |

---

## 8. 验收要点

- A1：新用户自助 create → copy → `ma3_whoami` 双库
- A2：UI 无 `撤销`/`已撤销`；操作为 `删除`
- A3–A5：硬删行 + MCP 立即 401 + 列表不含已删 key
- A6：`write_audit_log` 行保留原 `api_key_id`
- A7：删除释放配额
- A8：他人 key → 404
- A9：mutation 缺/错 Origin → 403
- A10：免费档 Community writer 锁定
- A11：rename 仅改 label
- A13：legacy `revoked_at` 行不在列表、不计配额

---

## 9. 相关文档

- [13-self-service-onboarding.md](../05-agent/getting-started.md) — 首登建库 + 自助签发切片
- [08-kb-access-and-org-isolation.md](../03-backend/authorization-and-libraries.md) — grants 模型
- [22-user-portal-ui-layout.md](information-architecture.md) §3.7 — 顶栏 API Keys 入口
