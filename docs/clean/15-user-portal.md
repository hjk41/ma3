# 15 — 用户门户（User Portal）

> **状态**：定稿（2026-07-04，产品决策 ratified）  
> **IA / 布局真源**：[22-user-portal-ui-layout.md](22-user-portal-ui-layout.md)（顶栏、列表壳、stat 链接）  
> **视觉真源**：[15-user-portal-visual.md](15-user-portal-visual.md)  
> **技术约束**：SSR HTML（`ui_theme.py`），无 SPA

---

## 0. 一句话结论

登录后默认落地页从 `/ui/observatory/` 改为 **`/ui/me/`**（个人主页）。Observatory 保留原路由但降级为**产品管理员专属**（`is_admin` 门控，非 admin → **403**）。普通用户看到的是「我的库权限、我写过的记录、我投过的票、API keys」——**以 principal 为中心**的视图。

---

## 1. 已 ratified 产品决策

| # | 议题 | **决定** |
|---|------|----------|
| 1 | 非 admin 访问 Observatory | **403 Forbidden**（非 302） |
| 2 | Authing 已启用且 admin 白名单为空 | **拒绝启动**（refuse boot）；LAN `authing_enabled=False` 不受限 |
| 3 | 库内容可见性 | 有读 entitlement → **仅 Stats**；不可枚举/改/导出；枚举/修改/导出 → 库管理员或产品管理员 |
| 4 | 未登录访客 | **仅 public 库 Stats**（`lib_default`）；无 record 详情、无投票 |
| 5 | `principal_id` | **v1 在 `/ui/me/settings/` 只读展示**（无复制）；不在概览页展示 |
| 6 | 显示名 | **`/ui/me/setup/` 一次性设定**；settings 只读（[17](17-display-name-registration.md)） |
| 7 | 顶栏 IA | 我的主页 · **库 · 记录 · 投票 · API Keys**（同级） |
| 8 | 账户 subnav | 仅 `/ui/me/*`：**概览 · 设置** |
| 9 | 列表页文案 | h1 / stat：**记录、投票**（非「我的贡献/我的投票」） |
| 10 | Stat cards | 5 张整卡可点：记录、待发布、可访问库、投票、API Keys |
| 11 | 个人库名 | `{display_name} 的个人库` |

---

## 2. 角色

| 角色 | 身份判定 | 核心诉求 |
|------|----------|----------|
| **普通用户（贡献者）** | Authing session + principal | 库权限、写入、投票、自助 key |
| **库管理员** | `library_grants` maintainer/admin，或 personal owner，或 org admin | 管库授权、审 draft（v1.1 UI） |
| **组织管理员** | `org_members.role == admin` | 管成员、建 org library（v1.1） |
| **产品管理员** | `SessionUser.is_admin` | 全局健康度（Observatory） |

角色**叠加**：产品管理员也是普通用户；Observatory 只是多出来的导航项。

---

## 3. 路由树

```text
/ui/me/                      个人主页 ★ 默认落地
/ui/me/settings/             账户（显示名只读、Principal ID）
/ui/me/setup/                首次显示名（一次性，design/17）

/ui/me/writes/               记录列表（顶栏「记录」）
/ui/me/votes/                投票列表（顶栏「投票」）
/ui/records/{record_id}/     单条详情 + 投票 + buffer 操作区

/ui/libraries/               我有读 entitlement 的库
/ui/libraries/{lib_id}/      库详情 — Stats only（非 admin）
/ui/libraries/{id}/settings/ 库 buffer 设置（owner）

/ui/keys/                    API key 管理（design/14）
/ui/keys/{key_id}            key 详情

/ui/observatory/             产品管理员专属

[v1.1] /ui/orgs/*, /ui/libraries/{id}/records/, /ui/libraries/{id}/grants
```

- record 详情 canonical URL：`/ui/records/{id}`；旧 Observatory 路径 301
- logo → `/ui/me/`；Authing 回调无 `next` → `/ui/me/`

---

## 4. 库内容三级能力（Stats / Enumerate / Mutate）

| 能力 | 普通用户（有读 entitlement） | 库管理员 | 产品管理员 |
|------|------------------------------|----------|------------|
| **Stats** — 聚合数字 | ✅ | ✅ 所管库 | ✅ 全局（Observatory） |
| **Enumerate** — record/case 列表、browse、search UI | ❌ | ✅ 本库 | ✅ 全局 |
| **Mutate / Export** | ❌ | ✅ 本库 | ✅ 全局；Export v1.1+ |

