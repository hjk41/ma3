# v1 验收 — 用户门户 UI（SSR）

- **版本**：2026-07-06（在 design/22 + write-buffer + keys 定稿基础上修订）
- **设计真源**：[information-architecture.md](../../04-frontend/information-architecture.md)、[portal-permissions.md](../../04-frontend/portal-permissions.md)、[visual-design-system.md](../../04-frontend/visual-design-system.md)
- **自动化**：`tests/integration/test_user_portal*.py`、`test_portal_html_regression.py`
- **目标**：**凡可 SSR 断言的行为均须有 pytest**；禁止仅依赖「曾验收 PASS」或人工点一次

## 验收结论模板

```text
Verdict: PASS | PASS-WITH-NITS | FAIL
Date:
Commit:
pytest: N passed, 0 failed
202 smoke: healthz OK / skipped
Browser E2E: run / skipped (AUTHING_TEST_*)
Open nits:
```

---

## 0. 全局 SSR 不变式（**R 系列 — 发版硬门禁**）

这些条目专门防止「页面能打开但 HTML 渲染错误」类缺陷（2026-07-06 真实回归）。

| ID | 条件 | 期望 | 自动化 |
|----|------|------|--------|
| **R1** | 任意带 `render_sort_link` 的列表页 GET | 响应 `text/html`；表头排序为 **可点击 `<a href>`**；**不得**出现转义后的 `&lt;a href=` | `test_portal_html_regression::test_*_sort_headers_are_links` |
| **R2** | `render_table` 表头含 HTML 片段 | 表头单元格 **不** 对已有 HTML 二次 `esc()` | 同上 + 代码审查 `ui_theme._render_table_cell` |
| **R3** | 任意门户 **SSR 表单 POST**（batch、delete、edit）校验失败 | **303/302 回 HTML 页** 或页内 JS 拦截；**不得** 向浏览器返回裸 JSON `{"detail":...}` | `test_writes_batch_empty_selection_redirects_with_message` |
| **R4** | 登录用户 GET 门户页 | 不得 500；Authing 未配置时 `/ui/me/` 等 → **503 HTML**（非 JSON） | `test_me_requires_login_when_authing_enabled` 等 |
| **R5** | 页面内 badge / link / button | 不得出现未闭合或整段当作文本输出的 HTML 标签字符串 | 人工 spot-check + R1 |

---

## 1. 路由与导航（N 系列）

| ID | 条件 | 期望 | 自动化 |
|----|------|------|--------|
| N1 | GET `/`、`/ui/` | 302 → `/ui/me/` | `test_root_redirects_to_me` |
| N2 | 未登录 GET `/ui/me/`（Authing on） | 302 → `/auth/login?next=...` | `test_me_requires_login_when_authing_enabled` |
| N3 | 顶栏 | 普通用户：**我的主页 \| 库 \| 记录 \| 投票 \| API Keys**；admin 末尾 **Observatory**（弱化） | `test_user_portal_nav.py` |
| N4 | 顶栏 active | `/ui/me/writes/?status=buffered` → **记录** active | `test_user_portal_nav.py` |
| N5 | subnav | **仅** `/ui/me/*` 有 **概览 \| 设置**；writes/votes/libraries/keys **无** subnav | `test_writes_page_has_filter_sort_and_footer`、`test_votes_page_has_filter_and_footer` |
| N6 | GET `/auth/login` 默认 next | `/ui/me/` | `test_auth_login_default_next_is_me` |
| N7 | 非 admin GET `/ui/observatory/` | **403 HTML**（非 302 进后台） | `test_observatory_non_admin_returns_403` |

---

## 2. 概览 `/ui/me/`（M 系列）

| ID | 条件 | 期望 | 自动化 |
|----|------|------|--------|
| M1 | 已登录 GET | 200；含 `.profile-header`、5 张 `stat-card-link` | `test_me_overview_is_dashboard_without_account_chrome` |
| M2 | 概览页 | **无** Principal ID、**无**「编辑显示名」、**无** `ma3CopyFrom` | 同上 |
| M3 | Stat 链接 | 记录→`/ui/me/writes/`；待发布→`?status=buffered`；库→`/ui/libraries/`；投票→`/ui/me/votes/`；Keys→`/ui/keys/` | `test_stat_card_links_to_buffered_filter` |
| M4 | 计数为 0 | Stat 卡片 **仍可点击**（href 存在） | 代码审查 `render_stat_cards` |
| M5 | 「最近贡献」 | list-group；链到 `/ui/records/{id}/` 或已删除占位 | 人工 / 后续补测 |

