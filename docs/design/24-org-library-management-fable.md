# 24 — 组织与知识库管理（Org & Library Management）设计（fable）

> **状态**：定稿（2026-07-06，[产品决策已 ratify](24-org-library-management-decisions-for-owner.md)）  
> **视觉真源**：[24-org-library-management-visual-fable.md](24-org-library-management-visual-fable.md)  
> **评审**：[24-org-library-management-review-gpt55.md](24-org-library-management-review-gpt55.md)、[24-org-library-management-review-sonnet5.md](24-org-library-management-review-sonnet5.md)  
> **前置**：[15-user-portal-fable.md](15-user-portal-fable.md) §3.7–3.9、[08-kb-access-and-org-isolation.md](../clean/08-kb-access-and-org-isolation.md)、[09-billing-and-quotas.md](../clean/09-billing-and-quotas.md)、[16-library-write-buffer-fable.md](16-library-write-buffer-fable.md)、[22-user-portal-ui-unified-layout-fable.md](22-user-portal-ui-unified-layout-fable.md)  
> **技术约束**：SSR HTML（`ui_theme.py` / `routes_portal.py`），无 SPA；复用 GitHub 浅色 token

---

## 0. 一句话结论

在 v1 个人门户（`/ui/me/`、`/ui/libraries/`、库设置 buffer）之上，**v1.1 补齐「组织 → 库 → 授权 → 容量」的人类管理闭环**：顶栏新增 **组织**；org admin 可管成员与 org 库；库 owner / org admin / maintainer 可管 **库设置、库内枚举、外部 grant、存储用量**；personal org 与 team org 共用同一套 UI，由 `organizations.kind` 与 billing plan 区分能力边界。**产品管理员（Observatory）仍不参与 org 业务管理**——全局观测与租户自助分离。

---

## 1. 问题与目标

### 1.1 现状（v1 已交付）

| 能力 | 状态 |
|------|------|
| 个人库自动创建、`/ui/libraries/` Stats 列表 | ✅ |
| 库详情 Stats-only、匿名 public Stats | ✅ |
| 个人库 **库设置**（`write_buffer_hours`） | ✅ owner / product admin |
| API Key grant 管理（personal + Community） | ✅ `/ui/keys/` |
| 个人库存储配额（100KB/条、10MB 免费档） | ✅ MCP + 写入 enforcement |
| `organizations` 表（仅 `id, name`） | ✅ seed `org_default` |
| `org_members`、`library_grants` 表与 UI | ✅ schema + 门户 UI（O1–O4）；team 创建 UI 仍 Phase O5 |
| org 库创建、visibility 管理、成员邀请 | ✅ |
| 库内 record 枚举 UI（非 Observatory） | ✅ maintainer `/records/` |
| 存储用量可视化（门户） | ✅ personal quota + org 预览 |

结果：团队/公司场景无法自助建 org、加人、开 org 库；库管理员无法在 UI 上管理外部 reader/writer；用户看不到个人库容量进度，付费升级无入口。

### 1.2 目标

| 目标 | 说明 |
|------|------|
| **组织可发现** | 登录用户看见「我属于哪些 org / 我拥有的 personal org」 |
| **成员可管理** | org admin 添加/移除成员、分配 admin/member（v1.1 手动 principal ID；v1.2 邀请链接） |
| **库可创建与分级** | org admin 在 org 下创建 library；visibility `org` / `private`（public 仅平台 seed） |
| **授权可审计** | 库管理员维护 `library_grants`；与 API key grants 分层展示 |
| **容量可感知** | personal / org 库存储进度条 + tier；写满时 UI 与 MCP 一致 403 |
| **动线不绕** | 从 `/ui/me/` → 组织 / 库 → 设置 / 成员，最多 3 次点击到常用操作 |
| **权限缺席优于禁用** | 无权限者不渲染入口；直链 URL → 404 |

### 1.3 非目标（本设计不含）

- Stripe 自助结账（billing UI 只展示 plan + 联系升级 CTA）
- 跨 org 联邦、库迁移 wizard
- 细粒度 RBAC（record 级 ACL）
- SPA / React 重写
- MCP `ma3_create_org`（v1.2 再议；v1.1 人类门户优先）

