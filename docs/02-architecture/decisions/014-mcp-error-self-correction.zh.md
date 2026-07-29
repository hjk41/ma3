# ADR-014 — MCP 错误必须可自纠

## 状态

Accepted（2026-07-03）

## 背景

ma3 v1 的 Agent 面仅有 MCP（[ADR-003](003-mcp-only-agent-surface.md)）。Agent 是**唯一**消费者，且大多在**无人值守**下运行——它读到什么错误、就凭什么错误决定下一步。

一次真实评测暴露了系统性缺陷：

- 服务端**已经**把结构化诊断（`validation_errors`、`schema_hint`、字段路径）放进 JSON-RPC `error.data`。
- 但**MCP 宿主（Cursor / Claude Code 等)只把 `error.message` 交给模型**，`error.data` 往往被丢弃——这与更早发现的 `structuredContent` 不可见是**同一类**宿主行为。
- 结果：Claude 把 `ma3_report` 的 payload 误套进 `arguments`（照抄 `ma3_validate` 的 `{tool_name, arguments}` 信封），收到 `-32602 "Invalid params"`（无字段信息），**连试 6 次相同错误**后放弃、未写回。

即"信息在协议里存在，但不在 Agent 能看到的位置"。

## 决策

**约束（不变式）**：**所有 MCP 错误都必须在 `error.message` 中携带足以让 Agent 自行纠正的信息。**

具体：

1. `error.message` 是**唯一**可假定被模型读到的字段。凡是 Agent 自纠所需的信息（缺哪个字段、多了什么、期望什么形状、如何取得权限），**必须**出现在 `message` 里。
2. `error.data` 仍保留结构化副本（`validation_errors`、`status_code`、`schema_hint` 等），供能读 data 的程序化客户端使用——但**不得**作为 Agent 自纠的**唯一**载体。
3. 校验类错误（`-32602` / `-32600`）的 message 必须**逐字段**说明 missing / unexpected / 类型错误，并在识别到常见误用（如把工具 payload 套进 `arguments`）时给出**定向提示**。
4. message **不得**泄露 secrets、内部堆栈、SQL 或原始异常链。

详见 [error-handling.md](../../05-agent/error-handling.md)。

## 后果

### 正面

- 无人值守 Agent 能一次纠错，减少"重试相同错误直至放弃/不写回"。
- 提升写回率与知识库沉淀质量（Agent 不再因 `ma3_report` 报错而丢弃可复用结论）。
- 错误契约可测试化、可回归。

### 负面

- message 变长、部分内容与 `data` 重复。
- 需要一处集中构造 message（`routes_mcp.py`），新增错误路径时须遵守约束（靠测试兜底）。

### 关联

- [ADR-003](003-mcp-only-agent-surface.md)：MCP 是唯一 Agent 面 → 错误面即产品面。
- 复用 `structuredContent` 可见性修复的同一结论：把关键信息放进宿主一定会展示的字段。
