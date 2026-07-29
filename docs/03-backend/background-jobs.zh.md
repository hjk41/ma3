# 后台任务（Background Jobs）

> **状态**：待补充 — 以下为已定行为摘要

## 已定任务

| 任务 | 触发 | 行为 | 规格 |
|------|------|------|------|
| `publish_due_buffered_records` | startup + 每 **60s** | `status=buffered` 且 `publish_at <= now` → `active` + 建索引 | [write-buffer.md](write-buffer.md) |
| trashed record purge | 未实现 / v1.1 | `trashed_at + retention_days` → 硬删 | [writes-audit-and-deletion.md](writes-audit-and-deletion.md) |
| usage rollup | Billing Phase B2 | `usage_events` → `usage_daily` / `usage_monthly` | [billing-and-quotas.md](billing-and-quotas.md) |

## 实现约定（buffer publish）

- 与 FastAPI lifespan / background task 集成
- 失败：log + 下次 tick 重试；不阻塞请求路径
- 作者 `ma3_publish_record` 与 job **竞态**：以 DB 行级 status 为准

## 待补充

- [ ] 任务注册表（模块、函数、interval）
- [ ] 单实例 vs 多实例 leader 选举（若水平扩展）
- [ ] 监控：最后一次 publish job 成功时间
- [ ] embedding 索引重建异步化（若有）
