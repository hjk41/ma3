# 19 — 记录 / 投票列表增强（fable）

> **状态**：**已并入 design/22**（§3.4–3.5）— 保留作需求溯源  
> **真源**：[22-user-portal-ui-unified-layout-fable.md](22-user-portal-ui-unified-layout-fable.md)

> **状态**：需求已定（2026-07-05）  
> **实现**：**未开始** — 见 [21-user-portal-enhancements-backlog.md](21-user-portal-enhancements-backlog.md)  
> **关联**：[15-user-portal-fable.md](15-user-portal-fable.md) §3.2–3.3、[16-library-write-buffer-fable.md](16-library-write-buffer-fable.md)、[18](18-user-portal-overview-stat-links.md)、[20](20-user-portal-nav-peer-sections.md)

---

## 0. 一句话结论

**`/ui/me/writes/`（记录）** 与 **`/ui/me/votes/`（投票）** 应支持 **列排序**、**过滤**、**可选每页条数的分页**；记录页 additionally 支持 **批量发布/删除**（buffered）及 **个人库显示名同步**。

**现网**：两页均为固定 `_PAGE_SIZE=50`、`ORDER BY` 写死、无 filter pill、无批量操作。

---

## 1. `/ui/me/writes/` — 记录列表

### 1.1 列排序

| 列 | query `sort` | 默认 |
|----|--------------|------|
| 时间 | `created_at` | desc |
| 记录 | `problem` | asc |
| 状态 | `status` | asc |
| 库 | `library` | asc |
| 类型 | `kind` | asc |
| Key | `key` | asc |

- Query：`sort=<column>&dir=asc|desc`
- 表头点击切换；当前列显示 ↑/↓

### 1.2 状态过滤

| Pill | query `status` | 语义 |
|------|----------------|------|
| 全部 | `all` / 省略 | 所有写审计行 |
| 已发布 | `active` | active 且未删 |
| 待发布 | `buffered` | buffered |
| 已删除 | `deleted` | 无 record 或已删 |

- design/18 stat「待发布」→ `?status=buffered`
- 过滤态 subtitle /「查看全部贡献」链

### 1.3 批量操作

- 复选框：仅 **buffered + owner** 行
- 表头全选当前页 buffered
- POST `/ui/me/writes/batch`：`action=publish|delete`，`record_ids[]`
- 删除需 `confirm()`；CSRF 同 origin

### 1.4 分页与每页条数

| Query | 默认 | 可选 |
|-------|------|------|
| `page` | 1 | ≥1 |
| `per_page` | 50 | **10 · 25 · 50 · 100** |

- 底栏：**共 N 条** + 每页 pill + 上一页/下一页
- 切换 `per_page` → 回第 1 页，保留 sort/filter

### 1.5 个人库显示名

- 规范：`{display_name} 的个人库`
- `ensure_personal_library`：库已存在但 name 不一致时 **自动同步**
- 修复现网「`6a45abec… 的个人库`」应显示为「`hjk41 的个人库`」类问题

---

## 2. `/ui/me/votes/` — 投票列表（同理）

与记录列表 **同 UX 模式**：

| 能力 | 说明 |
|------|------|
| 列排序 | `updated_at`（默认 desc）、`vote`、`problem`、`library` |
| 过滤 | 全部 / 👍 赞同 (`vote=up`) / 👎 反对 (`vote=down`) |
| 分页 | 同 §1.4 `page` + `per_page` |
| 批量 | **无**（改票仅在 record 详情） |

---

## 3. 实现映射（计划）

| 文件 | 变更 |
|------|------|
| `db.py` | `list/count_write_audit_*` + sort/filter；`list/count_feedback_*` + sort/vote filter |
| `onboarding_service.py` | 个人库名同步 |
| `routes_portal.py` | writes/votes GET 增强；POST `/ui/me/writes/batch` |
| `ui_theme.py` | `render_sort_link`、`render_list_footer`、filter pills CSS |

---

## 4. 验收

见 acceptance **P14–P18**。

- [ ] writes：sort / status filter / batch / per_page
- [ ] votes：sort / vote filter / per_page
- [ ] 个人库名 `{display_name} 的个人库`
