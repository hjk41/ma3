# 15 — 用户门户（User Portal）设计（fable）

> **状态**：定稿（2026-07-04，产品决策 ratified）  
> **Ratified 决策**：[15-user-portal-decisions-for-owner.md](15-user-portal-decisions-for-owner.md)
> **对象**：ma3 Web UI 登录后默认体验，替代当前「Observatory 即首页」的产品管理员视角  
> **参照**：[ADR-011](../adr/011-kb-access-and-org-isolation.md)、[design/08](08-kb-access-and-org-isolation.md)、[design/10](10-write-audit-and-delete.md)、[design/14-api-key-lifecycle-layout-fable.md](14-api-key-lifecycle-layout-fable.md)  
> **技术约束**：SSR HTML（`ui_theme.py` 的 `render_page` / `render_table` / `render_stat_cards`），无 SPA

---

## 0. 一句话结论

登录后默认落地页从 `/ui/observatory/` 改为 **`/ui/me/`**（个人主页）。Observatory 保留原路由但降级为**产品管理员专属**（`is_admin` 门控），从普通用户导航中消失。普通用户看到的是「我的组织、我的库权限、我写过的记录、我投过的票」——即**以 principal 为中心**的视图，而不是以平台为中心的视图。

---

## 1. 目标与角色（Goals & Personas）

### 1.1 目标

| 目标 | 说明 |
|------|------|
| **登录即有用** | 普通用户登录后第一屏回答：我能访问哪些库？我贡献了什么？下一步做什么（建 key / 接 agent） |
| **权限边界可见** | 用户不需要读 ADR 就能知道自己对每个库是 读 / 读写 / 维护 |
| **管理入口按角色浮现** | 库管理员看见「管理此库」，org 管理员看见「管理组织」；无权限者完全看不到入口（缺席优于禁用，同 design/14 §1） |
| **产品管理员视角隔离** | 全局统计与枚举仅 `is_admin`（Observatory）；普通用户直访 Observatory 得 **403** |
| **库内容分级** | 有读 entitlement → **Stats only**；枚举/修改/导出 → 库管理员或产品管理员（导出 v1.1+，可计费） |
| **分阶段可交付** | v1 只依赖已存在的表；`org_members` / `library_grants` 落地后 v1.1 补齐组织与授权管理 |

### 1.2 角色

| 角色 | 身份判定 | 核心诉求 |
|------|----------|----------|
| **普通用户（贡献者）** | Authing session，有 principal 行 | 看自己的库权限、写过的 record、投票历史；自助管 key |
| **库管理员** | `library_grants.role ∈ {maintainer, admin}`，或 `owner_principal_id == me`（v1 个人库），或 org admin 对该库 | 管库授权、审 draft |
| **组织管理员** | `org_members.role == 'admin'` | 管成员、建 org library、改 visibility |
| **产品管理员** | `SessionUser.is_admin`（`MA3_AUTH_ADMIN_USERS`） | 全局健康度（现 Observatory） |

角色**叠加**：产品管理员也是普通用户；Observatory 只是多出来的导航项。

---

## 2. 信息架构（Information Architecture）

### 2.1 路由树

```text
/ui/me/                      个人主页（默认落地页）★
/ui/me/writes/               我的贡献（写审计列表，分页）
/ui/me/votes/                我的投票（feedback 历史，分页）

/ui/libraries/               我有读 entitlement 的库（列表）
/ui/libraries/{lib_id}/      库详情 — Stats only（非 admin）；匿名仅 public 库
/ui/libraries/{lib_id}/records/  库内 record 枚举（库管理员）     [v1.1]
/ui/libraries/{lib_id}/grants 授权管理（库管理员）        [v1.1]

/ui/orgs/                    我所属的组织（列表）            [v1.1]
/ui/orgs/{org_id}/           组织详情                       [v1.1]
/ui/orgs/{org_id}/members    成员管理（org admin）           [v1.1]

/ui/records/{record_id}      单条 record 详情 + 投票（需登录 + 库读 entitlement；无枚举入口）
/ui/keys/                    API key 管理（已有，design/14）
/ui/keys/{key_id}            key 详情（已有）

/ui/observatory/             产品管理员专属，全局统计
```

### 2.2 `/ui/observatory` 的处置

1. **路由保留**，页面内容不变（全局枚举 + Stats）。
2. 门控：未登录 → 302 login；已登录但 `not user.is_admin` → **403 Forbidden**（HTML 含「返回我的主页」）。
3. **`MA3_AUTH_ADMIN_USERS` 为空且 Authing 已启用 → 进程拒绝启动**（见 ratified 决策 2）；LAN `authing_enabled=False` 不受限。
4. **record 详情迁出**：`/ui/observatory/records/{id}` → `/ui/records/{id}`；旧路径 301。
5. 品牌 logo 链接 → `/ui/me/`。

### 2.3 库内容三级能力（Stats / Enumerate / Mutate）

