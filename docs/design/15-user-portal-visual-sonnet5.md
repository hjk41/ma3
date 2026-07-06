# 15 — 用户门户视觉设计（Sonnet-5 · GitHub 风格）

> **状态**：设计稿（2026-07-04）；**导航/subnav 以 [22](22-user-portal-ui-unified-layout-fable.md) 为准**  
> **真源实现**：`code/server/app/api/ui_theme.py`（`MA3_CSS` + `render_page`）  
> **产品 IA**：[22-user-portal-ui-unified-layout-fable.md](22-user-portal-ui-unified-layout-fable.md)（布局）；[15-user-portal-fable.md](15-user-portal-fable.md)（权限模型）

参照 GitHub.com / GitHub Settings / Personal Access Tokens 的**浅色**界面：深色顶栏、白底内容区、6px 圆角、细边框表格、蓝色主按钮。

---

## 1. Design tokens（`:root` 扩展）

在现有 token 上追加（不替换）：

```css
--header-bg: #24292f;
--header-text: #f0f6fc;
--header-muted: #c9d1d9;
--canvas-default: #ffffff;
--canvas-subtle: #f6f8fa;
--border-default: #d0d7de;
--accent-fg: #0969da;
--danger-fg: #cf222e;
--page-max: 1012px;          /* GitHub settings 内容宽 */
--sidebar-width: 220px;
```

**不做**：dark mode、图标字体、外部 CSS/JS 框架。

---

## 2. 页面壳（Page shell）

```
┌─ .topbar (#24292f) ─────────────────────────────────────────────┐
│ [brand→/ui/me/]  .topnav  我的主页 | 库 | 记录 | 投票 | API Keys | Observatory* │
│                                    * .nav-admin 弱化色，仅 is_admin      │
│                              .topbar-meta  用户名 · 账户 · 退出          │
└────────────────────────────────────────────────────────────────┘
┌─ .page (max-width 1280; 门户页内层 .page-narrow max 1012) ──────┐
│ .breadcrumb（二级以下）                                          │
│ .page-header: .page-title + .page-subtitle | .actions            │
│ body                                                             │
│ .footer                                                          │
└──────────────────────────────────────────────────────────────────┘
```

- **Observatory** 导航项加 class `nav-admin`：`opacity:0.75; font-weight:400`
- Logo `href` 固定 `/ui/me/`

---

## 3. 布局模式

### 3.1 默认单栏（列表 / 详情）

`.page-narrow` 包裹主内容；`.card` 堆叠，间距 16px。

### 3.2 Settings 双栏（`/ui/me/` 可选 v1 单栏简化）

```
┌ .layout-settings ─────────────────────────────┐
│ .settings-sidebar │ .settings-main           │
│  · 概览            │ .profile-header           │
│  · 我的贡献 →      │ stat cards                │
│  · 我的投票 →      │ cards…                    │
└────────────────────────────────────────────────┘
```

**v1 实现**：`/ui/me/` 用**单栏** + 页内 `.subnav-links`（**仅概览 | 设置**）；记录/投票由顶栏进入。sidebar 双栏留 v1.1。

### 3.3 `.subnav-links`（GitHub repo tabs，仅 `/ui/me/*`）

```html
<nav class="subnav-links">
  <a class="active" href="...">概览</a>
  <a href=".../settings/">设置</a>
</nav>
```

CSS：`border-bottom:1px solid var(--border-default)`；active 项 `border-bottom:2px solid #fd8c73; font-weight:600`。

---

## 4. 组件 catalog → CSS class