---

## 3. 账户 `/ui/me/settings/`（S 系列）

| ID | 条件 | 期望 | 自动化 |
|----|------|------|--------|
| S1 | GET settings | 显示名 **只读**；无 `name="display_name"` 输入 | `test_me_settings_shows_readonly_display_name_and_principal_id` |
| S2 | Principal ID | `.id-block` 只读展示；**无**复制按钮 | 同上 |
| S3 | subnav | **设置** active | 人工 / nav 测试扩展 |

---

## 4. 记录列表 `/ui/me/writes/`（W 系列 — **重点**）

设计：[IA §3.4](../../04-frontend/information-architecture.md)

### 4.1 列表壳

| ID | 条件 | 期望 | 自动化 |
|----|------|------|--------|
| W1 | GET 默认 | 200；含 `filter-pills`、`table.data`、`list-footer`；h1「记录」 | `test_writes_page_has_filter_sort_and_footer` |
| W2 | Filter pills | 全部 / 已发布 / 待发布 / 已删除；active 态与 query 一致 | 同上 + `test_writes_status_filter_buffered` |
| W3 | `per_page` | 10 / 25 / 50 / 100；默认 50 | list-footer 链接存在 |
| W4 | 分页 | `page` 保留 sort/filter/status | 代码审查 `_writes_list_query` |

### 4.2 排序表头（**R1 子项**）

| ID | 条件 | 期望 | 自动化 |
|----|------|------|--------|
| W5 | GET 任意 writes 列表 | 列 **时间、状态、库、类型** 表头为 `<a href="...sort=...">` | `test_writes_sort_headers_are_links` |
| W6 | 点击排序（或 GET `sort=library_name&dir=asc`） | 200；箭头 ↑/↓ 出现在当前 sort 列 | 人工 / GET 断言 |
| W7 | 非法 `sort=` | 回退 `created_at` | 单元 / 后续 |

### 4.3 行内容与状态

| ID | 条件 | 期望 | 自动化 |
|----|------|------|--------|
| W8 | active 记录 | 「记录」列为 **链接** → `/ui/records/{id}/`；problem 摘要可见 | batch 测试间接 |
| W9 | buffered + owner | 状态 badge「待发布」；行首 **有** checkbox | `test_writes_status_filter_buffered` |
| W10 | 非 owner / 非 buffered | **无** checkbox | 代码审查 |
| W11 | **已删除**（`status=deleted` 或 tombstone） | 「记录」列文案：**记录内容已完全删除，不可显示**（`.card-muted`）；**不得**显示 problem 原文；**不得**仅用 badge 充当记录内容 | `test_writes_deleted_filter_shows_redacted_label` |
| W12 | 已删除 | 状态列仍可显示「已删除」badge | 同上 |

### 4.4 批量操作（**R3 子项**）

| ID | 条件 | 期望 | 自动化 |
|----|------|------|--------|
| W13 | 表头 | 本页有可批量操作的行时，显示 **全选本页** checkbox（`#writes-select-all`） | `test_writes_page_has_select_all_and_batch_script` |
| W14 | 全选 | 勾选表头 → 本页所有 `record_ids` checkbox 同步 | JS + 人工 L4 |
| W15 | **未选任何行** 点「批量发布/删除」 | 表单 **不提交** 或 POST 后 **303 回列表** + 页内 warning「请先选择至少一条记录」；**禁止** JSON 400 | `test_writes_batch_empty_selection_redirects_with_message` |
| W16 | 选中 buffered 行 → 批量发布 | 303；record → `active` | `test_writes_batch_publish` |
| W17 | 批量 POST | same-origin；保留 `status/sort/dir/page/per_page` query | 代码审查 hidden fields |
| W18 | 批量删除 | 仅 owner + buffered；行为与单条删除一致 | 后续补测 |

### 4.5 Write buffer 交叉

| ID | 条件 | 期望 | 自动化 |
|----|------|------|--------|
| W19 | 库 buffer>0 新写入 | 列表「待发布」filter 可见；概览「待发布」计数 +1 | write-buffer 验收 + portal |
| W20 | publish 后 | 从 buffered filter 消失；出现在「已发布」 | 间接 |

