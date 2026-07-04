# 16 — 库写入缓冲期（Write Buffer）设计（fable）

> **状态**：定稿（2026-07-04，产品决策 ratified）  
> **Ratified 决策**：[16-library-write-buffer-decisions-for-owner.md](16-library-write-buffer-decisions-for-owner.md)  
> **Review**：[16-library-write-buffer-review-gpt55.md](16-library-write-buffer-review-gpt55.md)、[16-library-write-buffer-discussion-fable-gpt55.md](16-library-write-buffer-discussion-fable-gpt55.md)

---

## 0. 一句话结论

为每个 **library** 增加可配的 **`write_buffer_hours`（schema 默认 24）**。用户（principal）通过 agent 写入的新增/补充类 record，在缓冲期结束前 **对他人不可见、不可被搜索引用**；**写入者本人始终可见**。缓冲期内 **仅写入者** 可 **PATCH 修改**、**硬删除** 或 **立即确认 publish**。缓冲期满自动 publish（`active`）。

**Personal 库**：sole owner 在 buffer 期间本就能读自己的内容，buffer **对其无实质影响**；owner 可将 `write_buffer_hours` 设为 **0** 关闭 buffer。

这与现有 **`visibility=draft`（维护者审核队列）** 和 **写前 `confirmation`（agent↔用户对话）** 是第三条轴：**写后、发布前的可撤销窗口**。

---

## 1. 动机

| 痛点 | buffer 如何缓解 |
|------|----------------|
| Agent 误写 Community Library，立刻被 `ma3_context` 检索到 | 24h 内仅作者可见，作者可在门户撤回 |
| 用户发现写错库/内容有误，但 record 已被他人引用 | 缓冲期内硬删或改稿，不污染他人上下文 |
| ADR-002 默认 active 与「立即可用」agent 闭环 | 保留 **提前 publish** + **buffer=0** 库级豁免，不堵死全自动场景 |
| 已有 `ma3_delete_record` | 删除解决「移除」；buffer 解决「发布前隔离」——语义不同 |

---

## 2. 范围

### 2.1 适用写入类型

| `report_kind` / 路径 | 是否进 buffer |
|----------------------|---------------|
| **new** / **supplement**（补充/新增） | **是**（若库 `write_buffer_hours > 0`） |
| **verify**（证实/证伪，带 `target_record_id`） | **否** — 锁定 target 库，语义是更新既有知识，不宜隐藏 |
| Agent 显式 `visibility=draft` | **否叠加** — 走 maintainer draft 队列，见 §6 |
| Maintainer / admin 代写 | **否** — 或库级策略 `buffer_applies_to=mcp_users_only`（v1 建议 maintainer 豁免） |

### 2.2 库级配置

| 字段 | 类型 | 默认 | 谁可改 |
|------|------|------|--------|
| `write_buffer_hours` | int ≥ 0 | **24**（所有库 schema 默认） | 库 owner / 库管理员；personal 库 **owner 可设为 0** |
| `0` | — | — | 关闭 buffer，行为与现 ADR-002 一致（写入即 `active`） |

**产品决策（ratified）**：

- **全局默认 24h** — 不按库类型分 schema 默认  
- **Personal 库**：buffer 对 sole owner 无实质影响（内容对自己始终可见）；owner 若需「写后立即可被 agent 当 active 检索」可 **自设 0**  
- **Community / org 库**：24h 保护误写；管理员可调

---

## 3. 状态模型（推荐）

### 3.1 新 status：`buffered`

```
ma3_report (supplement/new)
    → status = buffered
    → publish_at = now + write_buffer_hours
    → created_by = principal_id
    → 不入 search / ma3_context（对他人）
    → 写入者 deep link + ma3_list_my_writes 可见

缓冲期结束（cron / lazy on read）
    → status = active
    → publish_at = null

写入者操作：
    publish_now  → active（立即）
    PATCH        → 覆盖同 record_id；**publish_at 重置**为 `now + write_buffer_hours`（ratified）
    delete       → ma3_delete_record（现有硬删 + tombstone）
```

**不采用**「status=active + 隐藏字段」单态方案：Observatory stats、search、portal 已广泛假设 `active` = 可见，易漏网。

### 3.2 可见性矩阵

