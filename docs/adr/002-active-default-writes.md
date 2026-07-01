# ADR-002 — ma3_report 默认 active

## 状态

Accepted（2026-07-01）

## 背景

Q5 在 draft / active / library 级配置间选择。Verified knowledge（P1）与 immediate visibility 存在张力。

## 决策

- **`ma3_report` 默认写入 `status=active`**，所有 library 类型一致
- **`draft` 仅当** payload 显式 `visibility=draft`（或未来 library 级强制策略，v1 不默认启用）
- MCP 响应必须含 `status: "active"`，**不**默认 `requires_manual_review`
- **Hook / agentmemory 候选**仍与 Record 分离，**不得**自动 active（遵守 Q2/P1）

## 后果

### 正面

- Agent 写回后 `ma3_context` 立即可见，闭环简单
- 与当前 LAN 上 `immediate_visibility` 行为一致，迁移成本低

### 负面

- 误写、低质量 record 直接进入搜索索引
- 需依赖 ranking、Observatory 人工 `invalid`、以及 agent policy 中的 validate/redaction

### 缓解（v1 必须实现，对齐 Pitch §维护分层）

1. Search ranking 对低信号 record 降权（explain 可扩展）
2. **维护者 Agent** 日常标记疑似过时条目（可审计）
3. **人 — 维护者** 在 Observatory **纠偏** Agent 维护者，并清除隐私/价值观不合规内容
4. Policy 强制写前 dry-run + 自动脱敏
5. `ma3_list_drafts` / `ma3_review_record` 供维护者 Agent 使用；人不阻塞默认写路径

### 关联

- Q5, P1, P6
- MCP `ma3_report` 响应 schema
