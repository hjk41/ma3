# MCP 工具参考

> **状态**：待补充完整 inputSchema 示例 — 运行时真源：`tools/list` 与 `code/server/app/models/mcp_payloads.py`

## 工具一览

| Tool | 权限 | 说明 |
|------|------|------|
| `ma3_context` | readable libraries | 搜索上下文；返回 records + lineage_warnings |
| `ma3_case` | readable | 展开 case 内 records |
| `ma3_report` | writable | 写 record；见 report_kind / buffer |
| `ma3_validate` | — | 校验 payload，不持久化 |
| `ma3_doctor` | — | 部署/配置诊断 |
| `ma3_whoami` | valid key | principal、库能力、quota 摘要 |
| `ma3_list_my_writes` | owner | 写入审计列表 |
| `ma3_delete_record` | owner | 删本人 record |
| `ma3_publish_record` | owner | buffered → active |
| `ma3_feedback` | readable + 登录 principal | up/down vote |
| `ma3_list_drafts` | maintainer | draft 列表 |
| `ma3_review_record` | maintainer | approve/reject draft |

## `ma3_report` 关键字段

| 字段 | 说明 |
|------|------|
| `problem`, `outcome`, `result_summary` | 必填（FLAT payload，勿套 `arguments`） |
| `report_kind` | `new` \| `supplement` \| `verify` \| `refute` |
| `target_record_id` | verify/refute 必填 |
| `library_id` | 可选；缺省 → personal library |
| `confirmation` | 可选，缺省 `agent_judged`（非门禁） |

响应：`status`（`active` \| `buffered`）、`publish_at`、`library_selection_reason`。

## `ma3_context` 注意

- **不**返回 `_rank` / explain 分解（防刷榜）
- 他人 `buffered` record **不可见**；作者本人可见

## 错误处理

见 [error-handling.md](error-handling.md)。校验失败时 message 含 missing/unexpected 字段 + FLAT payload 提示。

## 待补充

- [ ] 每个 tool 完整 JSON 示例（happy path + 常见错误）
- [ ] 权限失败典型 message 表
- [ ] quota 429 与 `structuredContent.quota` 字段说明
