# Review: 24 — Organization & Library Management

> **Reviewer**: GPT-5.5  
> **Date**: 2026-07-06  
> **Scope**: [24-org-library-management-fable.md](24-org-library-management-fable.md)、[24-org-library-management-visual-fable.md](24-org-library-management-visual-fable.md)  
> **Cross-check**: `db.py`（无 `org_members`）、`storage_quota_service.py`、`routes_portal.py` 库设置、`design/09` billing schema

## 1. Verdict

**ACCEPT-WITH-NITS**

方向正确：把 design/15 延期的 org/grants/枚举 UI 收成 v1.1 可交付切片，并与刚落地的 **personal storage quota** 在门户侧闭环。顶栏加「组织」、404 而非 403、Observatory 与 org 业务分离——与 ADR-011/015 一致。

实现前需钉死：**entitlement_service 替换时机**、**team 创建与 billing 的空实现边界**、**library_grants 与 api_key_grants 双写是否允许**。

---

## 2. Blocking Issues

### B1 — `entitlement_service` 必须是 Phase O1 门禁，不能与 UI 并行

fable Phase O2 起 UI 依赖 `list_orgs_for_principal` / org member 判定，但库列表、record 详情、`/grants/` 均依赖 **Layer-1 entitlement**。若 O2 先 ship 而 O1 未完成，会出现：

- org 库对已添加 member 仍不可见（key grants 启发式）
- `/ui/libraries/{id}/records/` 与 MCP 读权限不一致

**Fix**：Acceptance 要求 Phase O1 合并进同一 release branch；`list_entitled_libraries_for_principal` 签名不变（design/15 §8.2），仅换实现。加集成测试：org member 无 key 仍可见 org library Stats。

### B2 — personal org bootstrap 与现有 `ensure_personal_library` 顺序

fable 要求 `ensure_personal_org` 在 personal library 之后，并回填 `libraries.org_id`。须明确：

- 已存在用户 migration：一次性 backfill script
- `org_personal_{sub}` id 确定性算法（与 `personal_library_id` 同风格）
- personal org 的 `owner_principal_id` = 用户本人；`org_members(admin)` 仅一行

**Fix**：在 §7.1 追加 migration 小节 + id 公式；启动时 doctor 检查 orphan library（有 personal kind 无 org_id）。

---

## 3. Non-Blocking Nits

1. **Q1 team 创建**：建议 **Phase O5 可裁剪**——O2–O4 用 seed org 测 UI；避免 billing 未就绪阻塞 org 管理主体功能。
2. **`/ui/libraries/{id}/storage/` 与 settings 合并？** 视觉稿拆两页合理（设置=行为，存储=计量）；v1.1 可在 settings 卡嵌入 mini meter，storage 页放 tier 表。
3. **grants 添加 maintainer 角色**：须写清 maintainer entitlement 是否自动包含 read/write（design/08 Layer-1 应 yes）。
4. **records 枚举默认 filter**：建议默认 `status=active`，避免 maintainer 被 draft/buffered 淹没；与 Observatory 行为对齐。
5. **org 存储汇总**：Team pooled bytes 若 billing 未实现，UI 显示「— / 联系管理员」而非假 10GB。
6. **i18n**：`portal.nav.orgs` 英文 Organizations 略长，顶栏可接受；mobile 未定义 org 顶栏折叠——可复用 768px 规则（visual §10）。
7. **JSON API defer 正确**——SSR first 符合项目约束。

---

## 4. What I Agree With

1. **顶栏「组织」与「库」并列** — 比塞进 `/ui/me/settings` 更符合 mental model。
2. **J3 添加成员需先登录** — 与 v1 acceptance 一致，避免 orphan principal（acceptance nit）。
3. **库 maintainer 枚举单库 records** — 填补 Observatory 403 后库管真空。
4. **storage meter + ma3_whoami 一致** — MCP/门户双端同一 `storage_quota_service`。
5. **404 隐藏存在性** — org/library 直链策略与 design/15 统一。
6. **产品 admin 不代管 org** — 避免 Observatory 膨胀为 super-admin CRUD。
7. **visual 复用 `.data` / list-footer** — 无新 CSS 预算风险。

---

## 5. Scope Check

v1.1 范围合适：schema + entitlement + org 成员 + library grants/records + storage 可视化。不应同期做 Stripe、invite link、MCP org API。

**建议合并**：刚实现的 `storage_quota_service` 应在 Phase O4 一并交付 UI，否则用户仍只能从 MCP 403 感知限额。

---

## 6. Disagreements with Fable

### D1 — library_grants 与 api_key_grants 关系

| | |
|---|---|
| **Fable** | UI 分层说明；各自管理 |
| **GPT-5.5** | 仅 library_grants 无 key grant → MCP 仍不可读写；门户应 **warn** 或 wizard「为此用户创建 key」链到 `/ui/keys/` |
| **严重度** | nit → v1.2 |

### D2 — org 库创建默认 visibility

| | |
|---|---|
| **Fable** | 默认 `org` |
| **GPT-5.5** | 默认 `private` 更安全；`org` 需 confirm「所有成员可见」 |
| **选项** | 产品选；倾向 private default + 文案 |

### D3 — Phase 顺序

| | |
|---|---|
| **Fable** | O1→O5 五段 |
| **GPT-5.5** | O1+O4 同 release（quota 已上线）；O5 team 创建可 last |

---

## 7. Recommended Acceptance Additions

| ID | 测试 |
|----|------|
| O11 | org member 无 API key 可 GET org library Stats |
| O12 | library_grants writer 仍须 key grant 才能 MCP 写（文档化） |
| O13 | personal org backfill 幂等 |
| O14 | storage 页 used_bytes 与 DB sum 一致 ±1 record |

---

## 8. Summary

**ACCEPT-WITH-NITS** — 可进入 ratify；实现时 **O1 entitlement 阻塞 UI**，补 migration/id 公式，Team 创建与 billing 可末位交付。与 storage quota 门户化建议同 release。

---

*GPT-5.5 · 2026-07-06*