| 组件 | Class | 说明 |
|------|-------|------|
| Profile 头 | `.profile-header` | 头像 + display_name（概览页无 Principal ID） |
| Principal ID | `.id-block` | **仅 settings** 只读；无复制 |
| Stat 可点 | `a.stat-card-link` | design/22；5 张 stat |
| 列表项（活动流） | `.list-group` > `.list-item` | 左标题链接 + 右 meta 时间；hover `#f6f8fa` |
| 表格 | `table.data` in `.table-wrap` | 已有 |
| 空状态 | `.empty` + `.empty-icon` + `.empty-cta` | CTA 用 `.btn.primary` |
| 403 | `.page-403` | 居中；`.page-403 h1`；链接 `.btn` |
| 分页 | `.pagination` | flex；`.pagination .current` |
| Badge | `.badge.*` | 已有 |
| Danger | `.danger-zone` | 已有（keys） |

### `.list-item` 结构（writes/votes 摘要）

```html
<a class="list-item" href="/ui/records/vk_xxx">
  <div class="list-item-title">MCP -32602 排查…</div>
  <div class="list-item-meta">Community · 2026-07-03</div>
</a>
```

### `.profile-header`

```html
<div class="profile-header">
  <div class="profile-avatar" aria-hidden="true">{首字母}</div>
  <div class="profile-body">
    <h2 class="profile-name">{display_name}</h2>
    <div class="profile-meta">… principal_id copy …</div>
  </div>
</div>
```

---

## 5. 分页面线框与 class 映射

### `/ui/me/`

- `.profile-header`
- `.subnav-links`（概览 active）
- `.grid.stats` ×4
- `.card`「我的库」→ `table.data`（≤5 行）+ header 右 `.btn.subtle`「查看全部」
- `.card`「最近贡献」→ `.list-group` 或 compact table

### `/ui/me/writes/` `/ui/me/votes/`

- `.subnav-links`（对应 tab active）
- 单 `.card` + `table.data`
- `.pagination`

### `/ui/libraries/`

- `table.data`；库名列 `<a class="key-link">` → detail

### `/ui/libraries/{id}/`

- `.breadcrumb`
- `.grid.stats`（Cases / Records / Active / Draft / Invalid）
- 两列小表 outcome/task_type（`.split` 内 mini card）
- `.card`「我的访问」`.kv`（登录用户）
- 匿名：`.alert.info` CTA「登录以贡献与投票」

### `/ui/records/{id}`

- `.breadcrumb`：`我的主页 / Record vk_…`
- 现有 `.split` 双 card（record + feedback）

### `/ui/keys/*`

- 保持 design/14；统一 `active_nav=keys`

### Observatory 403

```html
<div class="page-403">
  <h1>403</h1>
  <p>Observatory 仅产品管理员可访问。</p>
  <a class="btn" href="/ui/me/">返回我的主页</a>
</div>
```

---

## 6. 导航参数化

```python
def portal_nav_items(base: str, *, is_admin: bool) -> list[tuple[str, str, str, bool]]:
    # (key, label, href, admin_only_muted)
    items = [
        ("me", "我的主页", f"{base}/ui/me/", False),
        ("libraries", "库", f"{base}/ui/libraries/", False),
        ("records", "记录", f"{base}/ui/me/writes/", False),
        ("votes", "投票", f"{base}/ui/me/votes/", False),
        ("keys", "API Keys", f"{base}/ui/keys/", False),
    ]
    if is_admin:
        items.append(("observatory", "Observatory", f"{base}/ui/observatory/", True))
    return items
```

`render_page(..., is_admin=False, active_nav="me")`

---

## 7. 响应式

- `@media (max-width: 768px)`：`.topnav` 隐藏部分 label（保留 icon 首字）；`.split` → 单栏；`.grid.stats` minmax 120px
- `@media (max-width: 960px)`：`.layout-settings` 单栏

---

## 8. 明确不做（v1）

- Dark mode、动画、toast、模态框 JS
- 客户端路由 / hydration
- 库 record 枚举列表 UI（非 admin）
- Org 侧栏

---

## 9. CSS 增量预算

新增约 **120 行** 以内：`.profile-*`, `.subnav-links`, `.list-group`, `.list-item`, `.page-403`, `.pagination`, `.page-narrow`, `.nav-admin`, `.layout-settings`, `.settings-sidebar`, `.empty-cta`。
