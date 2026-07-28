# 设计 Backlog（design backlog）

> 来源：原仓库根 `todo.md`（2026-07-03 pitch vs PITCH.md 缺口评审）迁移至此。
> 这些是**计划中的设计议题（planned design issues），不是承诺（not commitments）**——
> 无排期、无交付承诺，讨论定稿后才会转为 ADR / design 文档。

## 待设计议题 → GitHub Issues

在已登录 `gh` 的环境执行一次：

```bash
bash scripts/file_design_backlog_issues.sh
```

脚本会创建 B1–B4 Issues，并把本文件改成带链接的索引表。

| ID | 摘要 |
|----|------|
| B1 | 维护者/合规删除他人内容（含 audit / legal hold） |
| B2 | 自动维护者 Agent（过时检测 / supersede / 人纠偏） |
| B3 | Org 成员管理 / SSO / SCIM / seat 分配 |
| B4 | Integrator / 委托子身份（B2B2C） |

## 已决策（追溯用，已落文档）

- **防误删 = 付费功能**：仅付费 org 可对其**拥有**的库开启（回收站/恢复）；默认硬删不可恢复。→ ADR-013 / design-10
- **所有读写都需 key**：移除匿名读表述，全文档同步。→ ADR-011 + pitch/design 同步
- **不强制一把 key 只对应一个库**：跨库/跨 org 由企业行政手段解决，服务端不强隔离。→ ADR-011 备注
- **库容量超额 → 只读**：超 cap 后该库禁写、可读。→ ADR-012 / design-09
