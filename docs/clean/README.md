# ma3 设计文档（整理版）

> **整理日期**：2026-07-06  
> **用途**：单一入口 — 当前有效设计的真源集合  
> **规则**：实现与验收以本文「真源地图」为准；`docs/design/` 中未列入真源的 `*-review-*`、`*-discussion-*`、早期线框文档仅作历史参考。

---

## 1. 真源地图（按主题）

| 主题 | 文档 | 验收 |
|------|------|------|
| 愿景与原则 | [00-vision.md](00-vision.md)、[PITCH.md](../pitch/PITCH.md) | — |
| 问题陈述 | [01-problem-statement.md](01-problem-statement.md) | — |
| 目标架构 | [04-target-architecture.md](04-target-architecture.md) | — |
| KB 访问与 org 隔离 | [08-kb-access-and-org-isolation.md](08-kb-access-and-org-isolation.md)、[ADR-011](../adr/011-kb-access-and-org-isolation.md) | — |
| 付费套餐与配额 | [09-billing-and-quotas.md](09-billing-and-quotas.md)、[ADR-012](../adr/012-billing-and-quotas.md) | — |
| 写入审计与删除 | [10-write-audit-and-delete.md](10-write-audit-and-delete.md)、[ADR-013](../adr/013-write-confirmation-audit-delete.md) | — |
| MCP 错误契约 | [11-mcp-error-contract.md](11-mcp-error-contract.md)、[ADR-014](../adr/014-mcp-error-self-correction.md) | — |
| 搜索排序 | [12-search-ranking.md](12-search-ranking.md) | — |
| 自助注册 / onboarding | [13-self-service-onboarding.md](13-self-service-onboarding.md) | [v1-self-service-onboarding](../acceptance/v1-self-service-onboarding.md) |
| API Key 生命周期 | [14-api-key-lifecycle.md](14-api-key-lifecycle.md) | [v1-api-key-lifecycle](../acceptance/v1-api-key-lifecycle.md) |
| 用户门户 **权限基线** | [15-user-portal.md](15-user-portal.md) | [v1-user-portal](../acceptance/v1-user-portal.md) P1–P12 |
| 用户门户 **IA + 布局** | [22-user-portal-ui-layout.md](22-user-portal-ui-layout.md) | P13–P19 |
| 用户门户 **视觉** | [15-user-portal-visual.md](15-user-portal-visual.md) | P12 |
| 显示名注册 | [17-display-name-registration.md](17-display-name-registration.md) | [v1-display-name-registration](../acceptance/v1-display-name-registration.md) |
| Write buffer | [16-library-write-buffer.md](16-library-write-buffer.md) | [v1-library-write-buffer](../acceptance/v1-library-write-buffer.md) |

---

## 2. 已 ratified 决策（统一表）

### 2.1 用户门户

| # | 议题 | **决定** |
|---|------|----------|
| P1 | 非 admin 访问 Observatory | **403**（非 302） |
| P2 | Authing 已启用且 admin 白名单为空 | **拒绝启动** |
| P3 | 非 admin 库详情 | **Stats only**，不可枚举 record |
| P4 | 匿名访客 | 仅 **public 库 Stats**；无 record 详情 |
| P5 | 默认落地 | **`/ui/me/`** |
| P6 | Principal ID 展示 | **仅 `/ui/me/settings/`**，只读、**无复制** |
| P7 | 显示名 | **`/ui/me/setup/` 一次性设定**；settings 只读 |
| P8 | 顶栏 IA | 我的主页 · **库 · 记录 · 投票 · API Keys**（同级） |
| P9 | 账户 subnav | 仅 `/ui/me/*`：**概览 · 设置** |
| P10 | 列表页文案 | h1 / stat：**记录、投票** |
| P11 | Stat cards | 5 张整卡可点：记录、待发布、可访问库、投票、API Keys |
| P12 | 记录/投票列表 | sort + filter + per_page + list-footer；记录页 buffered 批量操作 |
| P13 | 个人库名 | `{display_name} 的个人库`，`ensure_personal_library` 同步 |

### 2.2 Write buffer

| # | 议题 | **决定** |
|---|------|----------|
| B1 | 默认 `write_buffer_hours` | **24**；personal owner **可设 0** |
| B2 | PATCH 后计时 | **重置** `publish_at = now + hours` |
| B3 | 修改语义 | **同 record_id 覆盖** |
| B4 | 写入者权威 | `write_audit_log.principal_id` |
| B5 | UI | v1 即带：`/ui/me/writes/` + `/ui/records/{id}/` 操作区 |
| B6 | Stats | buffered **不计入**公共 active；作者侧「待发布」计数 |
| B7 | 用户说明 | 写入 **Community 公共库** |

### 2.3 API Key

| # | 议题 | **决定** |
|---|------|----------|
| K1 | 撤销语义 | 用户侧统一 **删除**，非「撤销/已撤销」 |
| K2 | plaintext | 加密存储；列表/详情可重复展示；详情页 **不可再复制完整 key** 的约束已放宽为 owner 可重复 copy（ciphertext decrypt 成功时） |
| K3 | JSON label 校验 | 超 120 字符 → **422**（SSR form 仍 truncate） |
| K4 | legacy revoked 行 | 列表过滤（`revoked_at IS NULL`），不参与配额 |

---

## 3. 明确不做（v1，跨文档统一）

