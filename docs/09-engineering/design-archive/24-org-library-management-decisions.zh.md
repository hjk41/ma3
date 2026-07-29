# 24 — 组织与知识库管理（Org & Library Management）决策摘要

> 状态：已定稿并实现（2026-07-06 产品负责人 ratify；GPT-5.5 review ACCEPT-WITH-NITS、sonnet-5 review REQUEST-CHANGES 的 blocking 项均已在 ratify 决策中覆盖）。
> 本文为压缩归档的决策摘要；非契约，以 docs 正式层、ADR 与代码为准。

## 背景一句话

v1 个人门户之上，v1.1 补齐「组织 → 库 → 授权 → 容量」的人类管理闭环：org admin 管成员与 org 库，库 maintainer 管授权与库内枚举，用户可感知存储配额；产品管理员（Observatory）不参与 org 业务管理。

## 已拍板决策（Ratified）

- **D1 = B**：Team 库 settings（含 `write_buffer_hours`）由 **org admin 可编辑**；personal 库仍仅 owner + product admin。（解决 sonnet-5 B1 的 team 库无 owner dead-end。）
- **D2 = B**：Team org 创建 UI 在 **Phase O5** 交付 — `/ui/orgs/new/` + plan gate（Free → 升级 CTA；Pro → 可建 1 个 team org），不作为 v1.1 前置必做。
- **D3 = B**：新建 org 库默认 visibility 为 **`private`**；选 `org` / `public` 须二次确认并说明可见范围（采纳 GPT-5.5 异议，否决 fable 原「默认 org」）。`visibility=public` 不在表单出现（仅平台 Community seed）。
- **D4 = B**：库 maintainer 在 `/records/` 列表可见 buffered 的**元数据**（status、author、publish_at），**详情正文仅作者可开**（他人行显示「待发布」）——对齐 design/16 buffered 404 规则。
- **D5 = B**：Org 库存储 UI 为**预览只读**（用量数字 + tier 表），**不做计费 enforcement**，留待 billing Phase B3；personal 库才显示 hard limit 进度条。
- **D6 = B**：org admin 的 maintainer 权限在 **`entitlement_service` 中代码显式**声明（org admin → 本 org 全部库 maintain），非仅 UI 隐藏。
- **M1（v1.1 必做）**：添加成员支持 **display name 前缀/子串搜索** + 精确添加；`user:…` 前缀可搜 principal（覆盖 fable 原 v1.2 defer）。
- **M2（v1.1 必做）**：**唯一 admin 保护** — 服务端拒绝移除/降级最后一个 active admin（`403 last_org_admin`），UI 同步禁用按钮。
- **权限模型**：无权限直链一律 **404（非 403）**；所有 SSR POST 须 `_assert_same_origin`（CSRF）；`entitlement_service` 为 Phase O1 硬门禁，UI 路由不得先于 `org_members` migration 合并。
- **数量配额（ratified 2026-07-06）**：personal 库 Free 1 / Pro 5；team org 库 10/org；可创建 team org Free 0 / Pro 1；平台硬顶 personal org 100 库、team org 1000 库、用户 100 个 team org；超限分别 `403 plan_library_limit_exceeded` / `403 platform_library_limit_exceeded`；Community `lib_default` 永不计入。
- **Schema**：`organizations` 扩展 `kind/owner_principal_id/billing_account_id`；新增 `org_members`（role admin|member、seat_status）与 `library_grants`（reader|writer|maintainer）；首登 bootstrap 隐式 personal org 并回填 `libraries.org_id`。

## 明确不做 / 否决项

- v1.1 不做：Stripe 自助结账、跨 org 联邦 / 库迁移 wizard、record 级细粒度 RBAC、SPA 重写、MCP `ma3_create_org`、邀请链接（v1.2）、maintainer 代发 buffered record。
- 否决：maintainer 删除他人 record（否，ADR-013）；产品 admin 代管任意 org（否，Observatory 仅观测）；org 库创建默认 `org` visibility（改 private）；org 存储显示假 pooled 限额（billing 未落地时显示预览/「联系管理员」）。
- 不做 chart 库：存储可视化用纯 CSS `.storage-meter` 进度条（≥80% warn、≥100% full）。

## 落地位置

- 代码：`app/storage/db.py`（schema + helpers）、`app/services/org_service.py`（成员搜索、唯一 admin 保护）、`app/services/entitlement_service.py`（D6）、`app/services/library_admin_service.py`、`app/services/library_quota_service.py`（数量配额）、`app/api/routes_portal.py`（`/ui/orgs/*`、`/ui/libraries/{id}/{grants,records,storage}/`）、`app/api/ui_theme.py`（`.org-card`、`.storage-meter`）、i18n `portal.orgs.*` 等。
- 测试：`tests/unit/test_org_service.py`、`tests/integration/test_org_library_portal.py`（验收 O1–O10）。
- 相关文档：ADR-011、ADR-013、ADR-015、design/08（KB access & org isolation）、design/09（billing & quotas）、design/15、design/16（write buffer）、design/22。

## 历史稿说明

以下原稿已压缩归档删除：

- `24-org-library-management-decisions-for-owner.md`（产品 ratify 决策表，本摘要主要来源）
- `24-org-library-management-fable.md`（产品/工程设计定稿）
- `24-org-library-management-review-gpt55.md`（GPT-5.5 review，ACCEPT-WITH-NITS）
- `24-org-library-management-review-sonnet5.md`（sonnet-5 review，REQUEST-CHANGES → 决策覆盖）
- `24-org-library-management-visual-fable.md`（视觉设计稿）