---

## 2. 概念模型（与 ADR-011 / design/09 对齐）

```text
Principal
    │
    ├── org_personal_{sub}     kind=personal, 1 seat, billing=free|pro
    │       └── lib_personal_*   kind=personal, visibility=private
    │
    └── org_members ── org_team_x   kind=team, billing=team
              └── libraries (visibility org|private)
                        └── library_grants → 外部 principal
```

| 实体 | v1.1 扩展字段 |
|------|----------------|
| `organizations` | `kind (personal\|team)`, `owner_principal_id`, `billing_account_id`（可空，过渡） |
| `org_members` | `role (admin\|member)`, `seat_status`, `joined_at` |
| `libraries` | 已有 `kind`, `visibility`, `owner_principal_id`；可选 `storage_bytes` 缓存列 |
| `library_grants` | `library_id`, `principal_id`, `role (reader\|writer\|maintainer)` |

**Implicit personal org**：Authing 首登 bootstrap 时创建 `org_personal_{sub}` + `org_members(admin)` + 已有 personal library 挂到该 org（`libraries.org_id` 回填）。

---

## 3. 信息架构与路由

### 3.1 顶栏变更（design/22 扩展）

```text
我的主页 | 库 | 组织 ★ | 记录 | 投票 | API Keys | Observatory*
```

| key | 标签 | href | active 条件 |
|-----|------|------|-------------|
| orgs | 组织 | `/ui/orgs/` | `/ui/orgs/*` |

v1.1 **不**把 org 塞进 subnav；与「库」并列，避免 `/ui/me/*` 账户区过载。

### 3.2 路由树

```text
/ui/orgs/                              我所属的组织（含 personal org 卡片）
/ui/orgs/new/                          创建 team org（org admin 候选；billing gate）
/ui/orgs/{org_id}/                     组织概览：成员数、库列表、plan、存储汇总
/ui/orgs/{org_id}/members/             成员管理（org admin）
/ui/orgs/{org_id}/settings/            组织设置：名称、plan 展示（org admin）

/ui/libraries/                         增强：按 org 分组 + 权限列
/ui/libraries/{lib_id}/                库详情：Stats + 我的访问 + 存储条（personal）
/ui/libraries/{lib_id}/settings/       已有 buffer；扩展 deletion/retention 只读展示
/ui/libraries/{lib_id}/storage/        存储详情与 tier（personal owner / org admin）
/ui/libraries/{lib_id}/records/        库内 record 枚举（库 maintainer+）
/ui/libraries/{lib_id}/grants/         外部 library_grants（库 maintainer+）

/ui/me/                                概览卡「组织」链接 → /ui/orgs/（替换 v1 占位删除）
```

### 3.3 Breadcrumb 模式

```text
组织 / Acme Team / 成员
库 / Acme 工程库 / 授权
```

复用 `render_breadcrumb()`；二级以下必显。

---

## 4. 用户动线（Journeys）

### J1 — 首次登录：看见 personal org（无额外操作）

```text
Authing 登录
  → bootstrap: org_personal + personal library（已有）
  → /ui/me/ 概览
  → 「组织」stat 卡 = 1
  → /ui/orgs/ 见「我的个人组织」卡片 + personal library 链接
```

**原则**：personal org 不强迫用户理解 billing；默认折叠为「个人账户」文案。

### J2 — 创建 Team 组织（付费 / 白名单 gate）

```text
/ui/orgs/ → [创建团队组织]
  → /ui/orgs/new/ 表单：组织名称
  → POST 创建 org(kind=team) + billing_account(plan=team 或 trial)
  → 创建者 org_members(admin)
  → 302 /ui/orgs/{id}/
  → 空状态 CTA：[创建第一个库] [邀请成员]
```

**Gate**：free personal org 用户点击创建 team → 展示 upgrade CTA（不 silent 403）。

### J3 — org admin 添加成员

