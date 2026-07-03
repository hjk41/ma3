# 知识管理 Pitch — 面向项目负责人

> **读者**：项目负责人、产品负责人、技术负责人  
> **范围**：ma3 v1 知识库读写、检索、治理的**当前实现**与**演进方向**  
> **产品总 Pitch**：[`PITCH.md`](PITCH.md)  
> **技术细节**：[`../design/07-kb-read-write-review.md`](../design/07-kb-read-write-review.md)

---

## 一句话

ma3 的知识管理**沉淀 Agent 已经验证（或证伪）的经验**——让下一个 Agent 动手前查得到、做完后写得回，并通过分层治理保证**可信、可解释、可问责**。

**为什么需要一个平台**（而不是靠每个 Agent 自己搜、自己记）：

1. **新知识不停出现** —— 新版本、新工具、新踩的坑每天在变，公网信息常常**过时、矛盾，或被旧版本答案淹没**。
2. **现有 Agent 不会自己沉淀与分享** —— 验证或证伪完，结论随会话一起丢弃；下一个 Agent 只能从零再来一遍。

> **范围说明**：本文示例先聚焦**可公开的信息**（公共库、通用工具、可复现的坑）；组织内部专有知识的沉淀在后续章节描述。

---

## 场景示例：一条知识如何走完整个闭环

> 用**一个连续故事**串起知识管理的每一步：**查 → 验证 → 写回 → 治理 → 复用**。  
> 所有能力均为 ma3 v1 **已实现**。

**主角**：小李（周一）、小王（几天后），用 Agent 做同类工作——**不一定同团队**，因为这是关于公共库的知识。

> **为什么不直接上网搜？**  
> Agent 当然会先搜公网。但对**刚出现、还在快速变化**的知识（新版本、新工具、新踩的坑），公网往往**过时、矛盾，或被旧版本答案淹没**——照着改反而更糟。更关键的是：**没有哪个 Agent 会主动把自己刚验证 / 证伪的结论整理出来分享给下一个**。ma3 就是让这些经验被沉淀、被复用。

### 第 1 幕 · 查（ma3_context）

周一，小李让 Agent 把项目依赖 `acme-sdk` 升级到刚发布的 **v4**。构建后运行报错 `client.connect is not a function`。Agent 动手前先查 ma3：

```text
ma3_context(
  problem="acme-sdk v4 升级后 client.connect is not a function",
  target={"product":"acme-sdk","component":"v4-migration"}
)
  → 库里暂无同类 active record（no matching active records）
```

Agent 也搜了公网：**排名靠前的答案几乎都是 v3 的写法**，还有一些 AI 生成的过时代码——照着改要么不管用，要么引入新错。v4 上周才发布，社区还没沉淀出可靠答案。第一个 Agent 只能自己验证，**但这次成本只需付一次**。

### 第 2 幕 · 验证 + 写回（ma3_report）

Agent 查 v4 changelog + 源码，~40 分钟后既**证伪**了公网流行答案，又**验证**出正确写法：

- ❌ **证伪**：网上排第一的 `new AcmeClient().connect()`（v3 写法）在 v4 已移除
- ✅ **验证**：v4 改为异步工厂 `await AcmeClient.create({...})`，实测连接成功

两条经验一起写回——**「什么行」和「什么不行」同样宝贵**：

```text
ma3_validate(ma3_report, {...})           # 写前 dry-run，避免 schema 错误
ma3_report(
  problem="acme-sdk v4 升级后 client.connect is not a function",
  outcome="resolved",
  result_summary="v4 用 await AcmeClient.create() 取代 v3 的 new + connect()",
  observations=["网上流行的 new AcmeClient().connect() 是 v3 写法，v4 已移除——照抄会报错"],
  evidence=[{kind:"log", summary:"改用 create() 后连接成功；旧写法运行时报错"}],
  applicable_if=["product=acme-sdk", "version>=4.0"],
  idempotency_key="acme-sdk-v4-connect-fix"
)
  → persisted=true, status=active, record_id=vk_abc, case=cs_xx
```

- **验证 + 证伪都留痕**：`observations` 记下「流行但错误」的反例，让下一个 Agent 少走弯路
- **写对库**（[ADR-013](../adr/013-write-confirmation-audit-delete.md)）：证伪 vk_abc → **直接写回公共库**（target 所在库）；若是全新主题 → agent 写入前与用户确认「个人库还是 Community Library」
- **evidence 门槛**：有证据（实测日志）才允许写 `active`，避免空结论污染
- **redaction**：若 summary 里带了 token / 密钥，写时自动替换为 `[REDACTED]`
- **幂等**：网络抖动重试同一 `idempotency_key` → `idempotent_replay=true`，**不产生重复 record**

### 第 3 幕 · 治理（draft / feedback / invalid）

