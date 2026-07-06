# Review — `/ui/me/` 概览页视觉（fable · owner 修订）

> **✅ ratified** — 决策已并入 [00-design-index-fable.md](00-design-index-fable.md) §2.1 P6–P7、[22](22-user-portal-ui-unified-layout-fable.md) §3.1–3.2

> **Reviewer**: fable  
> **Date**: 2026-07-05  
> **Scope**: `/ui/me/` 概览 vs `/ui/me/settings/` 账户信息分区  
> **Verdict**: **PASS**（按 owner 反馈修订后）

## 背景

初版实现把 **Principal ID 复制行** 和 **「编辑显示名」** 链接放在 `/ui/me/` 的 `.profile-header` 里（对齐 design/15 早期线框 §3.1）。Owner 反馈：概览页应聚焦**贡献与权限仪表盘**；账户标识与改名属于**设置**场景，不应占用首屏。

## Owner 决策（ratified）

| # | 决策 | 理由 |
|---|------|------|
| D1 | `/ui/me/` 只保留 **头像 + 显示名** | 概览页首屏给 stat cards / 库表 / 最近贡献 |
| D2 | **显示名** 仅在 **`/ui/me/setup/`** 注册时一次性设定；`/ui/me/settings/` 只读 | 设定后不可修改（见 design/17） |
| D3 | **Principal ID** 移到设置页第二张 card，**只读展示、无复制按钮** | 绝大多数用户只需显示名；ID 供排查时肉眼对照即可，不必在概览页强调 |
| D4 | API key 等**需要复制**的场景继续用 design/14 的 `copy-row` | 复制控件仅保留在 keys 页等操作型界面 |

## 修订线框

### `/ui/me/` — 概览（dashboard）

```
┌ topbar ─────────────────────────────────────────────────────────┐
│ [ma3] 我的主页 · Libraries · API Keys          显示名 · 退出     │
├─────────────────────────────────────────────────────────────────┤
│ .profile-header（仅 avatar + display_name，无 profile-meta）     │
│ .subnav-links  概览 | 我的贡献 | 我的投票 | 设置                  │
│ .grid.stats  我的贡献 | 待发布 | 可访问库 | 我的投票 | API Keys   │
│ card: 我的库                                                    │
│ card: 最近贡献                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**移除**：`编辑显示名` 链接、`Principal ID`、`copy-row` / `ma3CopyFrom`。

### `/ui/me/settings/` — 账户设置

```
┌ .profile-header（avatar + display_name，与概览一致）──────────────┐
│ .subnav-links  … | 设置 (active)                                │
│ card: 显示名 — 只读（注册时在 /ui/me/setup/ 设定，不可改）          │
│ card: Principal ID — .id-block（mono 只读，无复制按钮）           │
└─────────────────────────────────────────────────────────────────┘
```

**CSS 新增**：`.id-block` — muted 背景 + mono 字体 + `word-break: break-all`（见 `ui_theme.py`）。

## 通过项

1. **信息架构清晰**：概览 = 活动与权限；设置 = 身份与偏好。符合 GitHub「Profile overview vs Settings」分区习惯。
2. **与 subnav 一致**：「设置」tab 已是账户入口；去掉概览页重复链接后导航路径单一（topbar / subnav → settings）。
3. **复制控件收敛**：Principal ID 不再误用 keys 页的 `copy-row` 模式；减少概览页视觉噪音。
4. **实现成本低**：`_render_profile_header` 瘦身为纯展示；`_render_principal_id_card` 仅 settings 引用。

## Nits（非阻塞）

1. **设置页 subtitle** 可改为「账户与身份」以涵盖 Principal ID card（当前「自定义在 ma3 中显示的名字」略窄）。
2. **极少数支持场景**若需复制 Principal ID，v1.1 可在 settings 的 ID card 加「复制」而不回到概览页。
3. **design/15-user-portal-fable.md §3.1** 线框仍写「Principal ID v1 必展示」— 应勘误为「v1 必展示于 **设置页**」。

## 验收清单

- [x] `/ui/me/` HTML 不含 `编辑显示名`、`Principal ID`、`ma3CopyFrom`
- [x] `/ui/me/settings/` 含只读显示名 + Principal ID 只读块（无编辑表单）
- [x] `tests/integration/test_display_name_registration.py` 通过

## 实现映射

| 文件 | 变更 |
|------|------|
| `routes_portal.py` | `_render_profile_header` 瘦身；新增 `_render_principal_id_card` |
| `ui_theme.py` | `.id-block` |
| `tests/integration/test_user_portal.py` | 概览/设置分区断言 |