```text
/ui/orgs/{id}/members/
  → 说明：「对方需至少登录过一次 ma3」
  → 输入 display name 搜索（前缀/子串）或 principal ID（`user:…`）；从结果选择用户
  → 选 role: member | admin
  → POST 添加 → 表格刷新
  → 成员侧 /ui/orgs/ 自动出现该 org
```

**移除**：admin 二次确认；member 行 [移除] → confirm dialog。**唯一 admin 不可移除/降级**（服务端 `403 last_org_admin` + UI 禁用）。

**Seat 上限**：超 `included_seats` → 400 + 页面顶 alert「需升级 Team plan」。

### J4 — org admin 创建 org 库

```text
/ui/orgs/{id}/ → [创建库]
  → 表单：库名、visibility（默认 **private**；选 org 须二次确认）、write_buffer_hours 默认 24
  → POST → libraries 行 + org_id
  → 302 /ui/libraries/{lib_id}/
```

**约束**：`visibility=public` 不在表单出现（仅平台 Community）。

### J5 — 库管理员管理外部授权

```text
/ui/libraries/{lib_id}/grants/
  → 列表：principal | 显示名 | 角色 | 添加时间 | [移除]
  → [添加授权] principal ID + role (reader|writer|maintainer)
  → 校验：target principal 存在；grant ⊆ org 策略
  → 说明：「API Key grant 需在 /ui/keys/ 单独配置；此处为 entitlement 层」
```

### J6 — 库 maintainer 枚举 record

```text
/ui/libraries/{lib_id}/records/
  → 标准列表壳：filter status / outcome → table → pagination
  → 列：时间 | problem 摘要 | status | outcome | [详情]
  → 行链 /ui/records/{id}/
```

**与 Observatory 区别**：仅单库；无 cross-library 枚举。

### J7 — personal 库容量触顶

```text
Agent ma3_report → 403 storage quota
  → 用户打开 /ui/libraries/{personal}/storage/
  → 进度条 10MB/10MB + tier=free
  → CTA：「升级至 100MB / 10GB / 1TB」→ /ui/orgs/{personal_org}/settings/ 或 mailto admin
  → 删除旧 record 后进度下降（hard delete 释放计数）
```

### J8 — org admin 查看 org 存储池

```text
/ui/orgs/{team_id}/
  → Stat：已用 / 限额（Team pooled）
  → 各库分行条形图（简表即可，v1.1 不做 chart.js）
  → 链接各库 /storage/
```

---

## 5. 角色与可见性矩阵

| 页面 / 操作 | 普通 member | org admin | 库 owner (personal) | 库 maintainer | 产品 admin |
|-------------|-------------|-----------|---------------------|---------------|------------|
| `/ui/orgs/` 列表 | ✅ 所属 org | ✅ | ✅ | ✅ | ✅ |
| 创建 team org | ❌* | ✅ | ❌* | ❌ | ✅ |
| `/ui/orgs/{id}/members/` | ❌ 404 | ✅ | — | — | ❌ 404** |
| `/ui/orgs/{id}/settings/` | ❌ | ✅ | personal: ✅ | — | ❌ |
| 创建 org library | ❌ | ✅ | — | — | ❌ |
| `/ui/libraries/{id}/records/` | ❌ | ✅*** | ✅*** | ✅ | ❌ |
| `/ui/libraries/{id}/grants/` | ❌ | ✅*** | ✅*** | ✅ | ❌ |
| `/ui/libraries/{id}/storage/` | 只读**** | ✅ | ✅ | 只读 | ❌ |
| 改 write_buffer | ❌ | — | ✅ owner | — | ✅ |

\* 除非 billing 允许（paid / trial）  
\** 产品 admin 不走 org 业务 UI，用 Observatory + SQL  
\*** 对该库有 maintain entitlement  
\**** member 可见用量进度，不可改 tier

---

## 6. 前端设计（页面规格）

> 线框与 class 见 [24-org-library-management-visual-fable.md](24-org-library-management-visual-fable.md)

### 6.1 `/ui/orgs/` — 组织列表

