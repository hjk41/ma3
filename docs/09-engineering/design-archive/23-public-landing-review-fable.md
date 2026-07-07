# Review — 23 公开默认页实现（fable）

> **Reviewer**: fable  
> **Verdict**: **PASS-WITH-NITS**  
> **设计真源**：[23-public-landing-page-fable.md](23-public-landing-page-fable.md)、[23-public-landing-visual-fable.md](23-public-landing-visual-fable.md)  
> **部署验收**：`192.168.31.202:8000`（2026-07-06）

---

## 通过项

1. **路由语义正确** — 未登录 `GET /` → 302 `/ui/home/` → 200；不再强制 Authing；已登录 `GET /ui/home/` → 302 `/ui/me/`（L4）。
2. **视觉布局对齐** — Hero 居中、六段 `.landing-section`、compare 2 列、feature 3 列、flow flex 步骤条；复用 `.btn` / `.card` / `.grid.stats`，无新依赖。
3. **顶栏 minimal header** — brand → `/ui/home/`；仅「登录 + locale switcher」；无空 topnav（符合 22 review nit #4）。
4. **CTA 层级** — Hero primary → `/auth/login?next=/ui/me/`；次 CTA 社区库与 onboarding 文档；Get started 底栏重复 primary。
5. **Live status** — lib_default cases/records/active + version + instance meta；不暴露 principals 全局数（§9 安全）。
6. **i18n** — `landing.*` 全量 zh-CN / en-US；`Accept-Language: en-US` 验收通过；switcher 可用。
7. **Authing off 分支** — dev alert +「进入门户」→ `/ui/me/`（L6）。
8. **测试** — `test_public_landing.py` 6 项 + portal/i18n 回归 31 passed。

---

## 验收对照（design/23 §12）

| ID | 结果 | 备注 |
|----|------|------|
| L1 | ✅ | `/` → `/ui/home/`，不经 login |
| L2 | ✅ | 三 CTA + primary login |
| L3 | ✅ | stats + instance + version |
| L4 | ✅ | 已登录 redirect me |
| L5 | ✅ | en-US 整页 |
| L6 | ✅ | pytest dev mode |
| L7 | ⚠️ | 未做 375px 截图；CSS 有 `@768px` 规则，**建议 owner 浏览器 spot-check** |
| L8 | ✅ | pytest 通过 |

---

## Nits（非阻塞）

1. **顶栏「登录」vs Hero「注册 / 登录」** — minimal header 仍用 `common.login`（「登录」），Hero 用 `landing.hero.cta_primary`（「注册 / 登录」）。语义可接受；若需统一可 v1.1 加 `landing.header.login`。
2. **`auth/login?next=` 含绝对 URL** — 当 `public_base_url` 未设时 next 为 `http://host/ui/me/`；Authing 仍可用，但与 path-only next 略不一致；非 landing 独有问题。
3. **Get started 步骤 1 写「Authing」** — en/zh 均点名 Authing；若未来换 IdP 需改 copy；v1 可接受。
4. **Version stat 与 status meta 重复** — stat 卡与 meta 行均含 version；视觉略冗余，不影响功能。
5. **IA 未同步** — `docs/04-frontend/information-architecture.md` 仍无 `/ui/home/`；实现后应补一行（owner 文档债）。
6. **已登录用户 brand 仍链 `/ui/me/`** — landing 页 brand 链 `/ui/home/` 正确；登录后其它页 brand 仍 `/ui/me/`（design/22）；一致。

---

## 实现与真源映射

| 设计 class | 代码 |
|------------|------|
| `.landing-hero*` | `ui_theme.py` MA3_CSS |
| `_render_public_landing` | `routes_portal.py` |
| `/ui/home/`、`/` redirect | `routes_portal.py` `portal_root` / `portal_home` |
| i18n | `i18n/zh-CN.json`, `en-US.json` |
| meta description | `render_page(..., meta_description=...)` |

---

## 建议后续（非 v1 阻塞）

- Owner 375px 截图入 acceptance 附件
- 同步 `docs/04-frontend/information-architecture.md` 站点地图
- 考虑 `/ui/home/` 在 sitemap / 分享 OG tag（`og:title` / `og:description`）— v1.1

---

*fable · 2026-07-06 · PASS-WITH-NITS*
