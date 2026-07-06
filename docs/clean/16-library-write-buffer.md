# 16 — 库写入缓冲期（Write Buffer）

> **状态**：定稿（2026-07-04，产品决策 ratified）  
> **验收**：[v1-library-write-buffer](../acceptance/v1-library-write-buffer.md)

---

## 0. 一句话结论

为每个 **library** 增加可配的 **`write_buffer_hours`（schema 默认 24）**。用户通过 agent 写入的新增/补充类 record，在缓冲期结束前 **对他人不可见、不可被搜索引用**；**写入者本人始终可见**。缓冲期内 **仅写入者** 可 **PATCH 修改**、**硬删除** 或 **立即确认 publish**。缓冲期满自动 publish（`active`）。

**Personal 库**：sole owner 在 buffer 期间本就能读自己的内容，buffer **对其无实质影响**；owner 可将 `write_buffer_hours` 设为 **0** 关闭 buffer。

这与 **`visibility=draft`（维护者审核队列）** 和 **写前 `confirmation`（agent↔用户对话）** 是第三条轴：**写后、发布前的可撤销窗口**。

---

## 1. Ratified 决策

| # | 议题 | **决定** |
|---|------|----------|
| B1 | 默认 buffer | **24**（schema 默认）；personal owner **可设 0** |
| B2 | PATCH 后计时 | **重置** `publish_at = now + hours` |
| B3 | 修改语义 | **同 record_id 覆盖** |
| B4 | 写入者权威 | `write_audit_log.principal_id` |
| B5 | UI | v1 即带：`/ui/me/writes/` + `/ui/records/{id}/` 操作区 |
| B6 | Stats | buffered **不计入**公共 active；作者侧「待发布」计数 |
| B7 | 用户说明 | 写入 **Community 公共库**（`lib_default`）知识条目 |

---

## 2. 适用范围

| `report_kind` / 路径 | 是否进 buffer |
|----------------------|---------------|
| **new** / **supplement** | **是**（若库 `write_buffer_hours > 0`） |
| **verify** / **refute** | **否** — 锁定 target 库，不宜隐藏 |
| 显式 `visibility=draft` | **否叠加** — 走 maintainer draft 队列 |
| Maintainer / admin 代写 | **否**（v1 maintainer 豁免） |

### 库级配置

| 字段 | 默认 | 谁可改 |
|------|------|--------|
| `write_buffer_hours` | **24** | 库 owner / 库管理员；personal owner 可设 **0** |
| `0` | — | 关闭 buffer，写入即 `active`（ADR-002 行为） |

---

## 3. 状态模型

### 3.1 新 status：`buffered`

```
ma3_report (supplement/new)
    → status = buffered
    → publish_at = now + write_buffer_hours
    → created_by = principal_id
    → 不入 search / ma3_context（对他人）
    → 写入者 deep link + ma3_list_my_writes + 本人 ma3_context 可见

缓冲期结束（background job，每 60s）
    → status = active

写入者操作：
    publish_now  → active（立即）
    PATCH        → 覆盖同 record_id；publish_at 重置
    delete       → ma3_delete_record（硬删 + tombstone）
```

**不采用**「status=active + 隐藏字段」单态方案：Observatory stats、search、portal 已广泛假设 `active` = 可见。

### 3.2 可见性矩阵

| 观察者 | buffered record |
|--------|-----------------|
| **写入者** | 读、PATCH、删、publish；search/deep link 可见 |
| 同库其他读者 / 其他 agent | **404**；search / ma3_context **不可见** |
| 库 maintainer | **v1 不可见**（v1.1 可选「可见不可改」） |
| 产品 admin（Observatory） | 可见枚举 |
| Library Stats（portal） | **不计入** active；作者侧「待发布 N」 |

---

## 4. 门户 UI

```text
/ui/me/writes/          filter「待发布」/ badge / stat 链接 ?status=buffered
/ui/records/{id}/       buffered + owner → [立即发布] [修改] [删除]
/ui/libraries/{id}/settings/  owner/admin → write_buffer_hours 表单（0–168）
```

列表批量操作（buffered only）：批量发布 · 批量删除 → `POST /ui/me/writes/batch`（[22](22-user-portal-ui-layout.md) §3.4）。

---

## 5. MCP / Agent 契约

| 工具 | 变更 |
|------|------|
| `ma3_report` | 响应增加 `status: "buffered"`, `publish_at`, `buffer_hours_remaining` |
| `ma3_publish_record(record_id)` | 写入者提前 publish → active |
| `ma3_patch_record` / recall | 仅 buffered + owner；PATCH 后 **重置 publish_at** |
| `ma3_delete_record` | buffered 同样可删 |
| `ma3_context` | 永不返回他人 buffered；**包含作者本人 buffered** |
| `ma3_list_my_writes` | 增加 `status`, `publish_at` |

Agent policy：收到 `status=buffered` 时告知用户缓冲截止时间；提示 `/ui/me/writes/` 或 `ma3_publish_record` 提前发布。

---

## 6. 与 draft / confirmation 的关系

| 机制 | 时点 | 可见性 | 审批方 |
|------|------|--------|--------|
| **confirmation**（ADR-013） | 写**前** | 未落库 | agent↔用户（非门禁） |
| **buffer**（本设计） | 写**后** | 仅作者 | 作者 publish 或超时 |
| **draft**（ADR-002） | 写**后** | maintainer 队列 | maintainer approve |

**互斥**：`visibility=draft` → **never** 同时 `buffered`；`verify_direct` → 直接 active，无 buffer。

---

## 7. Schema

```sql
ALTER TABLE libraries ADD COLUMN write_buffer_hours INTEGER NOT NULL DEFAULT 24;
ALTER TABLE records ADD COLUMN publish_at TEXT NULL;   -- ISO8601；仅 status=buffered
-- records.status 允许 'buffered'
```

---

## 8. 定时任务

`publish_due_buffered_records()`：startup + 每 60s background task；`publish_at <= now` → `status=active` + 建索引。

---

## 9. 相关文档

- [10-write-audit-and-delete.md](10-write-audit-and-delete.md) — 写入者判定、删除
- [15-user-portal.md](15-user-portal.md) — Stats≠Enumerate
- [22-user-portal-ui-layout.md](22-user-portal-ui-layout.md) — 列表/filter/batch
