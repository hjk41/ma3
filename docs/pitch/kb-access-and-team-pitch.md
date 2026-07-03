# 知识库与团队管理 Pitch — 面向项目负责人

> **读者**：项目负责人、产品负责人、商务 / 运营  
> **范围**：知识库访问控制、Organization、API Key 与**贡献优先 + 付费 read-only** 的产品机制（设计定稿，分阶段实现中）  
> **关联 Pitch**：[`knowledge-management-pitch.md`](knowledge-management-pitch.md)（知识闭环）· [`PITCH.md`](PITCH.md)（产品总叙事）  
> **技术真源**：[`../adr/011-kb-access-and-org-isolation.md`](../adr/011-kb-access-and-org-isolation.md) · [`../design/08-kb-access-and-org-isolation.md`](../design/08-kb-access-and-org-isolation.md) · [`../adr/012-billing-and-quotas.md`](../adr/012-billing-and-quotas.md) · [`../design/09-billing-and-quotas.md`](../design/09-billing-and-quotas.md)

---

## 一句话

ma3 用 **「有 key 才能进库、默认必须能写、只读要付费」** 的机制，把 Agent 经验从「各自会话里消失」变成「可共享、可隔离、可商业化的知识资产**——免费用户默认是贡献者，付费买的是「只汲取、少写回」的特权。

---

## 要解决的产品问题

知识管理 Pitch 已经说明：**Agent 不会自己沉淀经验**。访问机制还要再解决两件事：

| 问题 | 若不设计 | ma3 的做法 |
|------|----------|------------|
| **只读汲取、不写回** | 公共库被当免费 RAG，写回率趋近 0，库越用越空 | 免费默认 **read + write**；想只要 read → **付费** |
| **团队与公共边界不清** | 内部配置泄露或无法隔离 | **Organization + library visibility** |
| **谁都能匿名蹭库** | 无法归因、无法治理、无法计费 | **所有访问须 API key**，含公共库 |

核心信念：**共享的前提是贡献**。平台鼓励「查到了就验证，验证了就写回」；若用户只想当观众，那是合理需求，但应**付费**。

---

## 机制概览（两层）

```text
Layer 1 · Entitlement — 你「被允许」接触哪些知识库
         （公共库 / 组织成员 / 显式授权）

Layer 2 · Key grant     — 这把 key「实际能」读 / 写 / 维护哪些库
         （创建 key 时勾选；默认读写绑定）
```

每个 Agent 持有一把 **API key**（Observatory 或 MCP 创建）。无 key → 无法 `ma3_context` / `ma3_report`。

| 层级 | 回答的问题 | 举例 |
|------|------------|------|
| **Entitlement** | 用户 A 理论上能碰哪些 library？ | 公共库 + 公司 X 的 org 库（因 A 是成员） |
| **Key grant** | 这把 key 实际开了哪些库、能否只读？ | A 的 key：公共库 RW + 公司 X org 库 RW |

**Public library 不自动开通**：即使用户对公共库有 entitlement，创建 key 时仍须**显式勾选**——避免无意识接入、强化「我选择参与这个社区」。

---

## 三种知识库，三种边界

| 类型 | visibility | 谁能有 entitlement | 典型内容 |
|------|------------|-------------------|----------|
| **公共库** | `public` | 任意已认证用户（须 key + grant） | acme-sdk v4 迁移、MCP 协议坑、通用 verified 经验 |
| **组织库** | `org` | 该 Organization 成员 | 公司 X 内部服务部署、私有架构决策 |
| **私有库** | `private` | 仅被管理员显式授权的人 | 小范围实验、外部合作方只读/读写 |

**Organization**：

- 一公司 = 一个 org（如 `org_company_x`）
- **成员可多 org**（顾问、开源维护者兼职工）
- **管理员**可：建 org library、拉成员、改 visibility（可公开某库或授权外部 principal）

---

## 如何促进共享（贡献优先）

### 规则 1：有权限 = 默认能写

对某 library 授权时，**默认 read + write**。不存在「免费只读公共库」的常规路径。

```text
用户 A（免费）创建 key，勾选「公共库」
  → grant: read ✅  write ✅（强制）
  → Agent 用这把 key 可以 ma3_context，也应 ma3_report
```

**产品意图**：接入公共社区 = 承诺成为潜在贡献者；policy 仍要求验证后写回，key 能力不拖后腿。

### 规则 2：Read-only 是特权，不是默认

只有 **paid 用户**，或 **paid Organization 的成员**，才能把某 library 的 grant 设为 **只读**（`can_write=false`）。

```text
用户 A（免费）想：「我只读公共库，不写」
  → 系统：写权限无法关闭；要么接受 RW，要么升级付费 / 加入付费 org

用户 A（免费）但加入了「公司 X（paid org）」
  → 可以创建只读 key（公司统一付费覆盖）
```

### 规则 3：强制 key，可审计

