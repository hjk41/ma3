# 21 — 用户门户增强 backlog（owner 需求汇总 · fable）

> **状态**：**已交付**（2026-07-05，design/22 + acceptance P13–P19 PASS-WITH-NITS）  
> **统一方案（真源）**：[22-user-portal-ui-unified-layout-fable.md](22-user-portal-ui-unified-layout-fable.md)  
> **决策索引**：[00-design-index-fable.md](00-design-index-fable.md)

---

## 0. 一句话结论

在 design/15 基线之上，owner 提出 **四类增强**（R1–R5），已并入 **design/22** 并完成实现。本文档保留为 **需求溯源索引**。

---

## 1. 需求清单（ratified）

| # | 主题 | 要点 | 设计 |
|---|------|------|------|
| R1 | 概览 stat 链接 | 5 张 stat card 整块可点，含「待发布」→ buffered 过滤 | [18](18-user-portal-overview-stat-links.md) |
| R2 | 记录列表 | 列排序、状态 filter、批量发布/删除（buffered）、个人库显示名 | [19](19-user-portal-writes-list-enhancements.md) |
| R3 | 记录/投票分页 | `page` + 可选 `per_page` 10/25/50/100 | [19](19-user-portal-writes-list-enhancements.md) |
| R4 | 投票列表 | 与记录列表同 UX：排序、👍/👎 filter、分页 | [19](19-user-portal-writes-list-enhancements.md) |
| R5 | 顶栏 IA | 库 · 记录 · 投票 · API Keys 与「我的主页」同级；subnav 仅概览+设置 | [20](20-user-portal-nav-peer-sections.md) |

---

## 2. 实现顺序（建议）

```text
Phase A  顶栏 IA (20)     — 先定导航，避免 writes/votes 改完又挪 tab
Phase B  列表 + 分页 (19) — writes + votes 表头/filter/batch/per_page
Phase C  stat 链接 (18)   — 依赖 writes 的 status=buffered 过滤
Phase D  库名同步 (19§5)  — ensure_personal_library 小改，可夹带在 B
```

Owner 未强制顺序；若一次交付，**20 + 19 + 18 同批** 验收。

---

## 3. 与现网差异（实现前 baseline）

| 区域 | 现网 (design/15) | 目标 |
|------|------------------|------|
| 顶栏 | 我的主页 · Libraries · API Keys | 我的主页 · **库** · **记录** · **投票** · API Keys |
| `/ui/me/` subnav | 概览 · 我的贡献 · 我的投票 · 设置 | 概览 · **设置** |
| stat cards | `<div>` 不可点 | `<a class="stat-card-link">` |
| `/ui/me/writes/` | 固定 50 条/页、无 sort/filter/batch | 见 design/19 |
| `/ui/me/votes/` | 固定 50 条/页、无 sort/filter | 见 design/19 |
| 个人库名 | 可能仍为 `{sub} 的个人库` | `{display_name} 的个人库` |

---

## 4. 验收索引

见 [docs/acceptance/v1-user-portal.md](../acceptance/v1-user-portal.md) **P13–P19** — **PASS-WITH-NITS**（2026-07-05）。

---

## 5. 明确不做（v1 本批）

- URL 美化（`/ui/records/`、`/ui/votes/`）— v1.1
- 库内 record 枚举 UI
- Observatory 中文化