| 项 | 说明 |
|----|------|
| SPA / 客户端路由 | SSR + query string 列表态 |
| 非 admin **库内 record 枚举** UI | 仅 Stats + 单条深链 |
| Export 批量导出 | v1.1+，可计费 |
| Org 管理 UI | v1.1（`/ui/orgs/*`） |
| Grants 管理 UI | v1.1 |
| URL 美化 `/ui/records/`、`/ui/votes/` | v1.1 |
| 顶栏 hamburger / responsive 专项 | v1 接受 flex 换行 |
| 投票列表 **批量改票** | 改票仅在 record 详情 |
| Observatory 中文化 | 保留英文 |
| 概览页 **Principal ID + 复制** | → 见 settings 只读 |
| 概览页 **编辑显示名** | → setup 一次性 |
| subnav **我的贡献 / 我的投票** | → 顶栏「记录」「投票」 |
| 顶栏文案 **Libraries** | → **库** |
| community browse/search UI | 与 Stats≠Enumerate 一致 |
| `ma3_ui_session` 匿名 cookie 签 key | onboarding 安全约束 |
| MCP `ma3_create_key` 等签发工具 | v1.1 |
| revoke 路由 / 「撤销」文案 | → 硬删除（design/14） |
| `ma3_search_explain` / `include_explain` | 排序 explain 仅内部/Observatory |

---

## 4. 文档阅读顺序（新人）

1. [00-vision.md](00-vision.md) + [PITCH.md](../pitch/PITCH.md) — 为什么做 ma3
2. [04-target-architecture.md](04-target-architecture.md) — 系统形态与 Agent 契约
3. [08-kb-access-and-org-isolation.md](08-kb-access-and-org-isolation.md) — 谁能读写什么
4. [13-self-service-onboarding.md](13-self-service-onboarding.md) + [14-api-key-lifecycle.md](14-api-key-lifecycle.md) — 用户如何接入
5. [15-user-portal.md](15-user-portal.md) + [22-user-portal-ui-layout.md](22-user-portal-ui-layout.md) — 登录后 UI
6. [10-write-audit-and-delete.md](10-write-audit-and-delete.md) + [16-library-write-buffer.md](16-library-write-buffer.md) — 写入与撤回
7. [11-mcp-error-contract.md](11-mcp-error-contract.md) + [12-search-ranking.md](12-search-ranking.md) — Agent 体验细节

---

## 5. 与 `docs/design/` 的关系

| `docs/design/` 原文档 | 整理版处置 |
|------------------------|------------|
| `00-vision.md` | → [00-vision.md](00-vision.md)（加索引链接） |
| `01-problem-statement.md` | → [01-problem-statement.md](01-problem-statement.md)（补 buffer 状态） |
| `02-current-state-audit.md` | **未纳入** — 2026-07-01 审计快照，仅供迁移参考 |
| `03-design-review.md` | **未纳入** — 讨论过程；结论已吸收进 04 + ADR |
| `04-target-architecture-draft.md` | → [04-target-architecture.md](04-target-architecture.md)（合并门户/buffer/Authing 修订） |
| `05-doc-code-mapping.md` | **未纳入** — 代码映射；随实现更新 |
| `06-pitch-alignment-review.md` | **未纳入** — 评审历史 |
| `07-kb-read-write-review.md` | **未纳入** — 评审历史 |
| `08`–`17` 主设计稿 | → 对应 `docs/clean/` 编号文档 |
| `15-user-portal-fable.md` | → 拆为 [15-user-portal.md](15-user-portal.md) + [22-user-portal-ui-layout.md](22-user-portal-ui-layout.md) |
| `15-user-portal-decisions-for-owner.md` | → 并入 README §2 + 15 |
| `15-user-portal-me-profile-review-fable.md` | → 并入 15 / 17 / 22 |
| `15-user-portal-visual-sonnet5.md` | → [15-user-portal-visual.md](15-user-portal-visual.md)（去掉废止线框） |
| `18`–`21` 门户增强 | → 已并入 [22-user-portal-ui-layout.md](22-user-portal-ui-layout.md) |
| `14-api-key-lifecycle-layout-fable.md` | → 并入 [14-api-key-lifecycle.md](14-api-key-lifecycle.md) §5 |
| `16-library-write-buffer-layout-fable.md` | → 并入 [16-library-write-buffer.md](16-library-write-buffer.md) |
| `16-library-write-buffer-decisions-for-owner.md` | → 并入 README §2 + 16 |
| `*-review-*.md`、`*-discussion-*.md` | **历史归档**，非实现真源 |
| `00-design-index-fable.md` | → 由本 README 替代 |

---

## 6. v1.1 预留（勿在 v1 实现）

- `/ui/orgs/*`、entitlement resolver 替换启发式
- `/ui/libraries/{id}/records/` 库管理员枚举
- `/ui/libraries/{id}/grants`
- Export、URL 美化、settings 页 Principal ID 复制（可选）
- Billing 完整 enforcement + Stripe UI（[09](09-billing-and-quotas.md) Phase B3–B4）
- MCP `ma3_create_key` / `ma3_list_keys`
- hybrid search golden / refute-verify 显式 bump（[12](12-search-ranking.md) follow-up）

---

## 7. 维护约定

1. **新 ratified 决策** → 更新本 README §2，并在对应真源文档交叉引用。
2. **IA / 布局变更** → 只改 [22-user-portal-ui-layout.md](22-user-portal-ui-layout.md)（或新编号统一稿）。
3. **评审文档** → 只追加在 `docs/design/`，不当作 spec；过时结论在 `docs/clean/` 删除，不在 review 里改历史。
4. **验收** → `docs/acceptance/v1-*.md` 与真源对齐后 sign-off。