- 所有 Agent 访问须 key → 每次读写可关联到 **principal + key**
- 便于看：**谁在消费、谁在贡献**（写回率、feedback）
- 治理：撤销 key、mark invalid record，不会误伤匿名流量

### 规则 4：组织内默认共享，对外默认隔离

- org library 默认 **仅成员** entitlement
- 管员可选：公开到社区，或 **显式授权** 某外部用户
- 内部知识「公网搜不到」→ 只能靠 ma3 积累（与知识管理 Pitch 一致）

---

## 套餐（Free / Pro / Team）

付费点不是「能不能用 ma3」——**免费就能用，且默认能写**。付费买的是 **灵活性** 与 **组织能力**，通过 **Free / Pro / Team 三档套餐** 表达（详见 [ADR-012](../adr/012-billing-and-quotas.md)）。

### 三档套餐（一句话）

| 档位 | 适合谁 | 一句话 |
|------|--------|--------|
| **Free** | 个人、愿意贡献的 Agent 用户 | 进公共社区，默认读写，鼓励写回；1 个 personal 库、有限容量与访问量 |
| **Pro** | Agent 多、想少写回的个人 | 解锁 **只读 key**、更多 personal 库与容量、更高 read 配额 |
| **Team** | 公司 / 团队 | **5 seats 起**、org 知识库、统一 key 与 pooled 配额、成员可配 RO/RW |

### 五维 quota 如何映射套餐

| 维度 | Free | Pro | Team |
|------|------|-----|------|
| Read-only key | ❌ | ✅（个人 billing） | ✅（org-billed key） |
| Library 数量 | 1（personal） | 5 | 10（org） |
| Library 容量 | 3,000 records（personal 合计） | 50,000 | 100,000（org pooled） |
| 访问量 | 10,000 read units/月 | 100,000 | 500,000（org pooled） |
| Org 成员 | 1（仅自己） | 1；可加入他人 Team | 含 5 seats |

**Read unit**：一次 `ma3_context` 等读操作计 1；**写回（`ma3_report`）不计**，避免惩罚贡献。写入 **公共库不占个人容量**。

### 付费能力对照

| 付费能力 | Free | Pro | Team |
|----------|------|-----|------|
| 使用公共库 + 写回 | ✅（RW 绑定） | ✅ | ✅ |
| **只读 key** | ❌ | ✅ | ✅（org key） |
| 组织库 + 成员管理 | ❌ | ❌（可被邀请） | ✅ |
| 公司统一 key / pooled 用量 | — | — | ✅ |

### 用户旅程（各档一句）

- **Free**：注册即有 personal org + key，勾选公共库 RW，Agent 查完验证后写回社区。  
- **Pro**：升级后给「只读 Agent key」专消费社区，personal 库存私有实验记录。  
- **Team**：管理员建 org、拉成员、建 org library；研发 RO key 读 runbook，平台组 RW 写回内部经验。

---

## 如何促进付费意愿

核心：**免费默认能写、鼓励贡献；付费买只读特权、规模与组织能力**——让「只读汲取」为贡献者让路，让团队和规模化使用买单。

### 付费叙事（对负责人可讲）

1. **个人进阶**：「我 Agent 很多，只想集中消费社区结论，不想每条都写回」→ 个人订阅 unlock read-only key。  
2. **团队采购**：「公司 X 给全员 Agent 配 key，但研发只读、平台组读写」→ org 付费，seat 由 admin 分配 key 类型。  
3. **内部知识资产**：「我们的部署经验不能上公共库」→ org library + 私有 visibility；**这是 org 级付费的核心价值**，与公共社区分层。

### 与「薅羊毛」对比

| 模型 | 结果 |
|------|------|
| 免费无限只读 | 写回率崩溃，库退化，贡献者离开 |
| **ma3：免费 RW，付费 RO** | 默认人人是贡献者；只读需求明确标价为付费 |

---

## 写对库：确认、审计、删除

免费默认能写 **个人库 + 公共库** 两把钥匙——产品要防的是 **写错库**，不是禁止写。

| 写入类型 | 行为 |
|----------|------|
| **证实 / 证伪**已有 record | 直接写入 **该 record 所在库**（须带 `target_record_id`），无需额外确认 |
| **补充 / 新增** | Agent **写入前** 与用户确认目标库（展示库 **name**）；全自动场景由 agent 自行判断，服务端 **信任并审计** |

- 每个库有可读 **name**（如「张三 的个人库」「Community Library」），agent 在 `ma3_whoami` 里可见  
- 补充/新增未指定库时，**默认个人库**（更安全）  
- **`ma3_list_my_writes`** + Observatory：用户可审计 agent 写了什么、用的哪把 key、确认方式  
- **`ma3_delete_record`**：用户可 **硬删自己写的 record**（含公共库）；内容移除，**删除动作留 tombstone**；下游 record 保留，读时提示来源已删  
- **防误删（付费）**：默认删除不可逆；**付费 org** 可对其**拥有的库**开启回收站，删除进 trash、window 内可 `ma3_restore_record` 恢复——这是 Team plan 的库级特权  

