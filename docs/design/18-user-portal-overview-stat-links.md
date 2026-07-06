# 18 — 概览页 Stat Cards 可点击跳转（fable）

> **状态**：**已并入 design/22**（§3.1）— 保留作需求溯源  
> **真源**：[22-user-portal-ui-unified-layout-fable.md](22-user-portal-ui-unified-layout-fable.md)

> **状态**：需求已定（2026-07-05，owner 提出）  
> **实现**：**未开始** — 见 [21-user-portal-enhancements-backlog.md](21-user-portal-enhancements-backlog.md)  
> **关联**：[15-user-portal-fable.md](15-user-portal-fable.md) §3.1、[16-library-write-buffer-fable.md](16-library-write-buffer-fable.md) §5、[20-user-portal-nav-peer-sections.md](20-user-portal-nav-peer-sections.md)

---

## 0. 一句话结论

`/ui/me/` 概览页 `.grid.stats` 中 **每一张 stat card 都应整块可点击**，跳转到对应功能页；数字与标签共同构成链接目标，而非纯展示。

**现网**：`ui_theme.render_stat_cards` 仅输出 `<div class="card stat-card">`，无 href。

---

## 1. 动机

| 现状 | 问题 |
|------|------|
| 概览页展示 5 个计数（我的贡献、待发布、可访问库、我的投票、API Keys） | 用户看到数字后需通过 subnav 或「查看全部 →」二次导航 |
| 「我的库」「最近贡献」card 已有「查看全部 →」链接 | stat 行与下方 card 交互不一致 |

Owner 要求：**点数字/标签即可直达对应列表或管理页**。

实现 design/20 后，stat 标签与顶栏对齐为 **记录 / 投票**（见 §3 表）。

---

## 2. Stat card → 目标路由（ratified）

| 标签（现网） | 标签（design/20 后） | 计数来源 | 点击目标 |
|--------------|----------------------|----------|----------|
| 我的贡献 | **记录** | `count_write_audit_for_principal` | `/ui/me/writes/` |
| 待发布 | 待发布 | `count_buffered_for_principal` | `/ui/me/writes/?status=buffered` |
| 可访问库 | 可访问库 | `len(list_entitled_libraries…)` | `/ui/libraries/` |
| 我的投票 | **投票** | feedback 计数 | `/ui/me/votes/` |
| API Keys | API Keys | key 数量 | `/ui/keys/` |

**零值行为**：计数为 `0` 时 **仍应可点击**。

**依赖**：「待发布」链接需 design/19 writes 页 `?status=buffered` 过滤；建议与 stat 链接 **同批交付**。

---

## 3. UI / 交互

```html
<a class="card stat-card stat-card-link" href="{base}/ui/me/writes/">
  <div class="stat-value">8</div>
  <div class="stat-label">记录</div>
</a>
```

- 整张 card 可点；hover/focus 用 `.stat-card-link`
- design/20 落地后，进入 writes/votes 时顶栏高亮「记录/投票」，而非「我的主页」

---

## 4. 实现映射（计划）

| 文件 | 变更 |
|------|------|
| `ui_theme.py` | `render_stat_cards((label, value, href))` |
| `routes_portal.py` | `portal_me` 传入 5 组 href |

---

## 5. 验收

见 acceptance **P13**。

- [ ] 5 张 stat card 均为 `<a href="…">`，href 符合 §2
- [ ] `?status=buffered` 过滤与「待发布」计数一致（依赖 design/19）
- [ ] 计数为 0 仍可点击
