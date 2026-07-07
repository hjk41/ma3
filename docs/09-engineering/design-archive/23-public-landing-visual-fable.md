# 23 — 公开默认页视觉布局（fable）

> **状态**：定稿（2026-07-06，随产品 ratify [23-public-landing-page-fable.md](23-public-landing-page-fable.md)）  
> **真源实现**：`code/server/app/api/ui_theme.py`（`MA3_CSS` + landing class）+ `routes_portal.py` `_render_public_landing`  
> **参照**：[15-user-portal-visual-sonnet5.md](15-user-portal-visual-sonnet5.md) GitHub 浅色 token；[22-user-portal-ui-unified-layout-fable.md](22-user-portal-ui-unified-layout-fable.md) 匿名顶栏

---

## 0. 一句话结论

公开默认页 `/ui/home/` 采用 **GitHub Marketing 浅色单栏**：Hero 居中 + 分段 `.landing-section` 卡片化内容区；Live status 复用 `.grid.stats`；全程 **无 subnav、无 page-header 重复标题**；顶栏 **minimal header**（brand + 登录 + locale）。

---

## 1. 页面壳

```
┌─ .topbar (#24292f) ────────────────────────────────────────────────┐
│ [brand→/ui/home/]                              登录 · 中文/EN       │
└────────────────────────────────────────────────────────────────────┘
┌─ .page > .page-narrow (max 1012px) ───────────────────────────────┐
│ .landing-hero                                                       │
│ .landing-section × 6                                                │
│ .footer（shell 共用）                                                │
└─────────────────────────────────────────────────────────────────────┘
```

| 项 | 值 |
|----|-----|
| `show_minimal_header` | `true` |
| `brand_href` | `{base}/ui/home/` |
| `active_nav` | `""`（无顶栏 nav） |
| `title`（`<title>`） | i18n `landing.meta.title` |
| `<meta name="description">` | i18n `landing.meta.description` |

---

## 2. 间距与 rhythm

| Token | 值 | 用途 |
|-------|-----|------|
| section gap | `48px` | `.landing-section + .landing-section` |
| hero padding | `32px 0 48px` | 首屏呼吸感 |
| hero → section | `0`（hero 自带 bottom padding） | |
| card inner | 沿用 `.card-body` `16px` | feature / compare |
| mobile section gap | `32px` | `@media (max-width: 768px)` |

---

## 3. 区块线框与 DOM

### 3.1 Hero — `.landing-hero`

```
                    ┌─────────────────────────────┐
                    │  H1.landing-hero-title      │
                    │  p.landing-hero-lead        │
                    │  .landing-hero-actions      │
                    │   [primary] [subtle] [subtle]│
                    └─────────────────────────────┘
                         text-align: center
```

| 元素 | 样式 |
|------|------|
| `.landing-hero-title` | `28px / 1.25`，`font-weight: 700`，`#24292f`，`max-width: 720px`，`margin: 0 auto 16px` |
| `.landing-hero-lead` | `18px`，`#57606a`，`max-width: 640px`，`margin: 0 auto 24px`，`line-height: 1.5` |
| `.landing-hero-actions` | `display: flex; flex-wrap: wrap; gap: 12px; justify-content: center` |

CTA 层级：

1. `.btn.primary` — 注册/登录（或 dev「进入门户」）
2. `.btn` — 浏览社区库
3. `.btn.subtle` — Agent 接入文档（外链 manifest 同级路径）

### 3.2 通用 section — `.landing-section`

```html
<section class="landing-section">
  <h2 class="landing-section-title">…</h2>
  …content…
</section>
```

| 元素 | 样式 |
|------|------|
| `.landing-section-title` | `20px`，`font-weight: 600`，`margin: 0 0 16px`，`#24292f` |
| `.landing-section-lead` | 可选副标题，`15px`，`#57606a`，`margin: -8px 0 16px` |

### 3.3 Problem — `.landing-problem-list`

```html
<ul class="landing-problem-list">
  <li>…</li>
</ul>
```

- 无 card 包裹；`padding-left: 20px`
- `li`：`margin: 10px 0`，`color: #57606a`，`line-height: 1.5`

### 3.4 Product — `.landing-compare-grid`

```
┌─ .landing-compare-grid (2 col) ─────────────────────┐
│ ┌ .card ──────────┐  ┌ .card ──────────┐           │
│ │ h3  ma3 是       │  │ h3  ma3 不是     │           │
│ │ ul              │  │ ul              │           │
│ └─────────────────┘  └─────────────────┘           │
└─────────────────────────────────────────────────────┘
```

