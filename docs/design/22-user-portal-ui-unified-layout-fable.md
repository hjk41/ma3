# 22 — 用户门户 UI 功能与布局统一方案（fable）

> **状态**：统一设计稿（2026-07-05）  
> **实现**：**已交付** — design/22 真源；P13–P19 见 [v1-user-portal acceptance](../acceptance/v1-user-portal.md)  
> **评审**：[22-user-portal-ui-unified-discussion-gpt55.md](22-user-portal-ui-unified-discussion-gpt55.md)  
> **真源**：已交付 [15](15-user-portal-fable.md) + [14-layout](14-api-key-lifecycle-layout-fable.md) + [17](17-display-name-registration.md) + [16](16-library-write-buffer-fable.md)；待交付 [18–20](21-user-portal-enhancements-backlog.md)

---

## 0. 一句话结论

ma3 登录后 UI 分为 **两层导航**：

1. **顶栏（资源管理）** — 我的主页 · **库 · 记录 · 投票 · API Keys**（同级目录）  
2. **账户 subnav（仅 `/ui/me/*`）** — **概览 · 设置**

列表类页面（记录、投票）共用 **标准列表壳**：filter pills → 可排序表格 → 批量操作条（仅记录）→ `list-footer`（共 N 条 + 每页条数 + 分页）。概览 stat cards 整卡可点，作为顶栏的快捷入口。

**技术约束不变**：SSR HTML（`ui_theme.py`），无 SPA。

---

## 1. 站点地图

```text
/ui/me/                      概览仪表盘 ★ 默认落地
/ui/me/settings/             账户（显示名只读、Principal ID）
/ui/me/setup/                首次显示名（design/17，一次性）

/ui/libraries/               库列表
/ui/libraries/{id}/          库详情（Stats only）
/ui/libraries/{id}/settings/ 库 buffer 设置（owner）

/ui/me/writes/               记录列表（顶栏「记录」）
/ui/me/votes/                投票列表（顶栏「投票」）
/ui/records/{id}/            单条详情 + 投票 + buffer 操作区

/ui/keys/                    API Keys 列表（design/14）
/ui/keys/{id}                Key 详情

/ui/observatory/             产品管理员（admin）
```

v1.1 预留：`/ui/orgs/*`、`/ui/libraries/{id}/records/`、URL 美化 `/ui/records/` `/ui/votes/`。

---

## 2. 全局壳（Page Shell）

沿用 [15-user-portal-visual-sonnet5.md](15-user-portal-visual-sonnet5.md) GitHub 浅色风格；**更新顶栏与 subnav 分工**。

### 2.1 顶栏 `.topbar`

```
┌─ #24292f ──────────────────────────────────────────────────────────────┐
│ [ma3→/ui/me/]  我的主页 | 库 | 记录 | 投票 | API Keys | Observatory* │
│                                              显示名 · 账户 · 退出       │
└────────────────────────────────────────────────────────────────────────┘
* Observatory：仅 is_admin，class nav-admin
```

| key | 标签 | href | active 条件 |
|-----|------|------|-------------|
| me | 我的主页 | `/ui/me/` | 概览、setup |
| libraries | 库 | `/ui/libraries/` | 库列表/详情/settings |
| records | 记录 | `/ui/me/writes/` | writes 及 query 变体 |
| votes | 投票 | `/ui/me/votes/` | votes 及 query 变体 |
| keys | API Keys | `/ui/keys/` | keys 列表/详情 |
| observatory | Observatory | `/ui/observatory/` | admin |

**文案**：「库」替代 `Libraries`；`API Keys` 保留英文（短、与 design/14 一致）。

### 2.2 账户 subnav `.subnav-links`

**仅**在 `/ui/me/`、`/ui/me/settings/` 渲染：

| tab | href |
|-----|------|
| 概览 | `/ui/me/` |
| 设置 | `/ui/me/settings/` |

**不在** 记录/投票/库/keys 页渲染 subnav。

### 2.3 内容区

```
.page-narrow (max 1012px)
  .page-header: h1.page-title + .page-subtitle | .actions
  [filter-pills]          ← 列表页
  .card > table.data      ← 列表/详情
  .list-footer            ← 列表页底栏
  .footer
```

---

## 3. 页面规格

### 3.1 `/ui/me/` — 概览（仪表盘）

**subnav**：概览 active  
**顶栏**：我的主页 active  

| 区块 | 内容 |
|------|------|
| `.profile-header` | 头像 + 显示名（无 Principal ID、无编辑链接 — design/17） |
| `.grid.stats` ×5 | **可点击** stat card（design/18） |
| card「我的库」 | ≤5 行 + 「查看全部 →」`/ui/libraries/` |
| card「最近贡献」 | `.list-group` ≤5 条 + 「查看全部 →」`/ui/me/writes/` |

**Stat cards（5 张，整卡 `<a>`）**：

| 标签 | href |
|------|------|
| 记录 | `/ui/me/writes/` |
| 待发布 | `/ui/me/writes/?status=buffered` |
| 可访问库 | `/ui/libraries/` |
| 投票 | `/ui/me/votes/` |
| API Keys | `/ui/keys/` |

计数为 0 仍可点击。

---

### 3.2 `/ui/me/settings/` — 账户

**subnav**：设置 active  

