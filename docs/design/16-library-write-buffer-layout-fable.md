# 16 — Write Buffer 实现布局（fable）

> **状态**：定稿（2026-07-04）  
> **真源**：[16-library-write-buffer-fable.md](16-library-write-buffer-fable.md)、[16-library-write-buffer-decisions-for-owner.md](16-library-write-buffer-decisions-for-owner.md)

## 1. 数据

- `libraries.write_buffer_hours INT NOT NULL DEFAULT 24`
- `records.publish_at TEXT NULL`（ISO8601；仅 `status=buffered`）

## 2. MCP

| 工具 | 行为 |
|------|------|
| `ma3_report` | new/supplement + buffer>0 → `buffered`；响应含 `publish_at` |
| `ma3_publish_record` | owner → `active`；建索引 + relations |
| `ma3_patch_record` | owner + buffered → PATCH 字段；**重置 publish_at** |
| `ma3_delete_record` | 不变 |
| `ma3_context` | search active + **作者本人 buffered** |
| `ma3_list_my_writes` | 增 `status`, `publish_at` |

## 3. Portal UI

```
/ui/me/writes/     badge「待发布 N」；表格 status 列
/ui/records/{id}/  buffered + owner → [立即发布][修改][删除]
/ui/libraries/{id}/settings/  owner/admin → write_buffer_hours 表单（0–168）
```

## 4. 定时

- `publish_due_buffered_records()`：startup + 每 60s background task

## 5. Acceptance（fable）

B1–B10 见 `docs/acceptance/v1-library-write-buffer.md`