- **布局**：`.page-narrow` + 1–N 张 `.card`
- **Personal org 卡**：始终置顶；标题「个人账户」；副文案 personal library 名；链接库详情 + 设置
- **Team org 卡**：org 名、角色 badge（管理员/成员）、库数量、成员数；[进入]
- **空 team**：仅 personal 卡 + 虚线 CTA 创建团队
- **Actions**：右上角 `[创建团队组织]`（gate 后可见）

### 6.2 `/ui/orgs/{org_id}/` — 组织概览

- **Stat 行**：成员 | 库 | 存储已用/限额 | Plan
- **库列表**（简表）：库名、visibility、records(active)、[进入]
- **Admin actions**：`[成员]` `[设置]` `[创建库]`
- **Member 视图**：隐藏 admin actions；库列表只读

### 6.3 `/ui/orgs/{org_id}/members/`

- **标准 table**：显示名 | Principal ID | 角色 | 加入时间 | 操作
- **Add form**（card 顶）：principal_id + role + [添加]
- **Remove**：行内 POST + `confirm()`

### 6.4 `/ui/libraries/{lib_id}/` — 库详情增强

在 v1 Stats 下方追加：

1. **存储区**（personal / org 库）：`.storage-meter` 进度条 + tier 文案
2. **管理入口区**（maintainer+）：按钮组 → 记录 / 授权 / 存储 / 设置

### 6.5 `/ui/libraries/{lib_id}/grants/`

- 与 `/ui/keys/` grant 表格视觉一致（design/14）
- 顶部 `.alert-info` 解释 Layer 1 vs Key grant

### 6.6 `/ui/libraries/{lib_id}/records/`

- 复用 `/ui/me/writes/` 列表壳（filter pills + sort + pagination）
- 数据源：`list_records_for_library(lib_id, filters)`

### 6.7 `/ui/libraries/{lib_id}/storage/`

- 大进度条 + 数字明细：records 数、估算 bytes、单条上限 100KB
- Tier 表（当前 vs 可升级档）
- personal：`MA3_PRINCIPAL_STORAGE_TIERS` / paid 状态只读展示

---

## 7. 后端设计

### 7.1 Schema migration（v1.1）

```sql
-- organizations 扩展
ALTER TABLE organizations ADD COLUMN kind TEXT NOT NULL DEFAULT 'custom';
ALTER TABLE organizations ADD COLUMN owner_principal_id TEXT;
ALTER TABLE organizations ADD COLUMN billing_account_id TEXT;

CREATE TABLE IF NOT EXISTS org_members (
  org_id TEXT NOT NULL,
  principal_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin', 'member')),
  seat_status TEXT NOT NULL DEFAULT 'active'
    CHECK (seat_status IN ('active', 'pending', 'removed')),
  joined_at TEXT NOT NULL,
  PRIMARY KEY (org_id, principal_id)
);

CREATE TABLE IF NOT EXISTS library_grants (
  library_id TEXT NOT NULL,
  principal_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('reader', 'writer', 'maintainer')),
  created_at TEXT NOT NULL,
  created_by TEXT,
  PRIMARY KEY (library_id, principal_id)
);
```

Bootstrap 脚本：`ensure_personal_org(principal_id)` 在 `ensure_personal_library` 之后调用。

### 7.2 服务层

| 模块 | 职责 |
|------|------|
| `org_service.py` | create/list orgs；members CRUD；seat check |
| `library_admin_service.py` | create org library；grants CRUD；assert_maintainer |
| `entitlement_service.py` | **替换** v1 启发式 `list_entitled_libraries`：public + personal + org_members + library_grants |
| `storage_quota_service.py` | 已有；门户读 `personal_library_quota_summary()` |

### 7.3 DB helpers（新增）