| 能力 | 谁可以 |
|------|--------|
| **Stats** — case/record 计数、outcome 分布等聚合数字 | 对该库有**读 entitlement**的登录用户；**匿名**仅 `lib_default`（public） |
| **Enumerate** — record/case 列表、browse、search UI | 库管理员（本库）；产品管理员（Observatory 全局） |
| **Mutate / Export** — 改状态、删、授权、批量导出 | 库管理员；产品管理员；导出 v1.1+，后续可针对库/组织收费 |

普通用户**不能**在 UI 上浏览库内 record 列表；只能看 Stats，并通过「我的贡献 / 我的投票」或已知 record ID 深链打开单条详情。

### 2.4 默认落地页

- Authing 回调无 `next` → 302 `/ui/me/`
- `/` 或 `/ui/` → 302 `/ui/me/`（未登录先 login）
- 产品管理员也落在 `/ui/me/`

---

## 3. 各页面设计

### 3.1 `/ui/me/` — 个人主页 ★

```
┌ topbar: [ma3◆] 我的主页 Libraries API Keys        用户名 · 账户 · 退出 ┐
│                                                  (admin 多一项 Observatory) │
├────────────────────────────────────────────────────────────────────────┤
│ 我的主页                                                                │
│ 你好，{display_name}。这里是你在 ma3 的贡献与权限概览。                    │
│ Principal ID  user:abc…                              [复制]  ← v1 必展示   │
│                                                                        │
│ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐                            │
│ │   12   │ │    3   │ │    8   │ │    2   │      ← render_stat_cards   │
│ │ 我的贡献│ │ 可访问库│ │ 我的投票│ │ API Keys│                            │
│ └────────┘ └────────┘ └────────┘ └────────┘                            │
│                                                                        │
│ ┌─ 我的库权限 ──────────────────────────────── [查看全部 →] ─┐           │
│ │ 库名              可见性    我的权限        角色           │           │
│ │ 个人库 lib_xxx    private   读写           所有者 [管理]   │           │
│ │ Community Library public    读写           贡献者          │           │
│ └────────────────────────────────────────────────────────────┘         │
│                                                                        │
│ ┌─ 最近贡献（5 条）───────────────────────── [查看全部 →] ─┐             │
│ │ 时间          记录                        库        类型   │           │
│ └────────────────────────────────────────────────────────────┘         │
│                                                                        │
│ ┌─ 组织 ────────────┐   ← v1.1；v1 该卡片不渲染                          │
│ └───────────────────┘                                                  │
└────────────────────────────────────────────────────────────────────────┘
```

**空状态**（新用户）：贡献 / 投票为 0 时，`.empty` + 引导「创建 API key → 查看 onboarding」。

### 3.2 `/ui/me/writes/` — 我的贡献

数据源：`list_write_audit_for_principal`（已存在）。

列：`时间 | 记录(problem 摘要) | 库 | 类型(report_kind) | Key(prefix)`。记录链到 `/ui/records/{id}`；已删 record 显示「已删除」badge。

### 3.3 `/ui/me/votes/` — 我的投票

数据源：**新** `list_feedback_for_principal`。

列表只读；改票 / 清除只在 `/ui/records/{id}` 一处。

### 3.4 `/ui/records/{record_id}` — 记录详情

- **登录** + record 所属库在 `list_entitled_libraries_for_principal` 内 → 可读 + 可投票。
- **匿名** → 403/302 login（决策 4：无 record 详情）。
- 无库级列表页；入口：我的 writes/votes、外部深链（record ID）。
- Feedback POST → `/ui/records/{id}/feedback`。

### 3.5 `/ui/libraries/` — 我的库

列：`库名 | 可见性 | 所属 | 我的权限 | Cases | Records(active) | 操作`。数字列来自 Stats；「管理」仅库管理员。

### 3.6 `/ui/libraries/{lib_id}/` — 库详情（Stats only，非 admin）

```
│ Libraries / Community Library                                          │
│ ┌─ 概况（Stats）────────────────────────────────────────────┐          │
│ │ Cases 1204   Records 8931   Active 8400   Draft 412       │          │
│ │ Invalid 119   by outcome / by task_type（小表，聚合数字）   │          │
│ └────────────────────────────────────────────────────────────┘          │
│ ┌─ 我的访问 ────────────────────────────────────────────────┐          │
│ │ 权限 读   绑定 key  ma3k_ab12                             │          │
│ └────────────────────────────────────────────────────────────┘          │
│ （无 record 列表 — 非 admin 不可枚举）                                    │
│ ┌─ 管理（仅库管理员）──────────────────────────────────────┐  [v1.1]   │
│ │ [查看库内记录] [授权管理] [导出]                            │          │
│ └────────────────────────────────────────────────────────────┘          │
```

**匿名**访问 `lib_default`：同上 Stats 卡，隐藏「我的访问」；顶部 CTA「登录以贡献与投票」。

### 3.7–3.9 Org / Grants 页面

见 v1.1；线框见评审附录。v1 **不渲染**任何 org 相关 UI（无占位页）。

### 3.10 `/ui/observatory/` — 产品管理员

全局 Stats + **全库枚举**（org/library/user 表、record 分布）。非 admin → **403**。

