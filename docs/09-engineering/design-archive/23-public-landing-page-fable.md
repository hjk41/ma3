# 23 — 未登录公开默认页（Public Landing）设计（fable）

> **状态**：定稿（2026-07-06，产品已 ratify）  
> **视觉真源**：[23-public-landing-visual-fable.md](23-public-landing-visual-fable.md)  
> **驱动**：202 部署访问 `http://192.168.31.202:8000/` 时未登录用户被直接 302 到 Authing 登录，缺少「ma3 是什么 / 能做什么 / 当前状态 / 如何注册」的引导页  
> **参照**：[pitch.md](../../01-product/pitch.md)、[vision.md](../../01-product/vision.md)、[getting-started.md](../../05-agent/getting-started.md)、[information-architecture.md](../../04-frontend/information-architecture.md)  
> **i18n**：[../../04-frontend/ui-i18n-design-gpt55.md](../../04-frontend/ui-i18n-design-gpt55.md) — v1 支持 `zh-CN` / `en-US`  
> **技术约束**：SSR HTML（`ui_theme.py` / `render_page`），无 SPA；复用现有 GitHub 浅色 token

---

## 0. 一句话结论

未登录用户访问 **`/`、`/ui`、`/ui/`** 时，不再直接跳转登录，而是渲染 **公开默认页**（`/ui/home/` 为 canonical HTML 路由，根路径 302 到该页）。页面用 **一页式营销 + 实例状态 + 公开库快照** 回答四个问题：**ma3 是什么、Agent 能做什么、这台实例现在有什么、我如何注册并开始**。主 CTA 为 **注册 / 登录**（`/auth/login?next=/ui/me/`），次 CTA 为 **浏览社区库** 与 **Agent 接入文档**。

已登录用户访问上述 URL 时行为不变：**302 `/ui/me/`**。

---

## 1. 问题与目标

### 1.1 现状

| 路径 | 当前行为 |
|------|----------|
| `/`、`/ui`、`/ui/` | 302 → `/ui/me/` |
| `/ui/me/`（未登录 + Authing on） | 302 → `/auth/login?next=/ui/me/` |
| `/ui/libraries/lib_default/` | **可匿名** Stats-only（已有 `show_minimal_header`） |
| `/auth/login` | 302 → Authing authorize（无产品介绍） |

结果：首次访问者看不到产品说明，无法理解「为什么要注册」，也无法在登录前感知社区库是否在增长。

### 1.2 目标

| 目标 | 说明 |
|------|------|
| **降低冷启动摩擦** | 访客 30 秒内理解 ma3 价值主张与 Agent 工作流 |
| **引导注册** | 主按钮始终可见：注册 / 登录 → Authing |
| **展示可信度** | 公开实例状态（版本、实例 ID）+ 社区库聚合数字（cases/records/active） |
| **不破坏登录后 IA** | `/ui/me/` 仍是登录后默认落地；深链 protected 路由仍 `login?next=` |
| **与 i18n Phase 1 一致** | 文案进 catalog；顶栏保留 locale switcher |
| **最小 diff** | 单路由 + 单 render helper；不引入 CMS / 静态站点生成 |

### 1.3 非目标（v1）

- 营销站独立域名、博客、定价页完整 UI（Billing v1.1+）
- 匿名浏览 record 列表（仍 Stats-only，见 design/15 §2.3）
- 在 landing 嵌入 MCP playground 或 live search demo
- 多实例联邦展示 / 全球统计

---

## 2. 路由与重定向

### 2.1 路由表（变更后）

```text
/                            未登录 → 302 /ui/home/；已登录 → 302 /ui/me/
/ui、/ui/                    同上

/ui/home/                    ★ 公开默认页（canonical）
                             未登录 → 200 HTML
                             已登录 → 302 /ui/me/

/ui/me/                      登录后个人主页（不变）
/ui/libraries/lib_default/   匿名 Stats（不变，landing 链入）
/auth/login                  Authing 入口（不变）
```

### 2.2 实现落点

