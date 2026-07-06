# Agent Policy 与 Client Sync

> 操作步骤真源：`code/client/agent-onboarding.md`（HTTP 可 curl）  
> Policy 真源：`code/client/templates/ma3-agent-policy.mdc`

## Bootstrap 流程

```text
1. 人：/ui/keys/ 创建 API key
2. curl ma3-client.env.example → ~/.ma3/ma3-client.env（编辑 MA3_BASE_URL）
3. curl sync 脚本 → ~/.ma3/bin + ~/.ma3/lib
4. sync_ma3_client.sh sync → ~/.ma3/ma3-client.json + policy + mcp-tools 缓存
5. 配置 IDE MCP（X-API-Key）+ 复制 policy 到 runtime
```

## Scheme B 版本字段

| 字段 | 含义 |
|------|------|
| `service_version` | 服务端 release |
| `skill_bundle_version` | policy + onboarding 集合 |
| `sync_tooling_version` | sync 脚本/lib |
| `tool_schema_version` | MCP payload 代际 |

Agent 每次 MCP 调用上报：`client_version`（对齐 skill_bundle）、`tool_schema_version`。

本地真相源：`~/.ma3/ma3-client.json`。

## MCP 响应升级标志

| 标志 | Agent 动作 |
|------|------------|
| `policy_refresh_required` | sync + 复制 policy |
| `mcp_reload_required` | sync + IDE reload MCP |
| `client_update_required` | sync + reload；**停止写路径** |

## Policy 要点（Agent 行为）

- 非 trivial 任务前：`ma3_context`
- 有可复用结论后：`ma3_report`（可省略 `confirmation`）
- 写社区库：显式 `library_id: "lib_default"`
- 收到 `status=buffered`：告知用户缓冲期与门户提前发布
- rank-based downvote：仅对排在最终选用 record **之前**且判定错误的 hit downvote
- 校验失败：读 `error.message` 自纠；`ma3_validate` dry-run

## HTTP Bundle

| 路径 | 内容 |
|------|------|
| `GET /client/manifest.json` | 版本 + sha256 + urls |
| `GET /client/templates/ma3-agent-policy.mdc` | policy |
| `GET /client/mcp-tools.json` | tools 快照 |
| `GET /client/scripts/sync_ma3_client.{sh,py}` | sync 入口 |

## 待补充

- [ ] policy 版本 bump 与发版 checklist 联动
- [ ] 各 Agent IDE 的 MCP 配置示例（Cursor / Claude / Codex）
- [ ] offline /  air-gapped 部署的 bundle 镜像方式
