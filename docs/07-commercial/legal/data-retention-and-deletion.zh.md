# ma3 数据保留与删除（Data Retention & Deletion）

> **English note**: Draft data retention & deletion policy for the ma3 hosted
> service (ma3.io), based on the actually implemented behavior in ADR-013
> (write confirmation / audit / delete). **Draft — not lawyer-reviewed.**
> Self-host operators define retention for their own instances.

> **状态：草案。未经律师审阅。**
> 技术依据：[ADR-013](../../02-architecture/decisions/013-write-confirmation-audit-delete.md)、
> [writes-audit-and-deletion.md](../../03-backend/writes-audit-and-deletion.md)。

## 1. 记录的所有者删除（已实现，自助）

记录所有者（以 `write_audit_log.principal_id` / `records.created_by` 判定）
可随时通过 `ma3_delete_record` 删除自己的记录：

| 库类型 | 行为 |
|--------|------|
| 默认（personal / public / 未开启删除保护） | **硬删**：物理删除记录 + 索引 + embedding，写入删除墓碑（`record_deletions`） |
| 开启 `deletion_protection` 的库（Team plan org 库） | **软删**：`status='trashed'`、移出搜索；保留期（默认 30 天，`retention_days`）内可 `ma3_restore_record` 恢复，到期后台任务转硬删 |

- 删除**不级联**下游记录；引用了被删记录的记录会在读路径收到
  `lineage_warnings`（"builds on … which was deleted by owner"）。
- 缓冲中（buffered）的记录同样可删。

## 2. 删除后保留的元数据

即使记录被硬删，以下**元数据**会保留：

| 数据 | 保留原因 |
|------|----------|
| 删除墓碑（`record_deletions`：record_id、library_id、删除者、时间） | 引用完整性与审计 |
| 写入审计日志（`write_audit_log`） | 滥用追责、配额执行；其中 `api_key_id` 为历史字符串，Key 硬删后仍保留原 id |
| 运行日志（op logs） | 排障；按运维需要滚动清理 |

墓碑与审计日志**不包含**记录正文内容。

## 3. 维护者下架（takedown）

- 公共社区库中违规/侵权内容，维护者可依据治理规则（ADR-007/008，Observatory）
  下架或删除。
- **该流程当前未自动化**：请通过维护者 GitHub 个人资料页所列邮箱提交下架请求
  （参见 [SECURITY.md](../../../SECURITY.md)），注明记录 ID 与理由，
  以 best-effort 处理，无响应时限承诺。

## 4. 账户数据删除

- 账户级删除（principal、API keys、全部个人库）当前**未提供自助入口**，
  通过邮箱联系维护者处理；处理方式为删除个人库记录（同 §1 硬删语义）与撤销 keys，
  审计元数据按 §2 保留。

## 5. 备份

- ma3.io 的数据库备份用于灾难恢复，按运维计划滚动覆盖；
  已删除数据可能在备份中短暂残留，直至备份轮换过期。
  当前**不承诺**具体的备份轮换周期（正式承诺随 v1.1+ SLA 一并给出）。

## 6. 自托管实例

自托管运营者是其实例的数据控制者：代码提供与 ma3.io 相同的删除机制
（ADR-013 已在开源代码中实现），但保留期、备份、下架流程由运营者自行定义并
对其用户负责。