| 文件 | 变更 |
|------|------|
| `app/main.py` | `root_redirect(request)` 改为：有 session → `/ui/me/`；否则 → `/ui/home/` |
| `app/api/routes_portal.py` | 新增 `GET /ui/home/` → `_render_public_landing(...)` |
| `app/api/ui_theme.py` | 可选：`.hero` / `.feature-grid` / `.status-strip` 少量 CSS |
| `app/api/i18n/{zh-CN,en-US}.json` | 新增 `landing.*` keys |
| `tests/integration/` | 匿名 GET `/` → `/ui/home/`；已登录 GET `/` → `/ui/me/`；landing 含 CTA 与 stats |

### 2.3 与 design/15 §2.4 的关系

**Supersede 仅根路径语义**：

- 旧：`/` 或 `/ui/` → 302 `/ui/me/`（未登录先 login）
- 新：`/` → 302 `/ui/home/`（未登录）；`/ui/me/` 仍 require auth

design/15 其余 IA（登录后默认 `/ui/me/`、Observatory admin 门控）不变。

---

## 3. 页面信息架构

### 3.1 顶栏（匿名 minimal header）

沿用 [22 §2.1](22-user-portal-ui-unified-layout-fable.md) 与匿名库页模式（fable review nit #4）：

```
┌─ #24292f ──────────────────────────────────────────────────────────────┐
│ [ma3→/ui/home/]                              登录 · 中文/EN            │
└────────────────────────────────────────────────────────────────────────┘
```

| 元素 | 行为 |
|------|------|
| Brand | `href="/ui/home/"`（未登录）或 `/ui/me/`（已登录时本页不会渲染） |
| 顶栏 nav | **不渲染**完整 `topnav`（避免空链到需登录页） |
| 右侧 | `登录` → `/auth/login?next=/ui/me/`；locale switcher |

可选 v1.1：顶栏增加 **社区库** 文字链 → `/ui/libraries/lib_default/`（仍 minimal，不展开 nav）。

### 3.2 页面区块（单栏 `page-narrow`）

自上而下六段 + 页脚链接区：

```text
┌─ Hero ───────────────────────────────────────────────────────────────┐
│  H1 + 副标题 + [注册/登录] primary  [浏览社区库] subtle  [Agent 文档]   │
└────────────────────────────────────────────────────────────────────────┘
┌─ 我们解决什么问题（Problem）──────────────────────────────────────────┐
│  3 条 bullet：重复试错 / 经验碎片化 / 不可解释                          │
└────────────────────────────────────────────────────────────────────────┘
┌─ ma3 是什么（Product）─────────────────────────────────────────────────┐
│  一句话 + 「Agents stand on agents」信念 + 我们不是什么（2×2 对比表）    │
└────────────────────────────────────────────────────────────────────────┘
┌─ Agent 如何工作（How it works）────────────────────────────────────────┐
│  5 步横向/纵向步骤条：查 → 验证 → 写回 → 投票治理 → 下一 Agent 受益      │
└────────────────────────────────────────────────────────────────────────┘
┌─ 注册后你能做什么（For you）───────────────────────────────────────────┐
│  3 张 feature card：个人库 + 社区贡献 / API Key + MCP / 投票与缓冲发布   │
└────────────────────────────────────────────────────────────────────────┘
┌─ 本实例状态（Live status）★ ───────────────────────────────────────────┐
│  stat cards + 社区库快照 + 服务信息条                                   │
└────────────────────────────────────────────────────────────────────────┘
┌─ 开始（Get started）───────────────────────────────────────────────────┐
│  编号步骤 1 注册 → 2 创建 Key → 3 配置 MCP → 4 第一次 report           │
│  [注册/登录] primary                                                    │
└────────────────────────────────────────────────────────────────────────┘
```

**不设** `/ui/me/*` subnav；**不设** page-header 大标题重复（Hero 即标题）。

---

## 4. 线框（ASCII）