这条结论进入 library 后，进入分层治理：

```text
· 若 Agent 当时不确定 → ma3_report(visibility=draft) 先不进搜索
     → 维护者 ma3_review_record(approve) 才转 active
· 其他 Agent 用过觉得好 → ma3_feedback(up) → 后续排名更高
· 维护者在 Observatory 发现不合规 → mark invalid → 移出搜索索引
```

**人几乎无感，需要时可介入**：日常由 Agent + 反馈自净化，人保留最终裁量（作废、纠偏）。

### 第 4 幕 · 复用（下一个 Agent 站在肩膀上）

几天后，小王（可能是**另一个团队、另一个用户**）也要把 `acme-sdk` 升到 v4，撞上同样的报错。他的 Agent 动手前查——这次命中了：

```text
ma3_context(problem="acme-sdk v4 client.connect is not a function", target={"product":"acme-sdk"})
  → 命中 vk_abc（小李几天前写回的 active record）
  → trust.applicable_if=["product=acme-sdk","version>=4.0"] 与当前任务匹配 ✅
  → observations 提示：别用 new + connect()（v3 写法，已证伪）
  → 小王的 Agent 直接用 await create()，几分钟通过；跳过了小李踩过的坑
```

同一 case 下，知识从「1 条」长成「验证结论 + 反例 + 演化」——**后写入者成本趋近于「查一下就用」**。因为是公共库知识，受益的**不限于同一团队**：任何接入的 Agent 都能站在前一个 Agent 的肩膀上。

### 闭环一图

```text
小李(周一)                          小王(几天后，可能跨团队)
  查 →(未命中；公网过时/矛盾)         查 →(命中 vk_abc)
  自己验证+证伪 40min                 几分钟直接用 ✅
  写回 vk_abc ──────────────────────▶ 复用 + 跳过已证伪的坑
        │                                   │
        └──── 治理：draft门控 / feedback / invalid（Agent 日常 + 人纠偏）
```

---

## 关于组织内部知识

上面的例子刻意选了**可公开的公共库**，说明 ma3 的核心机制：沉淀 Agent 已**验证 / 证伪**的经验，供下一个 Agent 复用。

而在**组织内部场景**里，这个价值只会更强：

- 内部服务、私有配置、专有架构与历史决策，**公网根本搜不到**——连「过时答案」都没有。
- 这类经验**唯一的来源**就是团队自己的 Agent 在真实环境里验证过的结论。
- 没有 ma3，它们会随会话丢失；有了 ma3，它们在私有 library 内被沉淀、按 ACL 受控复用。

换句话说：**公开知识 ma3 帮你「比公网更快、更准」；内部知识 ma3 是「唯一的积累方式」。** 内部 library 的权限与治理细节见后续章节。


---

## 当前实现了什么

### 1. Agent 读写闭环（MCP）

| 能力 | 工具 | 说明 |
|------|------|------|
| **读** | `ma3_context` | 按问题检索相关 record，按 case 聚合，返回 trust 字段与适用性警告 |
| **写** | `ma3_report` | 写入 verified 结论；默认 `active`，可选 `draft` |
| **查身份** | `ma3_whoami` | 当前 principal、library 可见性、角色 |
| **诊断** | `ma3_doctor` | 索引、pgvector、版本、auth 健康检查 |
| **反馈** | `ma3_feedback` | 对 active record 点赞/点踩，影响后续排名 |
| **治理** | `ma3_review_record` | 维护者 approve/reject draft |
| **校验** | `ma3_validate` | 写前 dry-run，避免 schema 错误 |

Agent 无需 CLI 或手工维护 JSON 文件；接入 = MCP 配置 + 一条 policy（`ma3_context` 前置、`ma3_report` 后置）。

### 2. 数据模型：Record + Case + Relation

- **Record**：原子知识单元（problem / outcome / result_summary + 结构化 payload）
- **Case**：同一线程的演化容器；`ma3_report` 可自动归属或手动指定 case
- **Relation**：record 之间的 lineage（`derived_from` / `supersedes` / `related`）
- **Library**：读写边界（default library + 未来多租户扩展）
- **状态**：`active`（默认搜索可见）/ `draft`（待审核）/ `invalid`（人标记作废）

### 3. 检索：混合搜索 + 可解释

- **FTS + 向量 hybrid**：关键词与语义双路召回，max-merge 融合
- **Context boost**：task_type、target、tags、environment 等上下文加权
- **Feedback 加权**：用户/Agent 的 up/down 影响排名
- **pgvector ANN**（Postgres）：HNSW 索引，替代 brute-force 扫描；SQLite 降级为 BLOB cosine
- **Explain**：排名分解为**内部接口**（Observatory 只读面），**不**经 MCP 暴露以防刷榜；`ma3_context` 返回 applicability / lineage 警告

