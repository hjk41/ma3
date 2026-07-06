# 11 — MCP 错误契约：所有错误必须可自纠

> **ADR**：[ADR-014](../adr/014-mcp-error-self-correction.md)  
> **状态**：实现完成（2026-07-03）  
> **真源**：本文 + ADR-014；实现见 `code/server/app/api/routes_mcp.py`

---

## 1. 目标与约束

| 项 | 说明 |
|----|------|
| **核心约束** | **每个 MCP 错误都必须在 `error.message` 里携带足以让 Agent 自纠的信息** |
| 单一可见字段 | `error.message` 是唯一可假定被模型读到的字段（宿主常丢弃 `error.data`） |
| 结构化副本 | `error.data` 保留机器可读诊断，但**不是** Agent 自纠的唯一载体 |
| 逐字段 | 校验错误必须逐字段说明 missing / unexpected / 类型错误 |
| 定向提示 | 识别到常见误用（如 payload 套进 `arguments`）时给出针对性修正建议 |
| 不泄密 | message 不含 secrets、堆栈、SQL、原始异常链 |

### 1.1 背景

MCP 宿主（Cursor / Claude Code / Codex 等）只把 JSON-RPC `error.message` 传给模型；`error.data` 往往被丢弃。这与 `structuredContent` 不可见是**同一类**宿主行为。

**实证**：评测中 Claude 把 `ma3_report` payload 误套进 `arguments`（照抄 `ma3_validate` 的 `{tool_name, arguments}` 信封），只读到 `-32602 "Invalid params"`，连试 6 次相同错误后放弃、未写回。修复后同场景 Agent 一次写回成功。

---

## 2. 错误分类与契约

所有 `tools/call` 及传输层错误统一经 `routes_mcp.py::_jsonrpc_error` 构造。

| JSON-RPC code | 触发 | message 必含 |
|---------------|------|-------------|
| `-32700` Parse error | body 非 JSON | "request body is not valid JSON" |
| `-32600` Invalid Request | JSON-RPC 信封字段错误 | 折叠后的字段级摘要 |
| `-32601` Method not found | 未知 method | 未知 method 名 + 支持列表 |
| `-32601`（映射自 404） | 未知工具 / record / case 不存在 | `HTTPException.detail` |
| `-32602` Invalid params | `params.name` 缺失 | "requires a string params.name" |
| `-32602` Invalid params | `params.arguments` 非对象 | "must be a JSON object" |
| `-32602` Invalid params | **payload 校验失败** | 逐字段 missing/unexpected + 定向提示（见 §3） |
| `-32602` Invalid params | 工具内 `ValueError` | `Invalid params: {原因}` |
| `-32001`（映射自 401） | 凭证无效/撤销/过期 | "check your X-API-Key with the ma3 administrator" |
| `-32001`（映射自 403） | 权限不足 | `HTTPException.detail` |
| `-32029`（映射自 429） | 限流 | `HTTPException.detail` |
| `-32000`（其它 5xx/HTTPException） | 兜底 | `HTTPException.detail` |

**规则**：

- HTTPException 路径：`str(detail)` 即 message；detail 文案必须本身可操作。
- 非 HTTPException 路径**必须**显式把 detail 折叠进 message。

---

## 3. 校验错误摘要器

`routes_mcp.py::_summarize_validation_errors(tool_name, errors)` 把 Pydantic `errors()` 折叠成单条可操作 message。

### 3.1 算法

```text
输入: tool_name, pydantic_errors[]
分桶:
  missing  ← type ∈ {missing, value_error.missing}         → loc
  extra    ← type ∈ {extra_forbidden, value_error.extra}   → loc
  other    ← 其余                                            → "loc: msg"
构造:
  prefix = "Invalid params for {tool_name}"
  段落 = [missing 段, extra 段, other 段]
  message = prefix + ": " + 段落
定向提示:
  IF tool_name ∉ {ma3_validate} AND "arguments" ∈ extra:
      + "Hint: {tool_name} takes a FLAT payload (the fields directly),
         NOT {tool_name, arguments} like ma3_validate. Move the inner
         fields up to the top level and retry."
  ELSE:
      + "Fix these fields and retry; ma3_validate offers a dry-run check."
```

### 3.2 示例

**信封混淆**：

```
-32602: Invalid params for ma3_report: missing required field(s):
problem, outcome, result_summary; unexpected field(s): arguments.
Hint: ma3_report takes a FLAT payload (the fields directly), NOT
{tool_name, arguments} like ma3_validate. Move the inner fields up
to the top level and retry.
```

**缺字段**：

```
-32602: Invalid params for ma3_report: missing required field(s):
outcome, result_summary. Fix these fields and retry; ma3_validate
offers a dry-run check.
```

`error.data` 仍并存 `{tool_name, validation_errors[], schema_hint}` 供程序化客户端。

---

## 4. `error.data` 结构（保留）

| 字段 | 出现于 | 内容 |
|------|--------|------|
| `validation_errors` | 校验类 -32602 | Pydantic `errors()` 原始列表 |
| `schema_hint` | 校验类 -32602 | 指向 `tools/list` inputSchema + `ma3_validate` |
| `tool_name` | 校验类 -32602 | 目标工具 |
| `status_code` | 由 HTTP 映射 | 原 HTTP 状态码 |
| `detail` | name/arguments/ValueError | 原因串 |

> `data` 是**冗余增强**，不是自纠的必要条件。删除 `data` 后 Agent 仍应能只凭 message 纠错。

---

## 5. 安全约束

- message / data **不得**包含：API key 明文、私钥、订阅 URL、数据库连接串、SQL、Python 堆栈、原始异常 `repr`。
- 工具内异常一律转 `HTTPException(detail=<安全文案>)` 或 `ValueError(<安全文案>)`。
- `unknown tool` / `not found` 类 message 只回显调用者已提供的标识符，不泄露其它库/记录的存在性（与 [10](10-write-audit-and-delete.md) 的 existence-oracle 约束一致）。

---

## 6. 测试要求（回归门禁）

`tests/integration/test_mcp_integration.py`：

| 测试 | 断言 |
|------|------|
| report 缺字段 | -32602 且 `message` 含 `ma3_report` + `missing required field` |
| `test_ma3_report_envelope_confusion_message` | message 含 `unexpected field` + `arguments` + `FLAT payload` |
| `test_method_not_found_message_lists_methods` | -32601 且 message 含 `tools/call` |
| 既有 -32001 用例 | 凭证/权限错误码稳定 |

**新增错误路径的验收标准**：必须有一条断言检查 `error.message`（而非仅 `error.data`）含可操作信息。

---

## 7. 映射文件

| 文件 | 职责 |
|------|------|
| `code/server/app/api/routes_mcp.py` | `_jsonrpc_error`、`_summarize_validation_errors` |
| `code/server/app/models/mcp.py` | `McpToolValidationError` |
| `code/server/app/services/mcp_tool_service.py` | 工具内以 `HTTPException`/`ValueError` 抛出安全文案 |
| `code/server/tests/integration/test_mcp_integration.py` | 错误 message 回归 |