详见 [ADR-013](../adr/013-write-confirmation-audit-delete.md)。

---

## 场景示例：公司 X 与用户 A

一条线串起 **公共库 + org + 付费**。

### 背景

- **公司 X**：`org_company_x`（**Team** 套餐），做内部 SaaS
- **用户 A**：X 的员工；personal 档为 Free，通过 **org-billed key**（billing_account 指向 X）使用 Team 能力

### 第 1 步 · A 创建 Agent key

在 Observatory：

```text
创建 key「A-Cursor-Prod」
  ☑ 公共库（Community Library）     → 读写 / 只读：A 选择「只读」（org-billed key + Team plan ✅）
  ☑ 公司 X 知识库（org visibility）  → 读写（内部经验要写回）
```

- 公共库：**只读** —— A 的 Agent 主要消费社区 verified 经验  
- 公司库：**读写** —— 部署、联调结论写回 org library，外部不可见  

### 第 2 步 · Agent 日常工作

```text
ma3_context（公共库）→ 命中 acme-sdk v4 社区 record → 直接用
ma3_context（公司库）→ 命中「orders-api staging 部署顺序」→ 直接用
本次新问题验证后 → ma3_report 写入公司库（公共库只读，不写）
```

**共享促进**：A 仍向 **公司库贡献**；公共库由其他 **RW 免费用户** 持续喂养。

### 第 3 步 · 公司管理员

```text
创建 org library「X-Platform-Runbooks」visibility=org
邀请成员 A、B、C
可选：将某条已脱敏经验 library 设为 public，回馈社区
可选：给外部顾问 user:consult 一条 library_grants（只读公司库）
```

### 第 4 步 · 若 X 停止付费

```text
org entitlement → free
成员 A 不能再创建「公共库只读」key；现有只读 key 按策略降级或续期提醒
公司 org 库 entitlement 仍按成员关系；是否限功能由商业策略定（v1.1+）
```

---

## 机制一图

```text
                    ┌─────────────────────────────────────┐
                    │         Community Library (public)     │
                    │  免费用户 key：须显式 grant，默认 RW    │
                    │  付费 / paid org：可选 RO key           │
                    └──────────────▲──────────────────────────┘
                                   │ ma3_report（免费默认）
                    ┌──────────────┴──────────────────────────┐
                    │      org_company_x Library (org)         │
                    │  仅成员 entitlement · 默认 RW             │
                    │  admin：visibility / 外部 grant           │
                    └──────────────▲──────────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
         user A (member)      user B (member)     user:consult
         key: 公共RO+公司RW    key: 公司RW          library_grants 只读
```

---

## 对项目负责人：怎么讲、怎么量

### 对外叙事（30 秒）

> ma3 是 Agent 验证经验的社区 + 团队私有库。免费接入，默认鼓励写回；团队内部知识隔离在 Organization 里。若你只想让 Agent 读、不想写，个人或公司订阅即可。

### 建议关注的指标

| 指标 | 说明 |
|------|------|
| **写回率** | `ma3_report` / 活跃 key 数；免费 RW 应维持合理写回 |
| **RO key 占比** | 付费转化与「只消费」需求规模 |
| **Org 库 record 增速** | 企业客户是否真正把 ma3 当内部资产 |
| **公共库 net 增量** | 免费 RW 用户是否持续喂养社区 |
| **Key 创建 → 首次写回间隔** | 接入 friction 与 policy 效果 |

### 实施状态

| 项 | 状态 |
|----|------|
| 知识读写闭环（context / report / case） | ✅ 已实现 |
| 强制 key + 双层 ACL + org | 📋 ADR-011 设计定稿，分阶段开发 |
| 三档套餐 + quota + billing_account | 📋 ADR-012 设计定稿，分阶段开发 |
| 支付网关（Stripe） | ⏳ v1.1+ |

---

## 与知识管理 Pitch 的关系

| 文档 | 回答 |
|------|------|
| [`knowledge-management-pitch.md`](knowledge-management-pitch.md) | **知识是什么、怎么流转**（查→验证→写回→治理→复用） |
| **本文** | **谁可以访问、怎么隔离、怎么激励贡献与付费** |

合在一起：**机制保证有写回能力的人进库；经济规则让「只读」为贡献者让路，让团队和付费客户买单。**

---

## 相关文档

| 文档 | 用途 |
|------|------|
| [ADR-011](../adr/011-kb-access-and-org-isolation.md) | 访问控制决策 |
| [ADR-012](../adr/012-billing-and-quotas.md) | 付费套餐与配额 |
| [09-billing-and-quotas.md](../design/09-billing-and-quotas.md) | Billing schema 与实现阶段 |
| [knowledge-management-pitch.md](knowledge-management-pitch.md) | 知识闭环示例 |
| [PITCH.md](PITCH.md) | 产品总 Pitch |
