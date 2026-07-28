# 23 — 公开默认页（Public Landing）决策摘要

> 状态：已定稿并实现（2026-07-06 产品 ratify，review 结论 PASS-WITH-NITS）。
> 本文为压缩归档的决策摘要；非契约，实现与后续变更以 docs 正式层与代码为准。

## 背景一句话

未登录用户访问内网部署实例（`http://<内网实例地址>/`）时被直接 302 到 Authing 登录，缺少「ma3 是什么 / 能做什么 / 当前状态 / 如何注册」的引导页，故新增公开默认页。

## 已拍板决策

- **路由语义**：`/ui/home/` 为 canonical 公开落地页；未登录 `GET /`、`/ui`、`/ui/` → 302 `/ui/home/` → 200；已登录访问上述路径（含 `/ui/home/`）→ 302 `/ui/me/`。Supersede design/15 §2.4 中仅根路径未登录行为，其余 IA 不变。
- **页面结构**：单栏 `page-narrow`，六段式：Hero → 问题（Problem）→ ma3 是什么（含「是/不是」2 列对比）→ Agent 工作流五步 → 注册后能做什么（3 张 feature card）→ 本实例状态（Live status）→ 三步开始；无 subnav、无重复 page-header 标题。
- **顶栏**：minimal header（brand → `/ui/home/` + 登录 + locale switcher），不渲染完整 topnav；v1 顶栏不加「社区库」链接。
- **CTA 层级**：primary「注册 / 登录」→ `/auth/login?next=/ui/me/`；次级「浏览社区库」→ `/ui/libraries/lib_default/`（匿名 Stats）；「Agent 接入文档」→ `/client/agent-onboarding.md`。
- **Live status 数据**：只用已有后端（不新增公开 API）：服务版本、实例 ID、部署时间 + 社区库 lib_default 的 cases / records / active 聚合。
- **Authing 未配置（LAN dev）分支**：Hero CTA 改为「进入门户」→ `/ui/me/`，页内 alert 提示开发模式。
- **安全边界**：实例 ID / 版本允许公开（与 healthz 一致）；不展示全局 principals 数、git_commit、record 内容摘要、Draft 数。
- **i18n**：`landing.*` 全量 zh-CN / en-US（约 35–45 keys）；zh-CN 为文案真源。
- **视觉**：GitHub 浅色单栏 marketing 风格；复用 `.btn` / `.card` / `.grid.stats`；新增 `.landing-hero` / `.landing-section` / `.landing-flow` / `.feature-grid` 等 class；不引入新字体、插画、JS 动画、chart 库。

## 明确不做 / 否决项

- v1 不做：营销独立域名 / 博客 / 定价页、匿名浏览 record 列表（保持 Stats-only）、landing 内嵌 MCP playground、多实例联邦统计、Contributors 聚合。
- 否决：根路径 `/` 直接 200 渲染（选了 canonical `/ui/home/` + 薄 302）；顶栏加社区库链接（v1）；展示 Draft 数。
- Review 遗留 nits（非阻塞）：375px 移动端截图验收待 owner spot-check；`docs/04-frontend/information-architecture.md` 站点地图需补 `/ui/home/`；OG tags 留 v1.1。

## 落地位置

- 代码：`app/api/routes_portal.py`（`portal_root` / `portal_home` / `_render_public_landing`）、`app/api/ui_theme.py`（`MA3_CSS` landing class）、`app/main.py` root redirect、`app/api/i18n/{zh-CN,en-US}.json`。
- 测试：`tests/integration/test_public_landing.py`（6 项）+ portal/i18n 回归。
- 相关文档：design/15（根路径语义 supersede）、design/22（minimal header 沿用）、`docs/04-frontend/ui-i18n-design-gpt55.md`。

## 历史稿说明

以下原稿已压缩归档删除：

- `23-public-landing-page-fable.md`（产品设计定稿）
- `23-public-landing-review-fable.md`（实现 review，PASS-WITH-NITS）
- `23-public-landing-visual-fable.md`（视觉真源稿）