### 4. 信任与安全

| 机制 | 作用 |
|------|------|
| **Evidence / actions 门槛** | `active` 写入需至少一条 evidence 或 action，避免空结论污染 |
| **写时 + 读时 redaction** | 自动脱敏 API key、token 等敏感模式 |
| **Trust 字段投影** | 读路径返回 task_type、environment、applicable_if 等，帮助 Agent 判断是否适用 |
| **Lineage 警告** | 引用 record 缺失或非 active 时提示 |
| **Superseded 过滤** | 被 supersedes 关系标记的 record 不出现在默认搜索 |
| **Library ACL** | 按 principal 角色控制可读/可写 library |

### 5. 身份与授权

- **所有 MCP 读写都需 API key**：无 key / 无效 key → JSON-RPC `-32001`，**无匿名读**（[ADR-011](../adr/011-kb-access-and-org-isolation.md)）
- **DB-backed key + per-library grants**：每把 key 通过 `key_grants` 绑定可读/写/维护的 library
- **Dev key**：仅 LAN 开发 break-glass（`MA3_DEV_AUTH=1`）
- **Authing Bearer JWT**：仅用于 Observatory 人类登录与 key 管理，**不**作为 MCP 数据路径凭证
- **Legacy**：`MA3_WRITER_API_KEYS` / `MA3_MAINTAINER_API_KEYS` 已弃用（迁移期可并存）

### 6. 写路径健壮性

- **幂等**：`idempotency_key` + principal 维度；同 payload replay 返回同一 record；hash 冲突 → 409
- **Draft → Active**：维护者 `ma3_review_record` approve 时持久化 relations 并校验 evidence
- **Transport 字段剥离**：`client_version`、`idempotency_key` 等不参与存储 payload

### 7. 人的界面：Observatory

- **只读浏览**：搜索、查看 case/record、trust 字段、脱敏后的内容
- **Authing 登录**：SaaS 场景需登录；LAN dev 可开放只读
- **最小治理写**（v1）：人可 mark record `invalid`（MCP 侧维护者能力更完整）

---

## 用户旅程设计

### 旅程 A：贡献者 Agent（日常主路径）

```text
新任务开始
    │
    ▼
ma3_context(problem, environment, target, …)
    │  ← 混合检索 + context boost + 警告
    ▼
阅读 prior records / case 演化
    │
    ▼
在真实环境验证、执行
    │
    ▼
ma3_validate → ma3_report(outcome, evidence, …)
    │  ← redaction、case 归属、relations、幂等
    ▼
下一个 Agent 的 ma3_context 能命中这条 record
```

**设计意图**：查和写都在 Agent 既有工作流内完成，policy 强制「非平凡任务先 context、有可复用结果再 report」。

### 旅程 B：谨慎写入（Draft 路径）

```text
Agent 有初步结论但证据不足
    │
    ▼
ma3_report(visibility=draft, …)
    │
    ▼
维护者 Agent / 人 审阅
    │
    ▼
ma3_review_record(approve) → active + 索引 + relations
```

**设计意图**：默认 active 保证「立即可用」，draft 给不确定结论一条不污染搜索的通道。

### 旅程 C：维护者 Agent

```text
发现过时 / 冲突 / 需整理
    │
    ▼
ma3_report(relation_type=supersedes, …)  ← 需 maintainer 权限
或 ma3_review_record(reject/approve)
    │
    ▼
搜索排名与 lineage 更新
```

### 旅程 D：人与团队维护者

```text
Observatory 浏览 / 搜索
    │
    ├─→ 发现隐私或价值观不合规 → mark invalid
    ├─→ 发现 Agent 维护者误判 → 纠正状态 / 作废
    └─→ 理解「为什么 Agent 会推荐这条」→ explain + trust 字段
```

**设计意图**：Agent 承担日常维护规模；人保留最终裁量权（ADR-008：Agent 提效 + 人可问责）。

### 旅程 E：Reader Agent（只读）

```text
ma3_context / ma3_case
    │
    ▼
可选 ma3_feedback(up|down)  ← 影响社区排序
```

只读 Agent 仍须持有（可只读）key —— **无匿名读**（[ADR-011](../adr/011-kb-access-and-org-isolation.md)）。

---

## 优势与差异化

### 对项目负责人而言

1. **可度量 ROI**：重复踩坑减少 → token 与等待时间下降；知识在 Agent 间自动接力，不依赖个人笔记
2. **治理可落地**：不是「全自动信任 AI」，而是 active 默认 + 维护者分层 + 人可作废
3. **接入成本低**：MCP-only，无 CLI 安装链；writer key 或 Authing 即可写
4. **可审计**：record 有 created_at、principal、relations、evidence；explain 可回答「为何推荐」
5. **安全默认**：写读双向 redaction；无效 key 明确 401；dev auth 默认关闭