```python
def list_orgs_for_principal(principal_id: str) -> list[dict]: ...
def get_org(org_id: str) -> dict | None: ...
def create_team_org(*, name: str, owner_principal_id: str) -> dict: ...
def add_org_member(*, org_id, principal_id, role, added_by) -> None: ...
def remove_org_member(*, org_id, principal_id, removed_by) -> None: ...
def list_org_libraries(org_id: str) -> list[dict]: ...
def create_org_library(*, org_id, name, visibility, created_by) -> dict: ...
def list_library_grants(library_id: str) -> list[dict]: ...
def upsert_library_grant(...) -> None: ...
def delete_library_grant(...) -> None: ...
def list_records_for_library(library_id, *, status, limit, offset) -> tuple[list, int]: ...
def sum_org_storage_bytes(org_id: str) -> int: ...
```

### 7.4 HTTP 路由（`routes_portal.py`）

| Method | Path | Handler | Auth |
|--------|------|---------|------|
| GET | `/ui/orgs/` | `portal_orgs_list` | session |
| GET/POST | `/ui/orgs/new/` | 创建 team | session + billing |
| GET | `/ui/orgs/{org_id}/` | 概览 | org member |
| GET/POST | `/ui/orgs/{org_id}/members/` | 成员 | org admin |
| GET | `/ui/orgs/{org_id}/settings/` | 设置 | org admin |
| GET/POST | `/ui/libraries/{id}/grants/` | grants | lib maintainer |
| GET | `/ui/libraries/{id}/records/` | 枚举 | lib maintainer |
| GET | `/ui/libraries/{id}/storage/` | 容量 | lib read entitlement |

**JSON API（可选 v1.1.1）**：`GET /api/orgs`、`GET /api/libraries/{id}/storage` 供未来 SPA；v1.1 可仅 SSR。

### 7.5 权限断言（统一）

```python
def assert_org_member(org_id, principal_id) -> None: ...
def assert_org_admin(org_id, principal_id) -> None: ...
def assert_library_maintainer(library_id, principal_id) -> None: ...
```

失败 → **404**（非 403），除 POST 表单 validation 用 400。

### 7.6 与 MCP / 配额衔接

- `ma3_whoami.storage_quota` 已有；org 库不写 personal quota
- Team org pooled quota：`effective_quota(billing_account, max_records_total)` **与** `sum_org_storage_bytes` 双轨（v1.1 先实现 **bytes 轨**，records 轨 follow design/09）
- `ma3_report` 继续调用 `assert_personal_library_write_allowed`；org 库写满返回同样 403 形

---

## 8. i18n

新增 catalog 前缀 `portal.orgs.*`、`portal.library.grants.*`、`portal.library.storage.*`。

| key 示例 | zh-CN | en-US |
|----------|-------|-------|
| `portal.nav.orgs` | 组织 | Organizations |
| `portal.orgs.personal_card_title` | 个人账户 | Personal account |
| `portal.orgs.create_team` | 创建团队组织 | Create team organization |
| `portal.orgs.members.add_help` | 对方需至少登录过一次 ma3，方可添加。 | They must have signed in to ma3 at least once. |
| `portal.library.storage.used` | 已用 {used} / {limit} | {used} / {limit} used |
| `portal.library.grants.layer_hint` | 库级授权（entitlement）；API Key 权限在 Keys 页单独配置。 | Library-level entitlement; configure API key grants on Keys. |

---

## 9. 分阶段交付

### Phase O1 — Schema + entitlement（backend only）

- 表迁移 + bootstrap personal org
- `entitlement_service` 替换 portal 库列表
- 单元 / 集成测试；**无新 UI**

### Phase O2 — Org 列表与成员

- `/ui/orgs/`、`/ui/orgs/{id}/`、`members/`
- 顶栏「组织」
- `/ui/me/` 组织 stat 卡

### Phase O3 — Library admin

- 创建 org 库、`/grants/`、`/records/`
- 库详情管理按钮组

### Phase O4 — Storage 门户

- `/ui/libraries/{id}/storage/`
- org 概览存储汇总
- 与 `storage_quota_service` 对齐

### Phase O5 — Team 创建 + billing 展示 ✅

- `/ui/orgs/new/` + plan gate（Free → 升级 CTA；Pro → 可建 1 个 team org）
- `/ui/orgs/` 入口「创建团队组织」
- settings 页 plan 展示 + personal org 升级提示

---

## 10. 验收标准

