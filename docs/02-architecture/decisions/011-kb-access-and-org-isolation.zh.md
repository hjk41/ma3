# ADR-011 — 知识库访问与组织隔离

## 状态

Accepted（2026-07-02）

## 背景

v1 已实现 MCP 读写闭环、混合检索、Authing 登录与 Observatory，但授权模型仍是 **env-var 密钥列表 + 单 library 硬编码**：

- 匿名可读 `lib_default`（`security.py` 中 `readable_library_ids` 对 anonymous 返回 default library）
- `MA3_WRITER_API_KEYS` / `MA3_MAINTAINER_API_KEYS` 全局列表，无 per-key ACL
- `organizations` / `libraries` 表存在但无成员关系、无 visibility  enforcement
- `ma3_report` 写路径固定 `lib_default`

产品方向已明确：

1. **所有 Agent 必须有 key 才能访问**，包括公共知识库
2. **鼓励贡献而非只读汲取**：对某 library 要么无权限，要么读写都有；**read-only key 仅付费用户或付费 org 成员**可创建
3. **Organization**：多成员、成员可属多 org；org 管理员可建 org library；默认 org 内可见，可公开或显式授权外部 principal

需在不 fork 产品的前提下，将授权从「凭证推导」改为「数据驱动」。

## 决策

### 1. 双层授权模型

**Layer 1 — Entitlement（谁 *可以* 访问某 library）**

| visibility | 谁可被授予 entitlement |
|------------|------------------------|
| `public` | 任意已认证 principal（仍须 key 显式 grant） |
| `org` | 所属 org 的 `org_members` |
| `private` | 仅 `library_grants` 显式行 |

Org 管理员可将 org library 提升为 `public`，或对非成员 principal 添加 `library_grants`。

**Layer 2 — Key capability（某 key *实际* 能做什么）**

- 每个 API key 通过 `key_grants` 绑定一个或多个 library
- 每行 grant：**read 隐含**；`can_write` 默认 **true**；`can_maintain` 可选
- **Read + Write 耦合**：创建 `can_write=false` 的 grant 要求 key 所有者 `entitlement=paid`，或属于任一 `entitlement=paid` 的 org
- 公共 library（`lib_default`，`visibility=public`）**不自动**出现在 key 上；用户创建 key 时必须**显式勾选**该 library

### 2. 强制 API Key；移除匿名 MCP 读

- 所有 MCP **数据工具**（context / report / case / feedback / review 等）要求有效凭证：**API key** 或 **ma3 签发的 MCP OAuth access token**（ADR-016）
- 无凭证或无效凭证 → **401** / JSON-RPC `-32001`（附带 `WWW-Authenticate` resource metadata 供 OAuth 发现）
- **裸 Authing Bearer** 仅用于 Observatory 人类登录与 key 管理 UI/API，**不**作为 MCP 数据路径凭证；**ma3 MCP OAuth token**（绑定 audience/resource）可用于 MCP
- 保留 `MA3_DEV_AUTH=1` + dev key 作为 **break-glass admin bypass**（LAN/dev only）

### 3. API Key 存储与签发

- Key 存 DB 表 `api_keys`：`key_hash`（SHA-256）、`prefix`（展示用）、`owner_principal_id`、可选 `org_id`（计费/覆盖上下文）、`label`、生命周期字段
- **Observatory**（Authing session）：创建 / 列表 / 撤销 key，配置 per-library grants
- **MCP 工具**：`ma3_create_key` / `ma3_list_keys` / `ma3_revoke_key`；新 key grants 必须是 owner entitlement 的**子集**
- 废弃 `MA3_WRITER_API_KEYS` / `MA3_MAINTAINER_API_KEYS`（迁移期可并存，见 Phase 6）

### 4. Organization 与成员

- `org_members(org_id, principal_id, role)`：`role ∈ {admin, member}`；**多对多**（一 principal 可属多 org）
- Org 管理员：创建 org library、设置 visibility、管理成员、对外 grant
- `organizations.entitlement ∈ {free, paid}`；`principals.entitlement` 同理
- **Read-only key 资格**：owner `paid` **或** owner 是任一 `paid` org 的成员（v1 不区分 org admin vs member 的覆盖范围）

### 5. 计费

- v1 **不接入**支付网关；`entitlement` 由平台管理员或 org 管理员手动设置
- 字段与规则预留，便于 v1.1 接 Stripe / 企业合同

### 6. 公共库

- `lib_default` 重定义为 **community public library**（`visibility=public`）
- 现有 record 保留；访问仍须 key + 显式 `key_grants` 行

### 7. Key 与 library/org 的绑定粒度（不强隔离）

- **不强制** 一把 key 只对应一个 library 或单一 org context：一把 key 可同时持有 **跨库、跨 org** 的 grants（如个人库 + 公共库 + 公司库）
- entitlement 解析对该 key 的授权取 **并集**；ma3 **不** 在服务端强制「单一 org 上下文」隔离
- 由此产生的「串味」风险（如员工用同一把 key 同时接触多家 org 库）**由企业行政手段解决**：org 签发专用 key、设备/账号管理、内部策略；ma3 提供 **可审计**（每次读写关联 principal + key + library）作为支撑，而非服务端强绑定

## 后果

### 正面

- 与「Agent 验证经验沉淀、鼓励贡献」产品叙事一致
- 团队隔离可落地：org library + ACL + key grants
- 授权可审计：谁创建了哪个 key、对哪些 library 有何能力
- 为 SaaS 订阅（read-only seat / org 统一付费）预留清晰扩展点

### 负面

- **Breaking change**：匿名 MCP 读消失；现有集成须配 key
- 实现量显著大于 env-var keys；需 migration、UI、测试
- Org 多对多与 visibility 组合增加 support 与文档成本

### 关联

- ADR-001（SaaS 多租户）、ADR-008（维护者分层）、ADR-010（Authing）
- [ADR-013](013-write-confirmation-audit-delete.md) — 写入确认、审计、owner 硬删除
- [authorization-and-libraries.md](../../03-backend/authorization-and-libraries.md) — 完整 schema 与分阶段实现
- [system-overview.md](../system-overview.md) §2 auth 模块
- Pitch：[pitch.md](../../01-product/pitch.md)