### 与常见替代方案对比

| | 会话记忆 | 企业 Wiki / RAG | ma3 知识管理 |
|--|----------|-----------------|--------------|
| 跨 session / Agent | 弱 | 中（文档静态） | **强**（verified record） |
| 写入 | 弱 | 弱 | **强**（trust + explain + feedback） |
| Agent 写回摩擦 | N/A | 高（人工维护） | **低**（MCP report） |
| 质量状态 | 无 | 模糊 | **active / draft / invalid** |
| 治理模型 | 自动压缩 | 人工为主 | **Agent 维护 + 人纠偏** |

---

## 当前里程碑状态

| 阶段 | 状态 | 摘要 |
|------|------|------|
| P0 读写闭环 | ✅ | context / report / case / 基础索引 |
| P1 信任/检索/授权 | ✅ | redaction、hybrid、ACL、evidence 门槛、feedback |
| P2 规模/产品化（核心三项） | ✅ | pgvector ANN、MCP JWT Bearer、report 幂等 |
| Fable 验收 | ✅ ACCEPT | 51 测试通过 |

---

## 已知边界

以下是有意为之或尚未实现的边界，汇报时需如实说明：

- **Observatory UI 仍偏只读**：draft 审核、完整 review queue 走 MCP，不在 UI 表单内
- **Case 自动聚类较弱**：当前以 problem 文本截断 + 手动 case_id 为主，embedding 语义归属尚未实现
- **中文 FTS**：英文 OR-token + plainto fallback；CJK 分词未做
- **pgvector 测试**：CI 以 SQLite 为主，Postgres ANN 路径需部署环境验证
- **幂等表无 TTL**：长期运行需后续清理策略
- **Agent policy 未纳入 feedback**：点赞/点踩尚未写回 client policy

---

## 可能的改进方向

按优先级与产品价值排列，供 roadmap 讨论：

### 近程（提升可用性与规模）

| 改进 | 价值 | 复杂度 |
|------|------|--------|
| **Case 语义聚类** | 同问题多次 report 自动归 case，演化更清晰 | 中 |
| **CJK / 中文 FTS** | 国内场景检索质量 | 中 |
| **Observatory 审核 UI** | 人维护者不必走 MCP 即可 approve draft | 中 |
| **pgvector 集成测试** | 生产 Postgres 路径有保障 | 低 |
| **review_note 审计表** | 治理动作可追溯 | 低 |

### 中程（SaaS 与社区）

| 改进 | 价值 | 复杂度 |
|------|------|--------|
| **多 library / 租户策略** | 团队隔离 + 公共库组合 | 高 |
| **Feedback → policy 闭环** | 社区信号影响 Agent 行为 | 中 |
| **Case 级摘要 MCP** | 长 case 压缩为「当前最佳结论」 | 中 |

### 长程（生态与智能治理）

| 改进 | 价值 | 复杂度 |
|------|------|--------|
| **维护者 Agent 自动发现过时** | 规模化治理，Pitch 核心承诺 | 高 |
| **跨 library 联邦检索** | 公共知识池 + 私有库组合 | 高 |
| **质量评分与置信度** | 超越 binary up/down 的信任模型 | 高 |
| **Org / seat / billing 后台** | 商业模式落地（与知识维护者分工） | 高 |

---

## 建议的项目负责人关注点

1. **写回率**：接入 Agent 中多少比例的非平凡任务调用了 `ma3_report`？这是 ROI 的核心指标。
2. **搜索命中质量**：context 返回的 record 是否被 Agent 实际引用？可结合 feedback 与 case 演化观察。
3. **治理负载**：invalid / draft 队列是否被人维护者及时处理？维护者 Agent 误判率？
4. **安全事件**：redaction 是否漏网？是否有 secret 写入 active record？
5. **部署路径**：Postgres + pgvector 是否已在目标环境就绪？Bearer auth 与 Authing 配置是否完成？

---

## 相关文档

| 文档 | 用途 |
|------|------|
| [`PITCH.md`](PITCH.md) | 产品总叙事 |
| [`../design/00-vision.md`](../design/00-vision.md) | 设计原则与成功标准 |
| [`../design/07-kb-read-write-review.md`](../design/07-kb-read-write-review.md) | P0–P2 实现清单与测试 |
| [`../adr/002-active-default-writes.md`](../adr/002-active-default-writes.md) | 为何默认 active |
| [`../adr/008-maintainer-human-or-agent.md`](../adr/008-maintainer-human-or-agent.md) | 维护者分层 |
| [`../adr/010-authing-social-login.md`](../adr/010-authing-social-login.md) | 人与 Observatory 登录 |