| ID | 场景 | 预期 |
|----|------|------|
| O1 | org member 打开 `/ui/orgs/{id}/` | 200；见库列表 |
| O2 | 非 member 直链 org URL | 404 |
| O3 | org admin 添加已存在 principal（display name 或 ID） | members 表 +1 |
| O3b | org admin 移除/降级唯一 admin | 403 `last_org_admin` |
| O4 | org admin 创建 org 库 | library org_id 正确 |
| O5 | maintainer 打开 `/records/` | 仅本库 record |
| O6 | 普通 member 直链 `/grants/` | 404 |
| O7 | personal 库存储页 | 进度条与 ma3_whoami 一致 |
| O8 | 写满 personal 库 | MCP 403 + UI 顶 alert |
| O9 | i18n en-US | org 顶栏 "Organizations" |
| O10 | Observatory 不出现 org 管理入口 | admin 仍仅观测 |

---

## 11. 开放问题（已 ratify → 见 [decisions-for-owner](24-org-library-management-decisions-for-owner.md)）

| ID | 问题 | 状态 |
|----|------|------|
| Q1 | team 创建是否 v1.1 必做？ | **否**（D2=B，Phase O5） |
| Q2 | principal 添加是否做 display name 搜索？ | **v1.1 必做**（M1） |
| Q3 | org 库默认 visibility | **默认 `private` + 确认**（D3=B） |
| Q4 | maintainer 能否删他人 record？ | 否（ADR-013） |
| Q5 | 产品 admin 是否代管任意 org？ | 否 |

---

## 12. 库与组织数量配额（ratified 2026-07-06）

与 GitHub「repo 数量 plan 限制 + 平台硬顶」对齐；enforcement 见 `library_quota_service.py`。

### 12.1 Plan 配额（用户可见）

| 范围 | Free | Pro | Team |
|------|------|-----|------|
| personal 库 / personal org | **1** | **5** | — |
| org 库 / team org | — | — | **10** |
| 可创建 team org | **0** | **1** | 1/订阅 |
| 可加入 team org | 999 | 999 | 999 |

Personal org 首登 bootstrap，不占「创建 org」配额。

**v1 实现注记**：`libraries` 上 `(kind=personal, owner_principal_id)` 唯一索引仍限制 **1 个 bootstrap 个人库**；Pro **5** 库配额在 **personal org 落地**后，对 `org_id=personal_org` 下 `kind≠personal` 的附加库生效。Team org 库配额 **现已 enforcement**。

### 12.2 平台硬顶（防滥用）

| 项 | 上限 |
|----|------|
| personal org 库总数 | **100** |
| team org 库总数 | **1000** |
| 用户拥有的 team org | **100** |

硬顶触发 → `403 platform_library_limit_exceeded`；plan 上限 → `403 plan_library_limit_exceeded`。

### 12.3 校验顺序（`create_library`）

```text
1. lib_default → 豁免
2. org_id = org_default 且非 personal → 豁免（测试/平台 seed）
3. kind=personal → count(owner) vs min(plan, 100)
4. 其他 org 库 → count(org_id) vs min(plan, 1000)
```

Community（`lib_default`）永不计入。

---

## 13. 实现落点（预估文件）

| 文件 | 变更 |
|------|------|
| `app/storage/db.py` | schema + helpers |
| `app/services/library_quota_service.py` | 库数量 plan + 平台硬顶 |
| `app/services/org_service.py` | 成员搜索、添加/移除、唯一 admin 保护 |
| `app/services/library_admin_service.py` | 新建 |
| `app/services/entitlement_service.py` | 新建 |
| `app/api/routes_portal.py` | org/library 路由 |
| `app/api/ui_theme.py` | `.storage-meter`、org 卡 |
| `app/api/i18n/*.json` | 文案 |
| `app/services/onboarding_service.py` | ensure_personal_org |
| `tests/unit/test_org_service.py` | 成员搜索 + 唯一 admin |
| `tests/integration/test_org_library_portal.py` | 验收 O1–O10 |

---

*fable · 2026-07-06 · ratified*
