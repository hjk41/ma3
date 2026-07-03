# ADR-012 — 付费套餐与配额（Billing & Quotas）

## 状态

Accepted（2026-07-02）

## 背景

[ADR-011](011-kb-access-and-org-isolation.md) 已定：强制 API key、默认 read+write、read-only key 为付费特权、Organization 与 library 隔离。产品提出五类付费触发：

1. Read-only key 特权  
2. 知识库容量超阈值  
3. 知识库数量超阈值  
4. 单账号访问量超阈值  
5. Organization 成员 > 1  

Fable 与 GPT 5.5 联合评审结论：

- 五维覆盖面正确，但**不应作为五路独立收费**，易重复计费、伤害「贡献优先」叙事  
- 收敛为 **Free / Pro / Team 三档套餐 + quota 上限**  
- 需引入 **`billing_account` 一等实体**；每用户隐式 **personal org**  
- **写路径与公共库写回**不得反向惩罚贡献者  

v1 **不接入** Stripe；`plan_code` 由平台管理员手工设置。

## 决策

### 1. 三档套餐（Free / Pro / Team）

| 维度 | Free | Pro | Team |
|------|------|-----|------|
| Read-only key | ❌（public grant 强制 RW） | ✅ 个人 billing account | ✅ org-billed key |
| Library 数量 | personal：**1**；public grant 不计 | personal：**5** | org：**10** |
| Library 容量 | **1,000** active records/库，personal 合计 **3,000** | **10,000**/库，合计 **50,000** | org pooled **100,000** |
| 访问量（read units/月） | **10,000** | **100,000** | org pooled **500,000** |
| Org 成员 | personal org **1 人** | 同左；可被邀请进 Team | **含 5 seats** |
| 防误删（回收站/恢复） | ❌ | ❌ | ✅ 对 org 拥有库可开启（见 [ADR-013](013-write-confirmation-audit-delete.md)） |
| Rate limit | 60 req/min/key | 120 | 300 |

具体数字存于 `plans` 表，可运营调整。

**Read unit**：`ma3_context` / `ma3_case` / `ma3_search_explain` 成功响应各计 1 unit；返回 records >10 时按 `ceil(n/10)` 计。`ma3_report`、`ma3_feedback`、`ma3_validate`、maintainer 工具 **不计** billable units。

### 2. Billing account（一等实体）

- 表 `billing_accounts`：`owner_type`（principal | org）、`owner_id`、`plan_code`、`status`、计费周期字段  
- 用户首次 Authing 登录 → 创建 **implicit personal org**（`org_personal_{sub}`）+ personal `billing_account(plan=free)`  
- 显式创建 Team org → 独立 `billing_account(plan=team)`  
- **`api_keys.billing_account_id` 必填**；创建 key 时选择 Personal 或某 Team org（须为成员）  
- 访问量计入 **key 的 billing_account**；存储/库数计入 **library owner org 的 billing_account**

### 3. 贡献优先 invariant（不可违反）

1. 写入 **public library**（`lib_default`）→ storage 归 platform，**不计** writer 的 storage quota  
2. **`ma3_report` 等写路径** → 不计 read usage  
3. Free 用户 grant public library → **`can_write` 强制 true**（ADR-011）  
4. Read-only grant → 仅当 `billing_account.allow_readonly_grants == true`（Pro personal 或 Team org-billed key）

### 4. Read-only 与 billing context（收窄 ADR-011）

- ADR-011「paid org 成员可开 RO key」**收窄**为：仅 **org-billed key**（`billing_account` 指向 Team org）或 org admin 明确授权的 org context  
- 避免 Team 订阅外溢到成员个人 free billing account  

### 5. 五维 enforcement

| 维度 | 时机 | 超限 |
|------|------|------|
| RO grant | key/grant 创建 | 403；Free FORCE RW |
| Library 数量 | create_library | 403 + upgrade |
| Storage | ma3_report 写 **owned** library | 80% 软警告；**超 cap（≥100%）该库转只读**：禁写，读不受影响 |
| Read usage | MCP 读成功 | 月度超限 429；Team 可选 overage（v1.1） |
| Org members | invite accept | free personal 第 2 人 403；Team 超 seat 403 |

**降级/欠费**：读永远可用；写/建库/invite 受限；存量 RO key 宽限 30 天后转 RW 或 revoke；**系统不自动删 record**（用户可经 [ADR-013](013-write-confirmation-audit-delete.md) 硬删自己的 record）。

### 6. Quota 与 rate-limit 分离

- **Rate limit**（req/min）：防滥用，各档不同  
- **Monthly read units**：商业化配额，独立计量  

### 7. 外部协作者

- `library_grants` **不算** org seat  
- Free：每库 **2** 个外部 grant 上限（v1.1 可配置，设计预留）

### 8. `entitlement` 字段迁移

- `principals.entitlement` / `organizations.entitlement`（ADR-011）保留为 **derived 兼容投影**  
- 真源：`billing_account.plan_code` + `plans` quota 列 + `quota_overrides`

## 后果

### 正面

- 套餐清晰：Free 贡献、Pro 个人灵活、Team 组织资产  
- 五维映射成本，又不重复收费  
- billing_account 解耦 key 用量与 org 资源  
- 为 Stripe v1.1 预留 schema  

### 负面

- 实现复杂度高于二元 `paid` flag  
- implicit personal org 增加 onboarding 与 UI 解释成本  
- 需 usage rollup 与 enforcement 联调  

### 关联

- [ADR-011](011-kb-access-and-org-isolation.md) — ACL 前置  
- [ADR-013](013-write-confirmation-audit-delete.md) — owner 硬删与 tombstone（修订「不删 record」）  
- [`docs/design/09-billing-and-quotas.md`](../design/09-billing-and-quotas.md) — schema 与分阶段实现  
- [`docs/pitch/kb-access-and-team-pitch.md`](../pitch/kb-access-and-team-pitch.md) — 商业叙事  

## 实现顺序

1. ADR-011 Phase 1–3（schema + key auth + entitlement 耦合）  
2. ADR-012 Phase B1–B3（billing schema → metering → enforcement）  
3. ADR-012 Phase B4（Observatory billing UI + Stripe stub，v1.1 接支付）  
