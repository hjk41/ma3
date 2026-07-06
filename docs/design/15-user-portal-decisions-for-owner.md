# 15 — 用户门户：产品决策（已 ratified）

> **Ratified**：2026-07-04，产品负责人  
> 主方案：[15-user-portal-fable.md](15-user-portal-fable.md)

---

## 决策摘要

| # | 议题 | **决定** |
|---|------|----------|
| 1 | 非 admin 访问 Observatory | **403 Forbidden**（非 302） |
| 2 | `MA3_AUTH_ADMIN_USERS` 为空且 Authing 已启用 | **拒绝启动**（refuse boot） |
| 3 | 库内容可见性（含公共库） | 有**读 entitlement**的用户 → **仅统计**（case/record 计数等）；**不可枚举、不可改**；**枚举 / 修改 / 导出**仅管理员（库级或产品级）；导出后续可收费 |
| 4 | 未登录访客 | **仅公共库统计信息**；无 record 详情、无投票 |
| 5 | `principal_id` | **v1 在 `/ui/me/settings/` 只读展示**（无复制） — 2026-07-05 owner 修订，废止「概览页展示+复制」 |

---

## 决策 1 — Observatory 非 admin → 403

- 未登录：302 `/auth/login?next=…`
- 已登录、`not is_admin`：**403**，HTML 页含「返回我的主页」链接
- 导航不对普通用户渲染 Observatory 项
- 集成测试：`test_observatory_non_admin_returns_403`

---

## 决策 2 — 空 admin 白名单拒绝启动

当 `settings.authing_configured and not settings.auth_admin_users`：

- **启动时 raise**（与 misconfigured DB URL 同级），错误信息指向 `MA3_AUTH_ADMIN_USERS`
- `ma3_doctor` 同步报 **fail**
- LAN / `authing_enabled=False` **不受此规则**（Observatory 保持 today 开放只读 dev 行为）

Deploy 清单（202 等）必须包含至少一个 admin 标识。

---

## 决策 3 — 三级库内容能力（Stats / Enumerate / Mutate）

### 能力定义

| 能力 | 普通用户（有读 entitlement） | 库管理员 | 产品管理员 |
|------|------------------------------|----------|------------|
| **Stats** — 库概况数字（cases、records by status、outcome 分布等） | ✅ 对其有读 entitlement 的库 | ✅ 所管库 | ✅ 全局（Observatory） |
| **Enumerate** — record/case **列表**、分页 browse、search UI、批量导出 | ❌ | ✅ 本库 | ✅ 全局 |
| **Mutate** — invalid 标记、删除、grants、visibility | ❌ | ✅ 本库 | ✅ 全局 |

「读 entitlement」v1 启发式：`个人库 ∪ lib_default ∪ active key grants 并集`（见 fable §8.2）；v1.1 换 entitlement resolver。

### UI 映射

- `/ui/libraries/{lib_id}/`（非 admin）：**仅 Stats 卡 + 元数据**（名称、可见性、我的权限、绑定 key）；**不渲染** record/case 表格
- `/ui/records/{record_id}`（已登录 + 对该库读 entitlement）：**单条详情 + 投票**；入口来自「我的贡献 / 我的投票」或**外部深链**（无库级列表 = 不构成枚举 UI）
- 库管理员：`/ui/libraries/{id}/records/`（或管理区块内枚举表）**[v1.1]**；Observatory 保留全局枚举
- **Export**：v1 不做；v1.1+ 仅管理员，后续可按库/组织计费（见 design/09）

---

## 决策 4 — 匿名访客

- **允许**：`/ui/libraries/lib_default/`（或专用 `/ui/public/`）展示 Community Library **统计卡**，无需登录
- **禁止**：任意 record 详情、投票、writes/votes、keys、Observatory、非 public 库
- 未登录访问需 session 的路由 → 302 login（与 today 一致）

---

## 决策 5 — principal_id v1 展示（2026-07-05 修订）

在 **`/ui/me/settings/`** 账户 card 中只读展示 Principal ID（`.id-block`，mono 字体，**无复制按钮**）。

- **不在** `/ui/me/` 概览页展示 Principal ID
- 需要复制的场景保留在 API Keys 页（design/14 `copy-row`）
- 真源：[15-user-portal-me-profile-review-fable.md](15-user-portal-me-profile-review-fable.md)、[22-user-portal-ui-unified-layout-fable.md](22-user-portal-ui-unified-layout-fable.md) §3.2

---

## 已关闭（三方原一致，不变）

- 默认落地 `/ui/me/`
- v1 无 org 管理页
- record canonical URL `/ui/records/{id}` + 旧路径 301
- `is_admin` 与 org/library 业务管理权分离
- v1 无 community **browse/search** UI（与决策 3 枚举禁令一致）
- 投票交互仅在 record 详情页

---

## 建议实施顺序

1. 启动校验 + doctor（决策 2）
2. `render_page` 导航参数化 + login 默认 `next=/ui/me/`
3. `list_entitled_libraries_for_principal` + `get_library_stats`
4. `/ui/me/` + writes + votes；Principal ID 在 settings（决策 5 修订）
5. `/ui/libraries/` 列表 + 库详情（Stats-only 非 admin）
6. `/ui/records/{id}` 迁移 + 匿名 public stats 页（决策 4）
7. Observatory `is_admin` 门控 **403**（决策 1）