普通用户**不能**在 UI 上浏览库内 record 列表；只能看 Stats，并通过「记录 / 投票」列表或已知 record ID 深链打开单条详情。

**v1 读 entitlement 启发式**：`个人库 ∪ lib_default ∪ active key grants 并集`；v1.1 换 entitlement resolver，**API 签名不变**。

---

## 5. 页面概要

详细线框与 query 契约见 [22-user-portal-ui-layout.md](22-user-portal-ui-layout.md)。

| 页面 | 要点 |
|------|------|
| `/ui/me/` | avatar + 显示名；5 可点 stat；我的库表；最近贡献 |
| `/ui/me/settings/` | 只读显示名 + Principal ID（无复制） |
| `/ui/me/writes/` | sort/filter/per_page/batch（buffered）；h1「记录」 |
| `/ui/me/votes/` | sort/filter/per_page；改票仅在 record 详情 |
| `/ui/libraries/{id}/` | Stats 卡 + 我的访问；**无** record 表格 |
| `/ui/records/{id}/` | 登录 + 读 entitlement；buffered 非 author → 404 |
| `/ui/observatory/` | 非 admin → 403 HTML +「返回我的主页」 |

**匿名**访问 `lib_default`：Stats 卡 + CTA「登录以贡献与投票」；无 record 详情。

---

## 6. 角色可见性矩阵

| 页面 / 入口 | 普通用户 | 库管理员 | 产品管理员 |
|---|---|---|---|
| `/ui/me/*` | ✅ | ✅ | ✅ |
| `/ui/keys/*` | ✅ | ✅ | ✅ |
| `/ui/records/{id}` | ✅ 单条 | ✅ | ✅ |
| `/ui/libraries/{id}/` Stats | ✅ | ✅ | ✅ |
| `/ui/libraries/{id}/records/` 枚举 | ❌ | ✅ | ✅* |
| `/ui/libraries/lib_default/` 匿名 Stats | ✅ | — | — |
| `/ui/observatory/` | ❌ **403** | ❌ **403** | ✅ |

\* 产品管理员（`is_admin`）**不**自动获得 org/库业务管理权；全局观测与业务管理分离。

**越权直查 URL** → 404（不泄露资源存在性）。

---

## 7. v1 vs v1.1

### v1（已存在表即可）

- `/ui/me/` + writes + votes + settings
- `/ui/libraries/` + Stats-only 详情 + 匿名 public Stats
- 启动拒绝空 admin 白名单
- Observatory 403 + record URL 迁移
- Write buffer UI（design/16）
- 显示名 setup（design/17）

**v1 不做**：record/case 枚举 UI（非 admin）；export；orgs；grants 管理页；community browse/search UI。

### v1.1

- `/ui/orgs/*`、`/ui/libraries/{id}/grants`、`/ui/libraries/{id}/records/`
- entitlement resolver 替换启发式
- URL 美化 `/ui/records/`、`/ui/votes/`
- settings 页 Principal ID 复制（可选）

---

## 8. 数据依赖

### 已存在

`list_write_audit_for_principal`、`get_feedback_summaries`、`list_api_keys_for_principal`、`get_record`、`SessionUser.is_admin`。

### v1 新增 helper

| Helper | 说明 |
|--------|------|
| `count_write_audit_for_principal` | 统计卡 + 分页 |
| `list_feedback_for_principal` | 投票列表 |
| `count_feedback_for_principal` | 统计卡 |
| `list_entitled_libraries_for_principal` | v1 启发式并集 |
| `get_library_stats(library_id)` | Stats-only 页 |
| `assert_admin_configured()` | Authing on 且 admin 白名单非空 |

### 路由

- `routes_portal.py`：`/ui/me/*`、`/ui/libraries/*`、`/ui/records/*`
- 复用 `routes_keys.py` 的 session 门控与 `_assert_same_origin`

---

## 9. 实现五条规则

1. 登录后一切入口收敛到 `/ui/me/`。
2. `render_page` 导航参数化是第一个 PR。
3. record 迁到 `/ui/records/{id}`，旧路径 301，feedback POST 一并迁移。
4. 管理能力与 `is_library_admin` / org role **单点判定**；UI 与路由共用。
5. v1 不渲染 org UI；`list_entitled_libraries_for_principal` 锁定签名，v1.1 只换实现。

---

## 10. 验收

[v1-user-portal](../acceptance/v1-user-portal.md) P1–P19。
