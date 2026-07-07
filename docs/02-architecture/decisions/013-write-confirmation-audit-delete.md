# ADR-013 — 写入确认、审计与删除

## 状态

Accepted（2026-07-03）

## 背景

[ADR-011](011-kb-access-and-org-isolation.md) / [ADR-012](012-billing-and-quotas.md) 已定访问与计费。产品讨论进一步明确：

- 用户默认对 **个人库 + 公共库** 均有写权限（同一把 key 可写两库），需避免 **写错库**
- **证实/证伪**已有经验 vs **补充/新增** 应区别对待
- 确认发生在 **写入前**（agent ↔ 用户），不是先写 draft 再统一审批
- **由 agent 自行判断** 是否需要找用户确认；服务端信任 agent 声明并 **审计留痕**
- 每个 library 须有 **可读 name**，供 agent 判断目标库
- 用户须能 **审计** 自己 agent 的写入，并 **硬删除** 自己的 record（含公共库）

[ADR-012](012-billing-and-quotas.md) 原「降级不删 record」须修订：改为 **owner 可硬删自己的 record**；系统不因欠费/降级删用户数据。

## 决策

### 1. 写入类型与判定树

`ma3_report` 按 **agent 声明的类型** 分流（服务端信任 agent，靠审计 + 删除兜底）：

| 类型 | 必填 | 目标库 | 确认 |
|------|------|--------|------|
| **证实 / 证伪** | `target_record_id` | **target 所在库**（服务端解析，agent 不可改） | 免确认 |
| **补充 / 新增** | `library_id`（或缺省→个人库） | agent 依据库 **name** 选择 | 见 §2 |

**证实/证伪 invariant**：

- 必须带 `target_record_id`；服务端校验 key 可读该 record
- 写入库 = `records.library_id` of target
- `confirmation = verify_direct`

### 2. 补充/新增：写入前确认

- **不产生** pending draft；未确认前 **不落库**
- Agent 在本地对话中向用户确认目标库（展示 **library name**）
- 用户同意后，agent 发带 `confirmation` 的写请求
- Agent **自行判断** 是否需要用户确认；两种合法值：
  - `user_confirmed` — 已与用户确认
  - `agent_judged` — agent 判断无需确认（如全自动场景）
- 服务端 **不** 强制 interactive/autonomous key mode；**如实审计** confirmation 类型

**缺省库**：补充/新增未指定 `library_id` 时，默认 **个人库**（fail-safe：误写落在无害侧）。

### 3. Library 命名（agent 判断依据）

- 每 library 必有 **`name`**（人类可读）
- 个人库默认名：`<display_name> 的个人库`
- 公共库：`Community Library`
- `ma3_context` / `ma3_whoami` / key grant 列表返回 `{library_id, name, visibility}`

### 4. 用户写入审计

- 新工具 **`ma3_list_my_writes`**：列出当前 principal 的写入历史
- 字段含：`created_at`, `key_id`, `library_id`, `library_name`, `record_id`, `confirmation`, `report_kind`（verify|supplement|new）
- Observatory **`/ui/writes/`** 只读页展示同一数据
- 每次 `ma3_report` 成功写入 append **`write_audit_log`**（见 design/10）

### 5. 硬删除（owner）与防误删（付费）

**默认（含 Free personal 与 public library）= 硬删，不可恢复：**

- 新工具 **`ma3_delete_record(record_id)`**
- **权限**：仅 **record 写入者 owner**（`principal_id` 匹配）可删；**含 public library**，无需 maintainer
- **效果**：从 `records`、搜索索引、embedding **物理移除** payload
- **Tombstone**：`record_deletions` 表保留 `{record_id, library_id, deleted_by, deleted_at}` — **内容删除，删除动作留痕**
- **下游**：**不级联删除**。`record_relations` 中指向已删 record 的行标记 `source_deleted=true`；读路径 `lineage_warnings` 提示「依据来源已被删除」
- **系统行为**：欠费/降级 **不** 自动删 record（与 owner 硬删区分）

**防误删（回收站 / 可恢复）= 付费功能：**

- 仅 **付费 org**（Team plan billing_account）可对其 **拥有的库**（org library）**开启** `deletion_protection`
- 开启后 `ma3_delete_record` 行为改为 **软删**：record 进回收站（`status=trashed`，移出搜索），保留 **retention window**（默认 30 天，可配）
- **`ma3_restore_record(record_id)`**：window 内 owner 或 org maintainer 可恢复
- window 到期或手动 purge → 转为上文 **硬删 + tombstone**
- **不开启 / 非付费 / personal / public 库**：无回收站，删除即硬删
- 本条 **细化** [pitch.md](../../01-product/pitch.md) 「人可恢复误删」承诺：**恢复能力是付费 org 的库级特权**，默认层删除不可逆

### 6. 修订 ADR-012

原「降级/欠费：不删 record」细化为：

- 欠费/降级：限写、限读配额，**不** 系统删数据  
- **用户** 可通过 `ma3_delete_record` 删除 **自己写的** record  
- **防误删** 是 Team plan 特权（`plans.deletion_protection`）；降级后已 trashed 的 record 按宽限策略 purge 或提示导出  

## 后果

### 正面

- 写错库：证实/证伪结构上锁定库；补充/新增默认个人库 + agent 确认
- 合规：审计 + 用户硬删 + tombstone
- 灵活：信任 agent 判断，不强制 key mode

### 负面

- Agent 可误分类或滥用 `agent_judged` — 依赖审计与用户删除
- 硬删后下游悬空引用 — 靠 lineage 警告缓解
- 公共库 owner 删 record 可能影响他人依赖 — 产品接受（用户对自己写入负责）
- 默认层「删即不可逆」对 Free/personal/public 用户偏严 — 以付费防误删对冲；误删风险由 agent 写前确认 + 审计缓解

### 关联

- [ADR-011](011-kb-access-and-org-isolation.md)、[ADR-012](012-billing-and-quotas.md)
- [writes-audit-and-deletion.md](../../03-backend/writes-audit-and-deletion.md)