---

## 5. 投票列表 `/ui/me/votes/`（V 系列）

| ID | 条件 | 期望 | 自动化 |
|----|------|------|--------|
| V1 | GET | filter-pills（全部/赞同/反对）、list-footer；**无** checkbox、**无** batch-bar | `test_votes_page_has_filter_and_footer` |
| V2 | 投票后 | 列表含 record problem 链接 | `test_votes_after_feedback` |
| V3 | 排序表头 | **R1**：时间/投票/库 为可点击链接 | `test_votes_sort_headers_are_links` |
| V4 | 无 subnav | 同 W 系列 | 同上 |

---

## 6. 库 `/ui/libraries/`（L 系列）

| ID | 条件 | 期望 | 自动化 |
|----|------|------|--------|
| L1 | 登录 GET 列表 | 200；表格列库名/可见性/权限/角色 | portal tests |
| L2 | GET 详情 | **Stats only** — 无 record 枚举表格 | `test_anonymous_public_library_stats` 等 |
| L3 | 匿名 GET 公共库 | 200 stats；minimal header | 同上 |
| L4 | 非 public 库 | 需登录 | `test_private_library_requires_login` |

---

## 7. 记录详情 `/ui/records/{id}/`（D 系列）

| ID | 条件 | 期望 | 自动化 |
|----|------|------|--------|
| D1 | active + entitlement | 200；可投票表单 | portal / feedback tests |
| D2 | buffered + owner | 显示发布/编辑/删除操作区 | write-buffer 验收 |
| D3 | buffered + 非 owner | **404**（existence oracle） | integration |
| D4 | 无 entitlement | 404 | portal tests |

---

## 8. API Keys `/ui/keys/`（K 系列 — 摘要）

完整见 [v1-api-key-lifecycle.md](v1-api-key-lifecycle.md)。

| ID | 条件 | 期望 | 自动化 |
|----|------|------|--------|
| K1 | 未登录 GET | 302 login | onboarding tests |
| K2 | 列表 | 复制 + 删除（非「撤销」） | `test_self_service_onboarding.py` |
| K3 | POST delete | 303 回列表；key 立即 401 | 同上 |

---

## 9. 与历史 P1–P19 映射

| 历史 | 新 ID |
|------|-------|
| P1 | N1, N6 |
| P2 | M1–M5 |
| P3 | W1–W4, V1–V4 |
| P4–P7 | L*, D* |
| P8–P11 | N7, 启动校验 |
| P12 | 视觉 token（代码审查） |
| P13 | M3 |
| P14 | W5–W6, R1 |
| P15 | W13–W18, R3 |
| P16 | onboarding unit |
| P17 | W3–W4 |
| P18 | V1–V4 |
| P19 | N3–N5 |

**新增（2026-07-06）**：R1–R5、W11–W15、W13（全选）

---

## 10. 发版门禁命令

```bash
cd code/server
.venv/bin/pytest \
  tests/integration/test_user_portal.py \
  tests/integration/test_user_portal_nav.py \
  tests/integration/test_user_portal_writes.py \
  tests/integration/test_user_portal_votes.py \
  tests/integration/test_portal_html_regression.py \
  tests/integration/test_display_name_registration.py \
  -q --tb=short
```

部署到 202 后追加：

```bash
bash deploy/common/verify_ma3.sh
# 可选：AUTHING_TEST_USER/PASS 设置时跑 e2e_authing_ui.py
```

---

## 11. Owner 目视清单（L4 — 每发版抽测 5 分钟）

- [ ] `/ui/me/writes/?status=buffered`：表头「时间 ↓」**可点击**，不是纯文本
- [ ] 不勾选 → 批量发布：页内黄色提示，**不是** JSON 页
- [ ] 表头全选：勾选/取消勾选本页 buffered 行
- [ ] `/ui/me/writes/?status=deleted`：记录列显示「记录内容已完全删除，不可显示」
- [ ] 顶栏五项同级；记录/投票页 **无** 账户 subnav
- [ ] `/ui/me/settings/`：Principal ID 只读、无复制

---

## 12. 已知非阻塞 nits

1. Batch 操作条在零行时仍显示 — 可接受 v1。
2. 「记录」列不支持 DB 排序 — design/19  defer。
3. TestClient 不走真实 Authing 浏览器流 — 靠 `e2e_authing_ui.py` 补。