| card | 内容 |
|------|------|
| 显示名 | 只读；注册时在 setup 设定，不可改 |
| Principal ID | `.id-block` 只读，无复制（design/15-me-profile） |

---

### 3.3 `/ui/libraries/` — 库

**顶栏**：库 active · **h1**：库  

表格：`库名(link) | 可见性 | 权限 | 角色`（现网逻辑不变，Stats only 政策不变）。

---

### 3.4 `/ui/me/writes/` — 记录（标准列表页）

**顶栏**：记录 active · **h1**：记录 · **无 subnav**  

**Query 契约**：

| 参数 | 默认 | 说明 |
|------|------|------|
| `page` | 1 | 页码 |
| `per_page` | 50 | 10 / 25 / 50 / 100 |
| `sort` | `created_at` | 见下表 |
| `dir` | `desc` | asc / desc |
| `status` | all | all / active / buffered / deleted |

**可排序列**：时间、记录、状态、库、类型、Key  

**Filter pills**：全部 · 已发布 · 待发布 · 已删除  

**表格列**：□（仅 buffered+owner）| 时间 | 记录(link) | 状态 | 库 | 类型 | Key  

**批量操作条**（有选中时）：批量发布 · 批量删除 → POST `/ui/me/writes/batch`  

**list-footer**：共 N 条 · 每页 pill · 上一页/下一页  

**依赖 design/16**：待发布 badge、buffer 语义不变；批量 = 单条 publish/delete 的集合。

---

### 3.5 `/ui/me/votes/` — 投票（标准列表页）

**顶栏**：投票 active · **h1**：投票 · **无 subnav**  

**Query**：`page`, `per_page`, `sort`, `dir`, `vote`（all/up/down）  

**可排序列**：时间、投票、记录、库  

**Filter pills**：全部 · 👍 赞同 · 👎 反对  

**无 checkbox、无批量**；改票仅在 `/ui/records/{id}/`  

**list-footer**：同记录页。

---

### 3.6 `/ui/records/{id}/` — 记录详情

**顶栏**：不强制高亮（breadcrumb 回我的主页）  

| 区块 | 条件 |
|------|------|
| buffer 操作 card | status=buffered 且 owner：发布/修改/删除 |
| 知识条目 + Feedback | active 可投票；非 author buffered → 404 |

（现网 + design/16，本方案不改动布局。）

---

### 3.7 `/ui/keys/` — API Keys

**顶栏**：API Keys active  

布局真源：[14-api-key-lifecycle-layout-fable.md](14-api-key-lifecycle-layout-fable.md)（列表 Actions 复制/删除；详情统一保存表单 + danger-zone）。

---

## 4. 共享组件（`ui_theme.py` 待增/改）

| 组件 | class / helper | 用途 |
|------|----------------|------|
| Stat 可点 | `a.stat-card-link` | `render_stat_cards((label, value, href))` |
| Filter | `.filter-pills` | `render_filter_pills(items, base, query)` |
| 排序表头 | `th.sortable` | `render_sort_link(...)` |
| 列表底栏 | `.list-footer` | `render_list_footer(page, total, per_page, query)` |
| 分页 | `.pagination` | 升级：保留 sort/filter/per_page query |

**原则**：列表 UI 不 hand-roll 在 `routes_portal.py` 多处；query 白名单排序列，防 SQL 注入。

---

## 5. 数据与文案

| 项 | 规则 |
|----|------|
| 个人库名 | `{display_name} 的个人库`；`ensure_personal_library` 自动同步 |
| 显示名 | design/17：setup 一次性，settings 只读 |
| 库列表 subtitle | 可保留「仅展示统计，不提供 record 枚举」 |

---

## 6. 实现阶段（fable + gpt-5.5 共识）

| Phase | 内容 | 验收 |
|-------|------|------|
| **0** | `ui_theme.py` helpers（nav、subnav、stat-link、filter、sort、list-footer、query 保留分页） | 单元/快照可选 |
| **1** | 顶栏 IA + 文案 + active_nav（无列表逻辑变更） | P19 导航部分 |
| **2** | DB query + 记录/投票列表 sort/filter/per_page | P14、P17、P18 |
| **3** | 记录批量 publish/delete | P15 |
| **4** | 个人库名同步 | P16 |
| **5** | 概览 stat 可点 | P13 |
| **6** | 集成测试 + acceptance 更新 | P13–P19 PASS |

**建议一次 PR 交付 Phase 0–5**，避免导航与列表分两次上线造成中间态混乱。

---

## 7. 明确不做（本方案）

- SPA / 客户端路由
- 库内 record 枚举（非 admin）
- 顶栏 responsive hamburger（v1 接受 flex 换行）
- `/ui/records/`、`/ui/votes/` URL 迁移
- 投票列表批量改票

---

## 8. 文档索引

| 文档 | 角色 |
|------|------|
| **本文 22** | 统一 IA + 布局真源 |
| [21](21-user-portal-enhancements-backlog.md) | Owner 需求 backlog 索引 |
| [18–20](21-user-portal-enhancements-backlog.md) | 分项需求细节 |
| [acceptance P13–P19](../acceptance/v1-user-portal.md) | 验收条目 |
| [discussion gpt55](22-user-portal-ui-unified-discussion-gpt55.md) | 双模型讨论与 nits |