| 观察者 | buffered record |
|--------|-----------------|
| **写入者**（`write_audit_log.principal_id`） | 读、PATCH、删、publish；**`ma3_context` / 自己的 deep link 可见** |
| 同库其他读者 / 其他 agent | **404**；**search / ma3_context 不可见** |
| 库 maintainer | **v1 不可见**（避免审核负担）；**v1.1 可选**「maintainer 可见不可改」 |
| 产品 admin（Observatory） | 可见枚举（运营/debug） |
| `ma3_context` / search | **排除** |
| Library Stats（portal） | **不计入** active 计数；可选单独「待发布 N」 |

---

## 4. 用户旅程（人类门户）— v1 必做

在 [design/15](15-user-portal-fable.md) 基础上扩展：

```text
/ui/me/writes/          「待发布」filter / badge / 计数
/ui/records/{id}/       若 buffered 且我是作者 → 操作区：
                          [立即发布] [修改] [删除]
                        若 buffered 且非作者 → 404
/ui/libraries/{id}/     owner 可改 write_buffer_hours（personal 可设 0）
```

**修改 UX（ratified）**：

1. 「修改」→ PATCH 表单（problem / summary / outcome / evidence）  
2. 保存后仍为 `buffered`，**`publish_at` 重置**（再获完整 buffer 窗口）  
3. 产品预期：多数用户 **删除** 或 **立即发布**；修改后计时重置对改稿更友好  

---

## 5. MCP / Agent 契约

| 工具 | 变更 |
|------|------|
| `ma3_report` | 响应增加 `status: "buffered"`, `publish_at`, `buffer_hours_remaining` |
| **新** `ma3_publish_record(record_id)` | 写入者提前 publish → active |
| `ma3_delete_record` | 已支持；buffered 同样可删 |
| **新或扩展** `ma3_update_record` / recall | 仅 buffered + owner；改内容 |
| `ma3_context` | 永不返回他人 buffered record |
| `ma3_list_my_writes` | 增加 `status`, `publish_at` |

Agent policy 补充：收到 `status=buffered` 时告知用户缓冲截止时间；**写入者自己的 ma3_context 仍可见该 record**；提示可在 `/ui/me/writes/` 或 `ma3_publish_record` 提前发布。用户说明写入 **Community 公共知识库**（ratified 决策 7）。

---

## 6. 与 draft / confirmation 的关系

| 机制 | 时点 | 可见性 | 审批方 |
|------|------|--------|--------|
| **confirmation**（ADR-013） | 写**前** | 未落库 | agent↔用户 |
| **buffer**（本设计） | 写**后** | 仅作者 | 作者 publish 或超时 |
| **draft**（ADR-002） | 写**后** | maintainer 队列 | maintainer approve |

**互斥规则（fable 建议）**：

- `visibility=draft` → **never** 同时 `buffered`；maintainer 路径优先  
- `verify_direct` → 直接 active，无 buffer  

---

## 7. 实现切片（若 ratified）

1. `libraries.write_buffer_hours` 列 + 迁移  
2. `records.status` 允许 `buffered`；`publish_at` 列  
3. `report_store_service` / search / stats 过滤  
4. 后台 job：`publish_due_buffered_records()`（每分钟或 hourly）  
5. MCP：`ma3_publish_record` + owner update  
6. Portal：`/ui/me/writes/` badge + record 操作区  
7. pytest + acceptance 矩阵  

---

## 8. Ratified 开放项（2026-07-04）

见 [16-library-write-buffer-decisions-for-owner.md](16-library-write-buffer-decisions-for-owner.md)。要点：全局默认 24、personal owner 可设 0、PATCH **重置** timer、v1 带 UI、作者可见 buffered、公共库用户说明。

---

## 9. 实现切片

1. `libraries.write_buffer_hours` 列 + 迁移（DEFAULT 24）  
2. `records.status` 允许 `buffered`；`publish_at` 列  
3. `report_store_service` / search：他人排除 buffered；**作者包含**  
4. 后台 job：`publish_due_buffered_records()`  
5. MCP：`ma3_publish_record` + owner PATCH  
6. Portal：待发布 UI + 库 buffer 设置（personal owner → 0）  
7. 公共库用户说明 record  
8. pytest + acceptance  
