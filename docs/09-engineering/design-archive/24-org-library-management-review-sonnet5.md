# Review — 24-org-library-management-fable — sonnet-5

> **Reviewer**: sonnet-5  
> **Date**: 2026-07-06  
> **Scope**: [24-org-library-management-fable.md](24-org-library-management-fable.md)、[24-org-library-management-visual-fable.md](24-org-library-management-visual-fable.md)  
> **Method**: cross-check `db.py`、`routes_portal.py`、`onboarding_service.py`、`storage_quota_service.py`、`write_audit_service.py`、`design/08`、`design/09`

## 1. Verdict

**REQUEST-CHANGES**

IA 与动线整体可用，视觉稿与 design/22 兼容。但有三处与**当前代码/安全模型**对撞，若不修订会在实现中途返工：**(1) `is_library_settings_editor` 与 maintainer 语义分裂**；**(2) org_members 表不存在却假定只读路径已安全**；**(3) record 枚举 UI 与 buffered 可见性规则需显式对齐 design/16**。

修文档即可，无需推翻方案。

---

## 2. Blocking Issues

### B1 — 库设置权限 vs 新「maintainer」路由权限

Today `is_library_settings_editor`（`buffer_service.py`）= product admin **或** `owner_principal_id == me`（personal owner）。

fable §5 把 `/records/`、`/grants/` 给 **库 maintainer+**，但 `/settings/` 仍仅 owner。会出现：

- team org 库：org admin 能枚举 record，却不能改 `write_buffer_hours`（合理？需产品一句话）
- 外部 `library_grants.role=maintainer` 能看 `/records/`，却不能进 `/settings/` — OK，但须在 UI 管理卡禁用「库设置」按钮，仅显示「记录/授权」

**Fix**：新增 `is_library_maintainer(library_id, principal_id)` 统一 grants + org admin + personal owner；`is_library_settings_editor` 保持更窄。文档 §5 矩阵加 footnote：settings 仅 owner + product admin（team 库 owner 字段为空时 **org admin 可改 settings**——today 无 owner 字段，会 dead-end）。

**推荐**：`libraries` 增加 `created_by` 或 team 库 `owner_principal_id` 指向创建者 org admin；或规定 team 库 settings 由 **任一 org admin** 可编辑。

### B2 — Schema 落地前 entitlement 不能部分切换

`grep org_members` → **0 matches** in `code/server`. fable Phase O1 正确，但 J1/J3 文案暗示「成员侧自动看见 org」——在表不存在时集成测试会全红。

**Fix**：§9 Phase 表加 **hard gate**：无 `org_members` migration merged 则不 merge `/ui/orgs/*` 路由。doctor 输出 `org_management_ready: false`。

### B3 — `/ui/libraries/{id}/records/` 与 buffered 404 规则

design/16：buffered 对他人 404 + 不可搜索。库 maintainer **是否算「他人」**？

- 若 org admin 应审 buffered → 列表需含 buffered，但仅 **author 行**可点详情；其他 maintainer 行显示「待发布（仅作者可见）」
- 若 maintainer 完全不可见 buffered → 与 product admin Observatory 能力不一致

**Fix**：fable §6.6 加一行：**maintainer 可见 buffered 行 metadata（status、时间、problem 前 120 字），详情链仅 author 可开**；或 maintainer 可 `ma3_publish_record` 代发（不建议 v1.1）。

### B4 — Storage quota 仅 personal，org 库 UI 勿误导

`assert_personal_library_write_allowed` 仅 `kind=personal`。fable J8/J6 org 存储汇总若显示 pooled limit，后端尚无 org bytes cap enforcement（design/09 Phase B3）。

**Fix**：org 库存储卡标注 **「计量预览；Team 限额 enforcement 跟随 billing Phase B3」**；personal 库才显示 hard limit 进度条。否则用户以为 org 库也 10MB。

### B5 — POST 表单 CSRF / same-origin

新 org member / grant / create library 全是 SSR POST。须复用 `routes_portal._assert_same_origin`（keys 页已有 pattern）。fable §7.4 未写 — 实现 checklist 漏项。

---

## 3. Non-Blocking Nits

1. **Principal ID 输入 UX**：members/grants 表单应链 `/ui/me/settings/`「复制 ID」— J3 文案已提，加 visual 线框链接。
2. **移除唯一 admin**：服务端拒绝 `remove last admin`；UI 禁按钮 — fable 仅 half 提到。
3. **create team org 名称**：`organizations.name` uniqueness 未定义；建议 `(owner, name)` 或全局 unique。
4. **list_records_for_library** 应用 `can_read_record` 过滤 buffered/draft，勿 raw SQL 泄露 private payload。
5. **顶栏 org 对 zero-team 用户**：仍显示「组织」合理（personal card）；避免 empty nav 404 — OK。
6. **`.storage-meter-bar.warn` 色** `#9a6700` 与 GitHub token 一致 — good。

---

## 4. What I Agree With

1. **组织与库分路由** — `/ui/orgs/*` vs `/ui/libraries/*` 清晰。
2. **grants 页 Layer-1/Layer-2 说明** — 降低 agent 用户混淆。
3. **404 非 403** — 与现有 portal 一致。
4. **Observatory 不参与 org CRUD** — 安全边界清楚。
5. **visual 不引入 chart.js** — 符合 SSR 约束。
6. **Phase 拆分 O1–O5** — 可 incremental merge。

---

## 5. Scope Check

v1.1 合理；不要一次做 invite link + Stripe + MCP org tools。

**必须同批**：storage personal UI（O4）+ 已有 `storage_quota_service`；否则 regression 体验。

---

## 6. Disagreements with Fable

### D1 — Team 库 settings 谁可编辑

| | |
|---|---|
| **Fable** | owner / product admin（沿用现 settings） |
| **Sonnet-5** | team 库无 owner 时 org admin 必须能改 buffer |
| **严重度** | **blocking（B1 子项）** — 需 ratify |

### D2 — org admin 是否自动 maintainer

| | |
|---|---|
| **Fable** | 矩阵 footnote *** maintain entitlement |
| **Sonnet-5** | 须在 `entitlement_service` 显式：`org admin → can_maintain all org libraries`；勿仅靠 UI 隐藏 |

### D3 — display name 搜索 defer v1.2

Agree — 但 v1.1 应提供 **copy-friendly** principal ID 在 members 表，monospace + copy button（design/14 pattern）。

---

## 7. Security Checklist（实现者）

- [ ] 所有 POST `_assert_same_origin`
- [ ] grant/member 添加校验 target principal 存在
- [ ] 不能 grant 高于自己的 role（member 不能 add admin grant）
- [ ] list_records 不返回无读权限的 payload_json 全文
- [ ] org_id path param 一律查 membership，不信任 client
- [ ] rate limit 添加成员（防 spray principal IDs）

---

## 8. Summary

**REQUEST-CHANGES** — ratify 前修订：

1. B1 team 库 settings 编辑者  
2. B3 buffered 在 records 列表的可见度  
3. B4 org vs personal 存储 UI 差异  
4. 追加 CSRF / security checklist  

修订后可 **ACCEPT-WITH-NITS** 进入 O1 实现。

---

*sonnet-5 · 2026-07-06*
