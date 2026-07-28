# 设计 Backlog（design backlog）

> 来源：原仓库根 `todo.md`（2026-07-03 pitch vs PITCH.md 缺口评审）迁移至此。
> 这些是**计划中的设计议题（planned design issues），不是承诺（not commitments）**——
> 无排期、无交付承诺，讨论定稿后才会转为 ADR / design 文档。
>
> **TODO**：GitHub Issue 工具可用后，将 B1–B4 逐条建为 GitHub Issues 并在此回填链接。

## 待设计议题

### B1 · 维护者/合规删除他人内容（原 T1）

- **场景**：pitch 承诺「人与团队维护者清除隐私 / 价值观 / 合规不该存在的内容」，
  尤其**公共库里别人写的** record。
- **缺口**：ADR-013 只覆盖 **owner 删自己的**；无 maintainer takedown、
  隐私删除请求、legal hold。当前 takedown 靠邮件人工处理
  （见 [legal/data-retention-and-deletion.md](../07-commercial/legal/data-retention-and-deletion.md) §3）。
- **需一并设计**：
  - SLA / 一等审计（audit as first-class）
  - Org 级强制策略（force-private、禁止写公共库）
  - 审计导出 / 留存策略
- **产出**：新 ADR（编号待分配；014/015 已被占用）+ design 文档。

### B2 · 自动维护者 Agent（原 T2）

- pitch 头条承诺「维护者 Agent 承担规模化日常维护」（发现过时 / 整理 / 总结），
  目前仅 roadmap 长程，无设计。
- **需定义**：过时检测信号、自动 supersede/整理的边界、人纠偏闭环、误判率指标。

### B3 · Org 成员管理 / SSO / SCIM / seat 分配（原 T3）

- ADR-011 说 admin「管理成员」，Team「5 seats」，但邀请流程、seat 分配、
  SSO/SCIM provisioning 未设计。
- pitch 商业模式点名 SSO（v1.1+）。

### B4 · Integrator / 委托子身份（B2B2C）（原 T4）

- persona 评审提出：集成商 App 代持 key、代理子身份（如 Agent 应用为最终客户持 key）。
- 未列优先级，无设计。

## 已决策（追溯用，已落文档）

- **防误删 = 付费功能**：仅付费 org 可对其**拥有**的库开启（回收站/恢复）；默认硬删不可恢复。→ ADR-013 / design-10
- **所有读写都需 key**：移除匿名读表述，全文档同步。→ ADR-011 + pitch/design 同步
- **不强制一把 key 只对应一个库**：跨库/跨 org 由企业行政手段解决，服务端不强隔离。→ ADR-011 备注
- **库容量超额 → 只读**：超 cap 后该库禁写、可读。→ ADR-012 / design-09
