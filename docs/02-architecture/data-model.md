# 数据模型总览

> 各模块字段细节见对应 backend 文档；本文提供 **实体关系与状态机** 总图。

## 核心 ER（逻辑）

```text
Organization ──< org_members >── Principal (user:xxx)
      │
      └──< libraries (visibility, write_buffer_hours, kind, owner)
                │
                └──< cases ──< records (status, publish_at)
                              └── relations

Principal ──< api_keys ──< api_key_grants >── Library
                │
                └── billing_account_id → billing_accounts → plans

write_audit_log ──> record_id, principal_id, api_key_id (无 FK 到 api_keys)
record_deletions (tombstone)
record_feedback → correctness_tier / Wilson 输入
```

## Record 状态机

```text
ma3_report (new/supplement)
    └──► buffered ──publish_at 到期 / ma3_publish_record──► active
              │ PATCH 重置 publish_at
              └── ma3_delete_record ──► 硬删 + tombstone

ma3_report (verify/refute) ──► active（无 buffer）

visibility=draft ──► draft ── maintainer review ──► active | invalid

active ── maintainer/user ──► invalid
active ── deletion_protection 库 ──► trashed ── retention job ──► 硬删
```

## 关键枚举

| 实体 | 字段 | 取值 |
|------|------|------|
| `libraries.visibility` | | `public` \| `org` \| `private` |
| `libraries.kind` | | `personal` \| … |
| `records.status` | | `active` \| `buffered` \| `draft` \| `invalid` \| `trashed` |
| `api_key_grants.role` | | `reader` \| `writer` |
| `library_grants.role` | | `contributor` \| `maintainer` \| `admin` |
| `plans.code` | | `free` \| `pro` \| `team` |

## 索引与约束要点

- `principals`：`idx_principals_user_display_name` UNIQUE `lower(display_name) WHERE kind='user'`
- `api_keys`：`key_hash` UNIQUE；列表 `revoked_at IS NULL`
- personal library 幂等：`(kind='personal', owner_principal_id)`

## 规格分文档

| 主题 | 文档 |
|------|------|
| ACL / grants | [authorization-and-libraries.md](../03-backend/authorization-and-libraries.md) |
| Billing 表 | [billing-and-quotas.md](../03-backend/billing-and-quotas.md) |
| 写入审计 / 删除 | [writes-audit-and-deletion.md](../03-backend/writes-audit-and-deletion.md) |
| Buffer | [write-buffer.md](../03-backend/write-buffer.md) |

## 待补充

- [ ] 完整 DDL 单页导出（与 `db.py initialize_database` 同步）
- [ ] 迁移版本历史