| 元素 | 样式 |
|------|------|
| `.landing-compare-grid` | `display: grid; grid-template-columns: 1fr 1fr; gap: 16px` |
| mobile | `@media (max-width: 768px) { grid-template-columns: 1fr }` |
| card `h3` | `14px`，`font-weight: 600`，`margin: 0 0 12px` |
| card `ul` | `margin: 0; padding-left: 18px; font-size: 14px; color: #57606a` |

### 3.5 Workflow — `.landing-flow`

```
  (1) ──→ (2) ──→ (3) ──→ (4) ──→ (5)
   查      验证     写回     投票     受益
```

```html
<ol class="landing-flow">
  <li><span class="landing-flow-step">1</span><span class="landing-flow-text">…</span></li>
  …
</ol>
```

| 元素 | 样式 |
|------|------|
| `.landing-flow` | `display: flex; flex-wrap: wrap; gap: 12px; list-style: none; padding: 0; margin: 0` |
| `.landing-flow li` | `flex: 1 1 140px; display: flex; gap: 10px; align-items: flex-start; padding: 12px; background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px` |
| `.landing-flow-step` | `width: 24px; height: 24px; border-radius: 50%; background: #0969da; color: #fff; font-size: 12px; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0` |
| `.landing-flow-text` | `font-size: 14px; color: #24292f; line-height: 1.4` |

### 3.6 Features — `.landing-feature-grid`

```
┌──────────┐ ┌──────────┐ ┌──────────┐
│ h3       │ │ h3       │ │ h3       │
│ p        │ │ p        │ │ p        │
└──────────┘ └──────────┘ └──────────┘
```

| 元素 | 样式 |
|------|------|
| `.landing-feature-grid` | `display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px` |
| `.landing-feature-card` | `.card` 复用；`h3` 14px/600；`p` 13px muted |
| mobile | 单列 |

### 3.7 Live status — `.landing-status`

```
  h2
  .grid.stats（4 格：Cases / Records / Active / Version）
  p.landing-status-meta（实例 ID · 服务正常 · vX）
  a.btn.subtle → 查看社区库详情
```

| stat 标签 | i18n |
|-----------|------|
| Cases | `landing.status.cases` |
| Records | `landing.status.records` |
| Active | `landing.status.active` |
| Version | `landing.status.version` |

`.landing-status-meta`：`13px`，`#57606a`，`margin-top: 12px`

Version stat **不可点**（无 href）；前三项 optional 不链（v1 静态 stat-card，非 link）。

### 3.8 Get started — `.landing-getstarted`

```html
<ol class="landing-numbered-steps">
  <li>…</li>
</ol>
<div class="landing-getstarted-cta">
  <a class="btn primary">…</a>
</div>
```

| 元素 | 样式 |
|------|------|
| `.landing-numbered-steps` | `margin: 0; padding-left: 20px; color: #57606a` |
| `.landing-numbered-steps li` | `margin: 10px 0; line-height: 1.5` |
| `.landing-getstarted-cta` | `margin-top: 20px` |

### 3.9 Dev alert（Authing off）

Hero 下方或 status 上方：

```html
<div class="alert info">…</div>
```

沿用现有 `.alert.info`。

---

## 4. 响应式断点

| 断点 | 行为 |
|------|------|
| `> 768px` | compare 2 列；feature 3 列；flow 横排 flex |
| `≤ 768px` | 全部单列；hero title `24px`；hero actions 全宽按钮 `width: 100%; justify-content: center` on `.landing-hero-actions .btn` |
| `≤ 1012px` | 沿用 `.page-narrow` 左右 `24px` padding（shell 已有） |

---

## 5. 颜色与组件复用

| 用途 | 来源 |
|------|------|
| 主按钮 | `.btn.primary` |
| 次按钮 | `.btn` |
|  tertiary | `.btn.subtle` |
| Stat 数字 | `.stat-value` / `.stat-label`（已有） |
| 卡片 | `.card` + `.card-body` |
| 顶栏 | `.topbar` minimal（同匿名 lib_default） |

**不做**：hero 背景大图、gradient、icon font、animation。

---

## 6. i18n 与 accessibility

- 每 section 单一 `h2`；全页单一 `h1`（hero title）
- CTA 文案完整（「注册 / 登录」而非「点击」）
- `lang` 属性随 locale
- flow 步骤用 `<ol>` 语义 + 视觉圆圈数字

---

## 7. 实现 checklist

- [ ] `MA3_CSS` 追加 §3 全部 class
- [ ] `render_page(..., meta_description=...)`
- [ ] `_render_public_landing` 按 DOM 顺序组装
- [ ] `/ui/home/` + root redirect 分支
- [ ] i18n `landing.*` zh-CN / en-US
- [ ] pytest L1–L8（见 23 主设计 §12）

---

*fable · 2026-07-06 · 视觉真源，随实现 PR 交付*
