# ADR-006 — Hook 候选默认本地，不上送 ma3 直至显式 promote

## 状态

Accepted（2026-07-01）

## 背景

Hook 在 agent 生命周期中自动采集 session、prompt、tool use 等上下文（见旧 repo `docs/agentmemory-mechanism-lessons.md`）。若与 `ma3_report` 默认 active 混为同一路径，verified knowledge 会被 raw trace 污染。

产品负责人确认：hook 候选 **不得** 自动 active；并进一步明确 **默认存储在本地**，而非 ma3 服务端。

## 决策

### 1. 存储位置

| 层级 | 默认位置 | 内容 |
|------|----------|------|
| **Hook 候选** | **本地**（agent 机器） | session 快照、截断后的 tool trace、draft report 模板、fingerprint 去重状态 |
| **Verified record** | **ma3 服务端** | 经 `ma3_report` 或人审 promote 后的 case/record |

Hook **默认不向 ma3 写入**任何 searchable 数据。

### 2. 上送 ma3 的唯一路径

本地 candidate → 显式动作 → 服务端：

1. Agent 调用 **`ma3_report`**（默认 `active`，见 ADR-002）
2. **维护者**（人/Agent）在 Observatory / review 流程 **promote** 本地或服务端 draft
3. 可选：payload 显式 `visibility=draft` 上送 ma3 草稿队列（**非** hook 自动触发）

无上述步骤 → **不进 ma3 索引**。

### 3. Hook 实现边界（v1 可不 ship，边界先定）

- Hook 脚本挂在 **Cursor/Codex 等 agent runtime** 的 hook 目录，**不**依赖 ma3 CLI / `install.sh`（ADR-003）
- 本地存储：轻量 JSON 或 SQLite，带 **TTL / session 级清理**
- Hook 侧：**截断**（如 tool output 8k）、**脱敏**、**去重**、**timeout + try/catch**，失败不阻塞 agent
- **禁止**：每个 `post-tool-use` 自动 POST 到 ma3；禁止 hook 静默创建 `active` record

### 4. 与 ADR-002 / ADR-003 的关系

```text
Hook（本地 draft candidate）
        │
        │  agent 整理 + ma3_validate + ma3_report
        ▼
ma3 服务端（active 默认）

Hook ──✗──► ma3 active   （禁止）
Hook ──✗──► ma3 默认上送  （禁止）
```

## 后果

### 正面

- 敏感 raw trace 默认不出本机
- 高频 hook 不压 ma3 网络与索引
- 与 P1（verified over raw）、Q2=A 一致
- 删除 CLI 后仍可在 agent IDE 侧集成 hook

### 负面

- 多机协作时本地 candidate 不共享（需靠 `ma3_report` 写回后，**其它 Agent** 在 library 内可见）
- 若要做「跨 session 本地检索」，需自管本地索引（非 ma3 v1 core）

### v1 范围

- **ADR 约束立即生效**（设计边界）
- **Hook 实现为可选模块**，不阻塞 v1 core（MCP + Observatory + SaaS auth）
- 若实现，落点：`code/client/hooks/`（示例脚本 + 本地 store 规范），**非** server 必需组件

## 关联

- ADR-002（ma3_report 默认 active）
- ADR-003（MCP + policy，无 CLI）
- Q2=A（verified over raw）
- 旧 repo `docs/agentmemory-mechanism-lessons.md` §1