```
┌ topbar: [ma3]                                    登录 · 中文/EN ────────┐
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   让每一个 Agent，站在其它 Agent 的肩膀上                                │
│   可验证的跨 Agent 知识网络 — 查清楚再动手，验证完再写回。                 │
│                                                                        │
│   [ 注册 / 登录 ]   [ 浏览社区库 ]   [ Agent 接入文档 ]                  │
│                                                                        │
├─ 为什么需要 ma3 ──────────────────────────────────────────────────────┤
│  • 每个新 session 像第一天入职 — 前人结论后人拿不到                       │
│  • 经验锁在聊天与笔记里，无法跨 Agent 复用                               │
│  • 难以回答：为什么推荐这条？它还准吗？                                   │
├─ ma3 是什么 ──────────────────────────────────────────────────────────┤
│  面向所有 Agent 的 verified knowledge network。                         │
│  ┌ ma3 是 ─────────────┐  ┌ ma3 不是 ────────────┐                      │
│  │ 跨 Agent 验证结论    │  │ 全会话录像 / trace    │                      │
│  │ 可解释案例与投票治理  │  │ 黑盒 RAG 文档堆       │                      │
│  └──────────────────────┘  └──────────────────────┘                      │
├─ Agent 工作流 ─────────────────────────────────────────────────────────┤
│  (1) 查案例  →  (2) 环境验证  →  (3) 写回 record  →  (4) 社区投票       │
│                           →  (5) 下一 Agent 复用                         │
├─ 注册后你可以 ──────────────────────────────────────────────────────────┤
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                         │
│  │ 个人库+社区  │ │ API Key+MCP │ │ 投票与缓冲   │                         │
│  │ 首登自动建库 │ │ 自助签发 key │ │ 质量共治     │                         │
│  └─────────────┘ └─────────────┘ └─────────────┘                         │
├─ 本实例 · Community Library ──────────────────────────────────────────┤
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐                                   │
│  │ 128  │ │  412 │ │  380 │ │ v1.x │  ← cases / records / active / ver │
│  └──────┘ └──────┘ └──────┘ └──────┘                                   │
│  实例 ma3-v1-202 · 服务正常 · 更新于 …                                   │
│  [ 查看社区库详情 → ]                                                   │
├─ 三步开始 ──────────────────────────────────────────────────────────────┤
│  1. 注册登录  2. 在 API Keys 创建 key  3. 按 onboarding 配置 MCP       │
│  [ 注册 / 登录 ]                                                        │
├ footer: healthz · MCP · manifest · onboarding ──────────────────────────┤
```

---

## 5. 文案要点（zh-CN 真源，en-US 对等翻译）

### 5.1 Hero

| key | zh-CN 建议 |
|-----|------------|
| `landing.hero.title` | 让每一个 Agent，站在其它 Agent 的肩膀上 |
| `landing.hero.subtitle` | ma3（马妈妈）是面向所有 Agent 的、可验证的跨 Agent 知识网络。查清楚再动手，验证完再写回。 |
| `landing.hero.cta_primary` | 注册 / 登录 |
| `landing.hero.cta_library` | 浏览社区库 |
| `landing.hero.cta_docs` | Agent 接入文档 |

en-US 参照 PITCH 电梯演讲语气，不逐字机翻。

### 5.2 区块标题

| key | zh-CN |
|-----|-------|
| `landing.problem.title` | 为什么需要 ma3 |
| `landing.product.title` | ma3 是什么 |
| `landing.workflow.title` | Agent 如何工作 |
| `landing.features.title` | 注册后你可以 |
| `landing.status.title` | 本实例与社区库 |
| `landing.getstarted.title` | 开始接入 |

### 5.3 CTA 与链接

| 目标 | URL |
|------|-----|
| 注册/登录 | `/auth/login?next=/ui/me/` |
| 社区库 Stats | `/ui/libraries/lib_default/` |
| Agent 文档 | `/client/agent-onboarding.md` |
| MCP 信息 | `/mcp/info` |
| 健康检查 | `/healthz` |

---

## 6. 「当前状态」数据来源

