# 10 — 写入确认、审计与删除

> **ADR**：[ADR-013](../adr/013-write-confirmation-audit-delete.md)  
> **前置**：08-kb-access、09-billing  
> **状态**：设计定稿（2026-07-03）

---

## 1. 写入判定树

```mermaid
flowchart TD
  Report[ma3_report] --> Kind{report_kind}
  Kind -->|verify_or_refute| Target[target_record_id required]
  Target --> TargetLib[write to target library]
  TargetLib --> AuditV[confirmation=verify_direct]
  Kind -->|supplement_or_new| AgentConfirm{agent asks user?}
  AgentConfirm -->|yes| UserOK[user_confirmed]
  AgentConfirm -->|no| Auto[agent_judged]
  UserOK --> PickLib[pick library by name default personal]
  Auto --> PickLib
  PickLib --> Write[ persist record ]
  Write --> AuditW[write_audit_log]
```

---

## 2. `ma3_report` 扩展字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `report_kind` | 是 | `verify` \| `refute` \| `supplement` \| `new` |
| `target_record_id` | verify/refute 必填 | 证实/证伪对象 |
| `library_id` | supplement/new 可选 | 缺省 → 用户 personal library |
| `confirmation` | supplement/new 必填 | `user_confirmed` \| `agent_judged`；verify/refute 用 `verify_direct` |

**校验**：

```python
if report_kind in ("verify", "refute"):
    assert target_record_id
    library_id = get_record(target_record_id).library_id
    assert key_can_read(library_id)
    confirmation = "verify_direct"
else:
    assert confirmation in ("user_confirmed", "agent_judged")
    library_id = library_id or default_personal_library(owner)
    assert key_can_write(library_id)
```

---

## 3. Library 命名

| 库 | 默认 name |
|----|-----------|
| personal | `{display_name} 的个人库` |
| public (`lib_default`) | `Community Library` |
| org | 创建时 admin 指定，如 `公司X-部署经验` |

`ma3_whoami` 返回示例：

```json
{
  "writable_libraries": [
    {"library_id": "lib_personal_abc", "name": "张三 的个人库", "visibility": "private"},
    {"library_id": "lib_default", "name": "Community Library", "visibility": "public"}
  ]
}
```

---

## 4. Schema

### `write_audit_log`

```sql
CREATE TABLE write_audit_log (
  id TEXT PRIMARY KEY,
  record_id TEXT NOT NULL,
  library_id TEXT NOT NULL,
  principal_id TEXT NOT NULL,
  api_key_id TEXT NOT NULL,
  report_kind TEXT NOT NULL,
  confirmation TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_write_audit_principal ON write_audit_log (principal_id, created_at DESC);
```

### `record_deletions`（tombstone）

```sql
CREATE TABLE record_deletions (
  record_id TEXT PRIMARY KEY,
  library_id TEXT NOT NULL,
  deleted_by TEXT NOT NULL,
  deleted_at TEXT NOT NULL
);
```

### `record_relations` 扩展

| 列 | 说明 |
|----|------|
| `source_deleted` | INTEGER 0/1；target 或 source 被删时置 1 |

---

## 5. `ma3_list_my_writes`

```json
{
  "writes": [
    {
      "created_at": "2026-07-03T10:00:00Z",
      "record_id": "vk_abc",
      "library_id": "lib_default",
      "library_name": "Community Library",
      "report_kind": "new",
      "confirmation": "user_confirmed",
      "key_prefix": "ma3k_abcd"
    }
  ]
}
```

Observatory：`GET /ui/writes/`、`GET /api/writes?limit=50`

---

## 6. `ma3_delete_record`

**权限**：`write_audit_log` 或 `records` 上 `created_by`（实现时写入 principal）匹配 caller。

**分支：库是否开启 `deletion_protection`**

```python
lib = get_library(record.library_id)
if lib.deletion_protection:      # 仅 Team plan 拥有的 org 库可开启
    soft_delete(record)          # status=trashed, 移出搜索, 记 trashed_at
else:
    hard_delete(record)          # 物理移除 + tombstone
```

**硬删步骤**（默认 / Free / personal / public）：

1. 校验 owner  
2. `DELETE FROM records WHERE id = ?`  
3. 删索引 / embedding  
4. `INSERT record_deletions`  
5. `UPDATE record_relations SET source_deleted=1 WHERE target_id=? OR source_id=?`  
6. **不** 删下游 records  

**软删步骤**（`deletion_protection=1`）：

1. 校验 owner 或 org maintainer  
2. `UPDATE records SET status='trashed', trashed_at=now WHERE id=?`  
3. 移出搜索索引（保留 payload）  
4. 到期（`trashed_at + retention_days`）由后台 job 转硬删

**读路径**：`lineage_warnings` 增加：

```text
record {rid} builds on {ref_id} which was deleted by owner
```

## 6b. `ma3_restore_record`（付费防误删）

- **前置**：record `status='trashed'` 且所在库 `deletion_protection=1`
- **权限**：owner 或 org maintainer
- **步骤**：`UPDATE records SET status='active', trashed_at=NULL` + 重建索引/embedding
- window 到期已硬删 → 不可恢复，返回 `already_purged`

### Schema 增量

| 对象 | 变更 |
|------|------|
| `libraries.deletion_protection` | INTEGER 0/1；仅 Team plan owned 库可置 1 |
| `libraries.retention_days` | 默认 30 |
| `records.status` | 增加 `trashed` 取值 |
| `records.trashed_at` | TEXT nullable |
| `plans.deletion_protection` | 是否允许开启（Free/Pro=0，Team=1，见 ADR-012） |

---

## 7. MCP 工具

| 工具 | 说明 |
|------|------|
| `ma3_list_my_writes` | `limit`, `offset`；审计列表 |
| `ma3_delete_record` | `record_id`；owner 删（默认硬删；受保护库软删） |
| `ma3_restore_record` | `record_id`；仅受保护库 window 内恢复 |

---

## 8. 实现阶段

| Phase | 内容 |
|-------|------|
| W1 | schema + report_kind/confirmation 校验 + write_audit_log |
| W2 | ma3_list_my_writes + Observatory 页 |
| W3 | ma3_delete_record（硬删）+ tombstone + lineage source_deleted 警告 |
| W4 | library 默认 naming on bootstrap |
| W5 | 防误删：libraries.deletion_protection（Team gate）+ 软删/回收站 + ma3_restore_record + 到期 purge job |

---

## 9. 相关文档

- [ADR-013](../adr/013-write-confirmation-audit-delete.md)
- [08-kb-access-and-org-isolation.md](08-kb-access-and-org-isolation.md)
- [pitch/knowledge-management-pitch.md](../pitch/knowledge-management-pitch.md)
