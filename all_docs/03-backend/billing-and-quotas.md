# 付费套餐与配额（Billing & Quotas）

> **ADR**：[ADR-012](../02-architecture/decisions/012-billing-and-quotas.md)  
> **前置**：[authorization-and-libraries.md](authorization-and-libraries.md)  
> **状态**：设计定稿；**v1 未全量实现** — 当前以 `paid_principal_ids` 等启发式过渡（见 [api-keys-ui-and-api.md](../04-frontend/api-keys-ui-and-api.md) 免费档 grant 锁定），schema/enforcement 按 Phase B1–B4 落地  
> **商业叙事**：[pricing-and-plans.md](../07-commercial/pricing-and-plans.md)、[pitch.md](../01-product/pitch.md)

---

## 1. 目标

| 目标 | 说明 |
|------|------|
| 三档套餐 | Free / Pro / Team，五维 quota 映射到 `plans` 表 |
| billing_account | 用量与资源的计费归属一等实体 |
| implicit personal org | 每用户自动 personal org + free billing account |
| 贡献安全 | 公共库写回、ma3_report 不计费惩罚 |
| v1 无 Stripe | `plan_code` 手工设置；schema 预留 provider 字段 |

---

## 2. 概念模型

```text
Principal (user)
    │
    ├── org_personal_{sub}  ── billing_account(plan=free|pro)
    │         └── libraries (personal, max N)
    │
    └── org_members ── org_company_x ── billing_account(plan=team)
              └── libraries (org visibility)

api_key.billing_account_id  →  read usage 计入此处
library.org_id              →  storage / library count 计入 owner org 的 billing_account
```

### 2.1 Read unit 计量

| 工具 | Billable | 规则 |
|------|----------|------|
| `ma3_context` | 是 | 1 + max(0, ceil(records_returned/10) - 1) |
| `ma3_case` | 是 | 同上 |
| `ma3_report` | **否** | 贡献路径 |
| `ma3_feedback` | **否** | |
| `ma3_validate` | **否** | |
| `ma3_list_drafts` / `ma3_review_record` | **否** | maintainer |
| key 管理等 mgmt | **否** | |

仅 **2xx 成功**响应计 billable；4xx 记 observability 不进 quota。

### 2.2 Storage 计量

- 计数：**active + buffered + draft** records（`invalid` 不计）
- 归属：library → owner org → org 的 `billing_account`
- **public library（`lib_default`）**：owner 视为 platform；写入 **不占** writer 任何 quota
- 字段：`libraries.active_record_count`（维护）；可选 `storage_bytes` 汇总

---

## 3. 数据模型

### 3.1 `plans`

```sql
CREATE TABLE plans (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  scope TEXT NOT NULL CHECK (scope IN ('personal', 'org')),
  allow_readonly_grants INTEGER NOT NULL DEFAULT 0,
  deletion_protection INTEGER NOT NULL DEFAULT 0,   -- Team=1，见 design/10 §6b
  max_libraries INTEGER NOT NULL,
  max_records_per_library INTEGER NOT NULL,
  max_records_total INTEGER NOT NULL,
  monthly_read_units INTEGER NOT NULL,
  daily_read_units INTEGER,
  rate_limit_per_min INTEGER NOT NULL DEFAULT 60,
  included_seats INTEGER NOT NULL DEFAULT 1,
  max_external_grants_per_library INTEGER NOT NULL DEFAULT 2,
  max_keys INTEGER NOT NULL DEFAULT 10,
  overage_mode TEXT NOT NULL DEFAULT 'block' CHECK (overage_mode IN ('block', 'allow')),
  created_at TEXT NOT NULL
);
```

**Seed（v1 起点）**：

| code | scope | RO | lib | rec/lib | rec total | read/mo | seats | keys |
|------|-------|----|-----|---------|-----------|---------|-------|------|
| free | personal | 0 | 1 | 1000 | 3000 | 10000 | 1 | 10 |
| pro | personal | 1 | 5 | 10000 | 50000 | 100000 | 1 | 50 |
| team | org | 1 | 10 | 100000 | 100000 | 500000 | 5 | 200 |