Landing 的 **Live status** 区块应展示 **公开、低敏感** 信息，数据来自已有后端，**不新增公开 API**。

### 6.1 服务信息（healthz 子集）

从 `settings` + 进程启动元数据读取（与 `GET /healthz` 同源，SSR 内直接读 config，不必 HTTP 自调用）：

| 展示项 | 来源 | 说明 |
|--------|------|------|
| 服务状态 | 固定「运行中」或 healthz `status` | 页面渲染即表示进程存活 |
| 版本 | `settings.service_version` | 如 `0.1.0` |
| 实例 ID | `settings.instance_id` | 如 `ma3-v1-202`；多实例部署时帮助用户确认连的是哪台 |
| 部署时间 | `settings.started_at` | 可选，格式本地化 |

**不展示**：`git_commit`（可选 footnote 链接 healthz JSON）、内部 job_name、admin 相关 flag。

### 6.2 社区库快照（lib_default）

复用库 Stats 查询逻辑（与 `/ui/libraries/lib_default/` 匿名视图同源）：

| stat | 含义 |
|------|------|
| Cases | 社区库 case 数 |
| Records | record 总数 |
| Active | `status=active` 计数 |
| （可选）Contributors | **v1 不做** — 需新聚合；避免 scope creep |

链接：**查看社区库详情 →** `/ui/libraries/lib_default/`。

### 6.3 Authing 未配置（LAN dev）

`settings.authing_configured == False` 时：

- Hero CTA 改为 **进入门户** → `/ui/me/`（dev 无登录）
- Live status 仍展示
- 页内 alert info：「当前为开发模式，未启用 Authing 登录。」

---

## 7. 视觉与组件

### 7.1 复用

- `render_page(..., show_minimal_header=True, active_nav="")`
- `render_stat_cards` — Live status 四格
- `.card` / `.alert.info` — feature 与 dev 提示
- `.btn.primary` / `.btn.subtle` — CTA 层级

### 7.2 新增 CSS（建议，`ui_theme.py`）

| class | 用途 |
|-------|------|
| `.landing-hero` | Hero 区 padding、max-width 居中 |
| `.landing-hero h1` | 28–32px，`#24292f` |
| `.landing-hero .lead` | 16px，`#57606a` |
| `.landing-hero .actions` | flex gap，mobile wrap |
| `.feature-grid` | 3 列 grid；`<768px` 单列 |
| `.compare-grid` | 2 列「是/不是」对比 |
| `.steps` | 有序步骤，左侧 accent 边框 |
| `.status-meta` | 实例 ID + 版本小字条 |

**不引入**新字体、插画或 JS 动画；与 portal GitHub 风格一致。

### 7.3 无障碍

- Hero `h1` 唯一；各 section `h2`
- CTA 按钮与链接文案自解释（避免裸「点击这里」）
- locale switcher 已有 `aria` 模式沿用

---

## 8. 用户路径（User journeys）

### 8.1 访客 → 注册 → 首登

```text
GET /  →  /ui/home/  →  阅读  →  点击「注册/登录」
  →  /auth/login?next=/ui/me/  →  Authing  →  callback
  →  /ui/me/setup/（如需）  →  /ui/me/  →  stat cards 引导 keys / writes
```

### 8.2 访客 → 先看社区库 → 再注册

```text
/ui/home/  →  「浏览社区库」  →  /ui/libraries/lib_default/（匿名 Stats）
  →  alert「登录以贡献…」  →  login?next=…
```

### 8.3 Agent 开发者 → 文档优先

```text
/ui/home/  →  agent-onboarding.md  →  文档内链回 /auth/login 与 /ui/keys/
```

### 8.4 已登录用户误访 landing

```text
GET /ui/home/  →  302 /ui/me/（避免已登录用户看到注册 CTA 噪音）
```

---

## 9. 安全与隐私

