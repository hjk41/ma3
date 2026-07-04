# Review — 15-user-portal-visual-sonnet5（fable）

> **Reviewer**: fable  
> **Verdict**: **PASS-WITH-NITS**

## 通过项

1. **GitHub 对齐可落地**：token 与现有 `MA3_CSS` 一致，增量 class 可在一个 PR 内完成；不引入新依赖。
2. **与 design/14 兼容**：`copy-row` / `copy-src` / `cell-actions` / `danger-zone` 原样复用；keys 页无需重设计。
3. **导航参数化**与 ratified IA 一致：Observatory `nav-admin` 弱化、logo → `/ui/me/`。
4. **Stats-only 库页**：线框无 record 表格，符合 owner 决策 3。
5. **403 页**独立组件，满足 Observatory 403 决策。

## Nits（非阻塞）

1. **`.subnav-links` active 色 `#fd8c73`** 是 GitHub repo tab 色，与 ma3 accent `#0969da` 并存略杂；实现时可改 active border 为 `var(--accent)` 统一品牌。
2. **`/ui/me/` v1 单栏 + subnav** 即可；`.layout-settings` sidebar 不要半实现——Acceptance 时 sidebar 不应出现在 DOM。
3. **`.list-item` vs `table.data`**：writes/votes 全页用 table（已排序列多）；`/ui/me/` 最近 5 条用 `.list-group`——实现时勿混用同一数据源两种样式。
4. **匿名 public 库页** 顶栏应只显示 brand +「登录」，不要渲染完整 `topnav` 空链。
5. **Acceptance 截图清单**：me 主页、403、anonymous lib_default stats、writes 分页、record 详情 breadcrumb。

## 实现顺序（fable 推荐）

1. `ui_theme.py` tokens + nav 参数化 + 新 components  
2. `routes_portal.py` 页面（依赖 theme）  
3. Observatory 403 + record 301  
4. 测试 + acceptance doc