---

## 4. 用户旅程

### J1 — 首次登录

Authing 登录 → 建 principal + personal library → 302 `/ui/me/` → 空状态引导创建 key → agent 首次 `ma3_report` 后「最近贡献」出现第一条。

### J2 — 贡献者查自己的写入

`/ui/me/` 看最近贡献 → `/ui/me/writes/` 翻页按 key prefix 核对 → `/ui/records/{id}` 看内容。

### J3 — org 管理员添加成员（v1.1）

同事先登录产生 principal → admin 在 `/ui/orgs/{id}/members` 填 principal ID 添加。

### J4 — 库管理员管理外部授权（v1.1）

`/ui/libraries/{id}/grants` 添加 / 移除 `library_grants`。

---

## 5. 角色可见性矩阵

| 页面 / 入口 | 普通用户 | 库管理员 | org 管理员 | 产品管理员 |
|---|---|---|---|---|
| `/ui/me/*` | ✅ | ✅ | ✅ | ✅ |
| `/ui/keys/*` | ✅ | ✅ | ✅ | ✅ |
| `/ui/records/{id}` | ✅ 单条（读 entitlement） | ✅ | ✅ | ✅ |
| `/ui/libraries/{id}/` Stats | ✅ 读 entitlement | ✅ | ✅ | ✅ |
| `/ui/libraries/{id}/records/` 枚举 | ❌ | ✅ 本库 | ✅ 本 org 库 | ✅ 全局* |
| `/ui/libraries/lib_default/` 匿名 Stats | ✅ 仅 public | — | — | — |
| `/ui/observatory/` | ❌ **403** | ❌ **403** | ❌ **403** | ✅ |

\* 产品管理员（`is_admin`）**不**自动获得 org/库业务管理权；全局观测与业务管理分离。

**越权直查 URL** → 404（不泄露资源存在性）。

---

## 6. v1 vs v1.1 范围

### v1（已存在表即可）

| 项 | 依赖 |
|----|------|
| `/ui/me/` + principal_id + writes + votes | 同上 |
| `/ui/libraries/` + Stats-only 详情 + 匿名 public Stats | `get_library_stats` |
| 启动拒绝空 admin 白名单 | `config.py` / lifespan |
| Observatory 403 + `/ui/records/{id}` 迁移 | `SessionUser.is_admin` |

**v1 不做**：record/case 枚举 UI（非 admin）；export；orgs；grants 管理页。

### v1.1（`org_members` / `library_grants` 落地后）

- `/ui/orgs/*`、`/ui/libraries/{id}/grants`
- entitlement resolver 替换 v1 启发式

---

## 7. 导航与布局规则

1. **导航**（参数化 `render_page`）：
   - 普通用户 v1：`我的主页 | Libraries | API Keys`
   - 普通用户 v1.1：加 `Orgs`
   - 产品管理员：末尾加 `Observatory`（弱化色）
2. logo → `/ui/me/`；列表页统一 card+table；分页 `?page=N` 每页 50。
3. 破坏性动作：行内 form + confirm（同 design/14）。
4. **CSS 预算**：目标 0 新组件；复用现有 class。

---

## 8. API / 数据依赖

### 8.1 已存在

`list_write_audit_for_principal`、`get_feedback_summaries`、`list_api_keys_for_principal`、`get_record`、`SessionUser.is_admin`。

### 8.2 v1 新增

| Helper | 说明 |
|--------|------|
| `count_write_audit_for_principal` | 统计卡 + 分页 |
| `list_feedback_for_principal` | 投票列表 |
| `count_feedback_for_principal` | 统计卡 |
| `list_entitled_libraries_for_principal` | v1 = 个人库 ∪ Community Library ∪ 全部 active key grants 并集；v1.1 换 entitlement resolver，**签名不变** |
| `get_library_stats(library_id)` | cases/records/outcome 聚合；Stats-only 页与匿名 public 页 |
| `assert_admin_configured()` | Authing on 且 admin 白名单非空，否则 refuse boot |

### 8.3 路由

- 新文件 `routes_portal.py`（`/ui/me/*`、`/ui/libraries/*`、`/ui/records/*`）。
- 复用 `routes_keys.py` 的 session 门控与 `_assert_same_origin`。
- 所有 POST 过 same-origin 校验。

---

## 9. 实现五条规则

1. 登录后一切入口收敛到 `/ui/me/`。
2. `render_page` 导航参数化是第一个 PR。
3. record 迁到 `/ui/records/{id}`，旧路径 301，feedback POST 一并迁移。
4. 管理能力与 `is_library_admin` / org role **单点判定**；UI 与路由共用。
5. v1 不渲染 org UI；`list_entitled_libraries_for_principal` 锁定签名，v1.1 只换实现。

---

## 10. 产品决策（ratified）

见 [15-user-portal-decisions-for-owner.md](15-user-portal-decisions-for-owner.md)。要点：**Observatory 403**、**空 admin 拒绝启动**、**Stats≠Enumerate**、**匿名仅 public Stats**、**v1 展示 principal_id**。