Team 的 `max_records_per_library` / `max_records_total` 均为 org **pooled**。

**库数量配额（design/24，2026-07-06 ratified）** — 两层：

| 层级 | personal org | team org |
|------|--------------|----------|
| Plan（用户可见） | Free **1** / Pro **5** | Team **10** |
| 平台硬顶 | **100** | **1000** |

环境变量：`MA3_PLAN_MAX_LIBRARIES_*`、`MA3_PLATFORM_MAX_LIBRARIES_PERSONAL_ORG`（100）、`MA3_PLATFORM_MAX_LIBRARIES_TEAM_ORG`（1000）。`lib_default` 不计入任何 org 库计数。Team org 拥有数硬顶 **100**（`MA3_PLATFORM_MAX_TEAM_ORGS_OWNED`）；加入 org 数软顶 **999**。

### 3.2 `billing_accounts`

```sql
CREATE TABLE billing_accounts (
  id TEXT PRIMARY KEY,
  owner_type TEXT NOT NULL CHECK (owner_type IN ('principal', 'org')),
  owner_id TEXT NOT NULL,
  plan_code TEXT NOT NULL REFERENCES plans(code),
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'past_due', 'cancelled')),
  current_period_start TEXT NOT NULL,
  current_period_end TEXT NOT NULL,
  provider TEXT,
  provider_customer_id TEXT,
  created_at TEXT NOT NULL,
  UNIQUE (owner_type, owner_id)
);
```

### 3.3 `quota_overrides`

```sql
CREATE TABLE quota_overrides (
  billing_account_id TEXT NOT NULL,
  quota_key TEXT NOT NULL,
  value INTEGER NOT NULL,
  reason TEXT,
  expires_at TEXT,
  PRIMARY KEY (billing_account_id, quota_key)
);
```

### 3.4 `usage_events`（append-only）+ `usage_daily` / `usage_monthly`

```sql
CREATE TABLE usage_events (
  id TEXT PRIMARY KEY,
  occurred_at TEXT NOT NULL,
  billing_account_id TEXT NOT NULL,
  principal_id TEXT, api_key_id TEXT, org_id TEXT, library_id TEXT,
  tool_name TEXT NOT NULL,
  operation TEXT NOT NULL CHECK (operation IN ('read', 'write', 'admin')),
  units INTEGER NOT NULL DEFAULT 0,
  records_returned INTEGER,
  status_code INTEGER,
  created_at TEXT NOT NULL
);

CREATE TABLE usage_daily (
  billing_account_id TEXT NOT NULL, date TEXT NOT NULL,
  metric TEXT NOT NULL, value INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (billing_account_id, date, metric)
);

CREATE TABLE usage_monthly (
  billing_account_id TEXT NOT NULL, period_start TEXT NOT NULL,
  metric TEXT NOT NULL, value INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (billing_account_id, period_start, metric)
);
```

`metric`：`read_units`、`reports`（观测用，非 billable）。

### 3.5 扩展 08 的表

| 表 | 新列 |
|----|------|
| `organizations` | `kind (personal|team)`、`billing_account_id` |
| `api_keys` | `billing_account_id`（read usage 归属） |
| `libraries` | `active_record_count`、可选 `storage_bytes` |
| `org_members` | `seat_status (active|pending|removed)`、`joined_at` |

---

## 4. Bootstrap 流程

用户首次 Authing 登录（`ensure_user_principal` 之后）：

```text
1. IF NOT EXISTS org WHERE kind='personal' AND owner=principal:
     CREATE org_personal_{sub}, kind=personal
     CREATE billing_account(owner=org, plan=free)
     INSERT org_members(org, principal, role=admin, seat_status=active)
2. 返回 principal + personal_org_id + billing_account_id
```

显式创建 Team org（v1.1 UI / MCP）：CREATE org(kind=team) + billing_account(plan=team) + creator admin；邀请第 2 人时 check `included_seats`（personal org 永远 1 seat → 403）。