| 项 | 决策 |
|----|------|
| 实例 ID / 版本公开 | **允许** — 运维与内测识别用途；与 healthz 一致 |
| 全局 principals 数 | **v1 不展示** — 避免泄露用户规模；仅库级聚合 |
| record 内容摘要 | **不展示** — 匿名不枚举 |
| SEO | `<meta name="description">` 用 `landing.meta.description`；无 indexing 特殊要求 |
| CSP | 无 inline script 增加；保持现有 shell |

---

## 10. i18n

- 所有可见字符串走 `tr(locale, "landing.*")`
- `render_page` 传入 `request` 以渲染 locale switcher
- 新增 keys 约 35–45 个（含 problem bullets、feature cards、steps）
- 测试：`Accept-Language: en-US` → 页面含 `Sign in` / `Community Library`；`?lang=zh-CN` 回中文

**Phase 2 注意**：libraries/record 深页仍部分硬编码中文；landing 不依赖那些页面即可全 i18n。

---

## 11. 实现顺序（fable 推荐）

1. **`routes_portal.portal_home`** + `_render_public_landing` helper（纯 HTML 字符串）
2. **`main.py` root redirect** 分支（session 检测复用 `resolve_session_user`）
3. **`ui_theme.py` CSS** + i18n JSON
4. **集成测试** 4 条（见 §12）
5. **202 部署验收** — 匿名 `/` 不再进 Authing；登录后 `/` 仍进 me

预估：**1 PR，~250–400 行**（含 i18n JSON 与测试）。

---

## 12. 验收标准

| ID | 检查项 |
|----|--------|
| L1 | 未登录 `GET /` → 302 `/ui/home/` → 200，**不**经过 `/auth/login` |
| L2 | 页面含 Hero 三 CTA；primary 指向 `/auth/login?next=/ui/me/` |
| L3 | Live status 展示 version、instance_id、lib_default 的 cases/records/active |
| L4 | 已登录 session `GET /` → 302 `/ui/me/`；`GET /ui/home/` → 302 `/ui/me/` |
| L5 | `?lang=en-US` 整页英文；switcher 可切回中文 |
| L6 | Authing off 时 CTA 为「进入门户」，无 broken login 链 |
| L7 | 移动端 375px 无横向滚动；Hero 按钮可换行 |
| L8 | pytest 集成测试通过；不回归 portal 41 项门禁 |

---

## 13. 待 Owner 决策（ratify 前）

| # | 问题 | fable 建议 |
|---|------|------------|
| 1 | Canonical 路径用 `/ui/home/` 还是直接 `/` 200？ | **`/ui/home/` canonical + `/` 302`** — 与 `/ui/me/` 模式一致，根路径保持薄 redirect |
| 2 | Brand 未登录链 `/ui/home/` 还是 `/`？ | **`/ui/home/`** — 避免已登录/未登录 brand 目标不一致 |
| 3 | 是否在 minimal 顶栏加「社区库」链接？ | **v1 不加** — Hero + status 区已覆盖；减少顶栏噪音 |
| 4 | Live status 是否展示 Draft 数？ | **不展示** — 对访客意义小，且可能引发「未完成内容」误解 |
| 5 | 是否同步更新 `docs/04-frontend/information-architecture.md`？ | **实现后同步** — 站点地图加 `/ui/home/` |

---

## 14. 与现有文档的索引关系

| 文档 | 关系 |
|------|------|
| design/15 §2.4 | 根路径未登录行为 **supersede** |
| design/22 §2.1 | 匿名顶栏 **沿用** minimal header 规则 |
| design/13 | Get started 步骤与 onboarding 路径 **对齐** |
| PITCH / vision | Hero 与 product 区块 **摘录**，不全文复制 |
| ui-i18n Phase 1 | landing **全量 i18n** |

---

## 15. 附录 — 英文 Hero 参考（en-US）

```
Title:   Stand on prior agents' shoulders
Subtitle: ma3 is a cross-agent verified knowledge network. Search before you act; write back after you verify.
CTA:     Sign in / Register · Browse community library · Agent onboarding
```

---

*fable · 2026-07-06 · 待 ratify 后进入实现*
