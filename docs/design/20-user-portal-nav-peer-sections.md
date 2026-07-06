# 20 — 门户顶栏：库 / 记录 / 投票 / API Keys 同级目录（fable）

> **状态**：**已并入 design/22**（§2.1–2.2）— 保留作需求溯源  
> **真源**：[22-user-portal-ui-unified-layout-fable.md](22-user-portal-ui-unified-layout-fable.md)

> **状态**：需求已定（2026-07-05，owner 提出）  
> **实现**：**未开始** — 见 [21-user-portal-enhancements-backlog.md](21-user-portal-enhancements-backlog.md)  
> **关联**：[15-user-portal-fable.md](15-user-portal-fable.md)、[19-user-portal-writes-list-enhancements.md](19-user-portal-writes-list-enhancements.md)

---

## 0. 一句话结论

**库、记录、投票、API Keys** 四类「可管理资源」应在 **同一级顶栏** 并列；**我的主页** 仅保留概览仪表盘与账户（subnav：**概览 | 设置**）。

Owner：**对库、记录、投票、API key 的管理应该是同一级的目录。**

**现网顶栏**：我的主页 · Libraries · API Keys  
**现网 subnav**：概览 · 我的贡献 · 我的投票 · 设置

---

## 1. 目标顶栏（ratified）

| key | 标签 | 路径 |
|-----|------|------|
| `me` | 我的主页 | `/ui/me/` |
| `libraries` | 库 | `/ui/libraries/` |
| `records` | 记录 | `/ui/me/writes/` |
| `votes` | 投票 | `/ui/me/votes/` |
| `keys` | API Keys | `/ui/keys/` |
| `observatory` | Observatory | `/ui/observatory/`（admin） |

- Brand → `/ui/me/`
- **v1 不改 URL**（记录/投票仍 `/ui/me/writes|votes/`）；`active_nav` 高亮 `records` / `votes`

---

## 2. `/ui/me/` subnav（仅账户）

| tab | 路径 |
|-----|------|
| 概览 | `/ui/me/` |
| 设置 | `/ui/me/settings/` |

**移除**：我的贡献、我的投票（改由顶栏「记录」「投票」进入）。

---

## 3. 文案对齐

| 位置 | 现网 | 目标 |
|------|------|------|
| 库列表 `<h1>` | Libraries | **库** |
| writes `<h1>` | 我的贡献 | **记录** |
| votes `<h1>` | 我的投票 | **投票** |
| stat cards | 我的贡献 / 我的投票 | **记录 / 投票** |

---

## 4. 不在范围

- `/ui/records/`、`/ui/votes/` URL 迁移（v1.1）
- 库内 record 枚举

---

## 5. 实现映射（计划）

| 文件 | 变更 |
|------|------|
| `ui_theme.py` | `portal_nav_items` 五项；`render_subnav` 两项 |
| `routes_portal.py` | writes/votes 无 subnav；`active_nav`；标题/stat 文案 |

---

## 6. 验收

见 acceptance **P19**。

- [ ] 顶栏：我的主页 · 库 · 记录 · 投票 · API Keys
- [ ] writes/votes 页顶栏高亮对应项，无 account subnav
- [ ] `/ui/me/` 保留 subnav「概览 | 设置」
