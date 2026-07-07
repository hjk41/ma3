# 24 — 组织与库管理：产品决策（ratified）

> **状态**：定稿（2026-07-06，产品负责人拍板）  
> **设计真源**：[24-org-library-management-fable.md](24-org-library-management-fable.md)  
> **Review**：[24-org-library-management-review-gpt55.md](24-org-library-management-review-gpt55.md)、[24-org-library-management-review-sonnet5.md](24-org-library-management-review-sonnet5.md)

---

## Ratified 决策

| # | 议题 | 决定 |
|---|------|------|
| **D1** | Team 库 settings 谁可编辑 | **B — org admin 可编辑** team org 下任意库 settings（含 `write_buffer_hours`）；personal 库仍仅 owner + product admin |
| **D2** | Team org 创建 UI | **Phase O5 已做** — `/ui/orgs/new/` + plan gate（Free→升级 CTA，Pro→1 个 team org） |
| **D3** | 新建 org 库默认 visibility | **B — 默认 `private`**；选 `org` / `public` 须 **二次确认**（文案说明可见范围） |
| **D4** | Maintainer 在 records 列表见 buffered | **B — 列表可见元数据**（status、author、publish_at）；**详情正文仅作者**（他人行显示「待发布」） |
| **D5** | Org 库存储 UI | **B — 预览只读**（用量数字 + tier 表）；**不计费 enforcement** 留待 billing Phase B3 |
| **D6** | Org admin maintainer  entitlement | **B — 代码显式**：`entitlement_service` 中 org admin → 本 org 全部库的 **maintain**（非仅 UI 隐藏） |
| **M1** | 添加成员：display name 搜索 | **v1.1 必做**（覆盖 fable 原 v1.2 defer）；支持前缀/子串搜索 + 精确 display name 添加；`user:…` 前缀可搜 principal |
| **M2** | 移除唯一 admin 保护 | **v1.1 必做** — 服务端拒绝移除/降级 **最后一个 active admin**；UI 同步禁用按钮 |

---

## 对 review / fable 开放问题的覆盖

| 原条目 | 产品决定 |
|--------|----------|
| Q1 team 创建 v1.1 必做？ | **否**（D2=B，Phase O5） |
| Q2 display name 搜索 | **v1.1 必做**（M1） |
| Q3 org 库默认 visibility | **`private` + 确认**（D3=B） |
| Sonnet B1 team settings dead-end | **org admin 可编辑**（D1） |
| Sonnet 唯一 admin half 提及 | **服务端 + UI 必做**（M2） |

---

## 实现约束（engineering）

1. **Schema**：`organizations` 扩展字段 + `org_members` 表（见 fable §7.1）；`library_grants` 随 Phase O3。
2. **成员搜索**：`db.search_users_by_display_name()` + `org_service.search_members_by_display_name()`；添加成员 `resolve_member_principal_id(principal_id \| display_name)`。
3. **唯一 admin**：`org_service.remove_org_member` / `update_org_member_role` 在 `count_active_org_admins <= 1` 且 target 为 admin 时 → `403 last_org_admin`。
4. **默认 visibility**：`org_service.DEFAULT_TEAM_LIBRARY_VISIBILITY = "private"`；创建库表单默认选中 private，非 private 须 confirm checkbox。
5. **Entitlement**：Phase O2 引入 `entitlement_service` 时落实 D6；org admin 自动 maintain 本 org 全部库。
6. **Team 创建**：seed org 脚本/测试 fixture；不在 v1.1 暴露自助创建。

---

## 下一步

- [x] 本决策文档  
- [x] `org_members` schema + 成员搜索 + 唯一 admin 保护（`org_service.py`）  
- [x] Phase O1–O4 门户路由与 grants UI  
- [x] `entitlement_service`（D6）  
- [x] 创建 org 库表单 + D3 确认 UX  
- [x] 集成验收 `tests/integration/test_org_library_portal.py` O1–O10  
