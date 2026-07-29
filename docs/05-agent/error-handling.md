# 11 — MCP Error Contract: Every Error Must Be Self-Correctable

> Chinese version: [error-handling.zh.md](error-handling.zh.md)

> **ADR**: [ADR-014](../02-architecture/decisions/014-mcp-error-self-correction.md)  
> **Status**: implementation complete (2026-07-03)  
> **Source of truth**: this doc + ADR-014; implementation in `code/server/app/api/routes_mcp.py`

---

## 1. Goals and Constraints

| Item | Description |
|----|------|
| **Core constraint** | **Every MCP error must carry enough information in `error.message` for the Agent to self-correct** |
| Single visible field | `error.message` is the only field we can assume the model will see (hosts often drop `error.data`) |
| Structured copy | `error.data` keeps machine-readable diagnostics, but is **not** the sole vehicle for Agent self-correction |
| Field-by-field | Validation errors must state missing / unexpected / type errors per field |
| Targeted hints | When a common misuse is detected (e.g. payload nested inside `arguments`), give a targeted correction suggestion |
| No leaks | messages must not contain secrets, stack traces, SQL, or raw exception chains |

### 1.1 Background

MCP hosts (Cursor / Claude Code / Codex, etc.) only pass the JSON-RPC `error.message` to the model; `error.data` is often dropped. This is the **same class** of host behavior as `structuredContent` being invisible.

**Evidence**: in evaluations, Claude mistakenly nested the `ma3_report` payload inside `arguments` (copying the `{tool_name, arguments}` envelope of `ma3_validate`), only saw `-32602 "Invalid params"`, retried the same error 6 times, then gave up without writing back. After the fix, the Agent succeeded in a single write-back in the same scenario.

---

## 2. Error Classification and Contract

All `tools/call` and transport-layer errors are uniformly constructed via `routes_mcp.py::_jsonrpc_error`.

| JSON-RPC code | Trigger | message must contain |
|---------------|------|-------------|
| `-32700` Parse error | body is not JSON | "request body is not valid JSON" |
| `-32600` Invalid Request | JSON-RPC envelope field error | folded field-level summary |
| `-32601` Method not found | unknown method | unknown method name + supported list |
| `-32601` (mapped from 404) | unknown tool / record / case not found | `HTTPException.detail` |
| `-32602` Invalid params | `params.name` missing | "requires a string params.name" |
| `-32602` Invalid params | `params.arguments` is not an object | "must be a JSON object" |
| `-32602` Invalid params | **payload validation failed** | per-field missing/unexpected + targeted hint (see §3) |
| `-32602` Invalid params | in-tool `ValueError` | `Invalid params: {reason}` |
| `-32001` (mapped from 401) | credential invalid/revoked/expired | "check your X-API-Key with the ma3 administrator" |
| `-32001` (mapped from 403) | insufficient permission | `HTTPException.detail` |
| `-32029` (mapped from 429) | rate limited | `HTTPException.detail` |
| `-32000` (other 5xx/HTTPException) | fallback | `HTTPException.detail` |

**Rules**:

- HTTPException path: `str(detail)` is the message; detail copy must itself be actionable.
- Non-HTTPException paths **must** explicitly fold detail into the message.

---

## 3. Validation Error Summarizer

`routes_mcp.py::_summarize_validation_errors(tool_name, errors)` folds Pydantic `errors()` into a single actionable message.

### 3.1 Algorithm

```text
Input: tool_name, pydantic_errors[]
Bucketing:
  missing  ← type ∈ {missing, value_error.missing}         → loc
  extra    ← type ∈ {extra_forbidden, value_error.extra}   → loc
  other    ← the rest                                       → "loc: msg"
Construction:
  prefix = "Invalid params for {tool_name}"
  segments = [missing segment, extra segment, other segment]
  message = prefix + ": " + segments
Targeted hint:
  IF tool_name ∉ {ma3_validate} AND "arguments" ∈ extra:
      + "Hint: {tool_name} takes a FLAT payload (the fields directly),
         NOT {tool_name, arguments} like ma3_validate. Move the inner
         fields up to the top level and retry."
  ELSE:
      + "Fix these fields and retry; ma3_validate offers a dry-run check."
```

### 3.2 Examples

**Envelope confusion**:

```
-32602: Invalid params for ma3_report: missing required field(s):
problem, outcome, result_summary; unexpected field(s): arguments.
Hint: ma3_report takes a FLAT payload (the fields directly), NOT
{tool_name, arguments} like ma3_validate. Move the inner fields up
to the top level and retry.
```

**Missing fields**:

```
-32602: Invalid params for ma3_report: missing required field(s):
outcome, result_summary. Fix these fields and retry; ma3_validate
offers a dry-run check.
```

`error.data` still coexists with `{tool_name, validation_errors[], schema_hint}` for programmatic clients.

---

## 4. `error.data` Structure (retained)

| Field | Appears in | Content |
|------|--------|------|
| `validation_errors` | validation-class -32602 | raw list from Pydantic `errors()` |
| `schema_hint` | validation-class -32602 | points to `tools/list` inputSchema + `ma3_validate` |
| `tool_name` | validation-class -32602 | target tool |
| `status_code` | mapped from HTTP | original HTTP status code |
| `detail` | name/arguments/ValueError | reason string |

> `data` is a **redundant enhancement**, not a prerequisite for self-correction. Even with `data` removed, the Agent should still be able to correct itself from the message alone.

---

## 5. Security Constraints

- message / data must **not** contain: plaintext API keys, private keys, subscription URLs, database connection strings, SQL, Python stack traces, raw exception `repr`.
- Exceptions inside tools are always converted to `HTTPException(detail=<safe copy>)` or `ValueError(<safe copy>)`.
- `unknown tool` / `not found` class messages only echo identifiers the caller already provided, and do not reveal the existence of other libraries/records (consistent with the existence-oracle constraint in [writes-audit-and-deletion.md](../03-backend/writes-audit-and-deletion.md)).

---

## 6. Test Requirements (regression gate)

`tests/integration/test_mcp_integration.py`:

| Test | Assertion |
|------|------|
| report missing fields | -32602 and `message` contains `ma3_report` + `missing required field` |
| `test_ma3_report_envelope_confusion_message` | message contains `unexpected field` + `arguments` + `FLAT payload` |
| `test_method_not_found_message_lists_methods` | -32601 and message contains `tools/call` |
| existing -32001 cases | credential/permission error codes stable |

**Acceptance criterion for new error paths**: there must be at least one assertion checking that `error.message` (not just `error.data`) contains actionable information.

---

## 7. File Mapping

| File | Responsibility |
|------|------|
| `code/server/app/api/routes_mcp.py` | `_jsonrpc_error`, `_summarize_validation_errors` |
| `code/server/app/models/mcp.py` | `McpToolValidationError` |
| `code/server/app/services/mcp_tool_service.py` | tools raise safe copy via `HTTPException`/`ValueError` |
| `code/server/tests/integration/test_mcp_integration.py` | error message regression |