---

## 5. Enforcement 伪代码

### 5.1 Read-only grant（key 创建）

```python
def validate_key_grants(billing_account_id: str, grants: list[KeyGrant]) -> None:
    plan = plan_for_billing_account(billing_account_id)
    for g in grants:
        if g.role == "reader" and not plan.allow_readonly_grants:
            reject_or_force_writer(g)   # v1 UI：免费档 Community writer 锁定（design/14）
        assert_subset_of_entitlement(owner, g.library_id)
```

### 5.2 Storage（ma3_report）

```python
def check_storage_quota(library_id: str) -> QuotaCheck:
    if library_id == settings.public_library_id:
        return QuotaCheck(ok=True)  # platform bears cost
    ba = billing_account_for_library(library_id)
    usage, limit = count_records(ba), effective_quota(ba, "max_records_total")
    if usage >= limit:
        raise HTTPException(403, "library is read-only: storage quota exceeded")  # 禁写不禁读
    if usage >= limit * 0.8:
        return QuotaCheck(ok=True, warn=True, pct=usage/limit)
    return QuotaCheck(ok=True)
```

### 5.3 Read usage（MCP 读工具）

超月度上限 → `429` + `Retry-After`。

### 5.4 Org seats

personal org 拒绝加人（403）；team org 超 `included_seats` → 403 提示升级。

---

## 6. MCP `structuredContent.quota`

每个 MCP 响应可选携带（与 `server` 块并列）：

```json
{
  "quota": {
    "billing_account_id": "ba_xxx",
    "plan": "free",
    "read_units": {"used": 8200, "limit": 10000, "period": "2026-07"},
    "storage": {"used": 2400, "limit": 3000, "scope": "personal"},
    "warnings": ["read_units at 82%"],
    "upgrade_url": "/ui/billing/"
  }
}
```

Agent policy 可要求：有 `warnings` 时转告用户。

---

## 7. 与 08 的集成点

| 08 位置 | 09 钩子 |
|---------|---------|
| `validate_key_grants` | `billing_service.allow_readonly()` |
| `create_library` | `check_library_count()` |
| `invite_member` | `check_seats()` |
| MCP 读工具 | `record_read()` + quota warn |
| `ma3_report` | `check_storage()` |
| `ma3_whoami` | 返回 plan + quota 摘要 |
| `ma3_doctor` | `billing_schema_ok`, `usage_rollup_lag` |

---

## 8. Observatory / Admin（Phase B4）

| 页面 | 功能 |
|------|------|
| `/ui/billing/` | 当前 plan、quota 使用率、升级 CTA |
| `/ui/billing/upgrade` | 展示 Pro / Team；v1 手工联系或 admin API |
| Admin API | `PATCH /admin/billing_accounts/{id}` 设 `plan_code`（platform maintainer） |

Stripe webhook 占位：`POST /webhooks/stripe` → v1.1。

---

## 9. 分阶段实现

| Phase | 内容 | 验收 |
|-------|------|------|
| B1 | Schema + seed plans + 登录 bootstrap personal org/ba；无 enforcement | 新用户登录后有 personal org + ba；migration 可重复 |
| B2 | Metering：`record_read_usage` 挂读工具 + rollup job + `active_record_count` | 读 10 次后 `usage_monthly.read_units == 10` |
| B3 | Enforcement：RO grant、library count、storage、seats、read 429、quota warnings；past_due 限写不限读 | `test_billing_enforcement.py` 全绿 |
| B4 | Billing 页 + admin plan API + Stripe webhook stub | — |

---

## 10. v1.1 开放问题

| 项 | 说明 |
|----|------|
| Team overage 默认开/关及单价 | 商业策略 |
| Pro 是否含「轻量 Team」 | 产品包装 |
| Contribution credit | 写回换 read quota |
| 向量检索档位 | 独立 meter |
| Stripe Price ID 与 plan 映射 | 支付接入 |
| `max_keys_per_principal` 启发式迁移 | 并入 plan.max_keys |
