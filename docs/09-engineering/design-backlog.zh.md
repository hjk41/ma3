# 设计 Backlog（design backlog）

> 来源：原仓库根 `todo.md`（2026-07-03 pitch vs PITCH.md 缺口评审）迁移至此。
> 这些是**计划中的设计议题（planned design issues），不是承诺（not commitments）**——
> 无排期、无交付承诺，讨论定稿后才会转为 ADR / design 文档。
>
> **真源**：以下 GitHub Issues（本文件仅作索引）。

## 待设计议题

| ID | Issue | 摘要 |
|----|-------|------|
| B1 | https://github.com/hjk41/ma3/issues/1 | 维护者/合规删除他人内容 |
| B2 | https://github.com/hjk41/ma3/issues/2 | 自动维护者 Agent |
| B3 | https://github.com/hjk41/ma3/issues/3 | Org 成员 / SSO / SCIM / seats |
| B4 | https://github.com/hjk41/ma3/issues/4 | Integrator / 委托子身份（B2B2C） |

重新建 Issue：`bash scripts/file_design_backlog_issues.sh`（会新建而非去重，慎用）。


## 运维 / 质量债（持续改进）

| ID | Issue | 摘要 |
|----|-------|------|
| O1 | ~~https://github.com/hjk41/ma3/issues/5~~ | **已关闭** — Phase 0–3 指标/告警/SLO 已上线 |
| O2 | ~~https://github.com/hjk41/ma3/issues/6~~ | **已关闭** — 生产 Runbook 已补全（中英） |
| O3 | https://github.com/hjk41/ma3/issues/7 | Playwright 门户回归范围 |
| O4 | https://github.com/hjk41/ma3/issues/8 | Agent eval 固定节奏 |

## 已决策（追溯用，已落文档）

- **防误删 = 付费功能**：仅付费 org 可对其**拥有**的库开启（回收站/恢复）；默认硬删不可恢复。→ ADR-013 / design-10
- **所有读写都需 key**：移除匿名读表述，全文档同步。→ ADR-011 + pitch/design 同步
- **不强制一把 key 只对应一个库**：跨库/跨 org 由企业行政手段解决，服务端不强隔离。→ ADR-011 备注
- **库容量超额 → 只读**：超 cap 后该库禁写、可读。→ ADR-012 / design-09
