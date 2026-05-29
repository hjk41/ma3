# agentmemory 接口对比与 ma3 可借鉴点

## 背景

本文记录对 `/root/code/agentmemory` 与 `/root/code/ma3` 对外接口的代码阅读结论，重点关注 REST、MCP、CLI、插件/技能等 agent-facing surface。目的不是要求 ma3 复制 agentmemory，而是把可借鉴的设计点沉淀下来，供后续接口演进、设计评审和路线规划参考。

## 总体结论

- **agentmemory** 是本地优先的 agent 记忆运行时：接口面很宽，覆盖 session、observation、memory、lesson、slot、action、lease、signal、checkpoint、mesh 等大量底层能力；通过 hooks 自动采集，通过本地 stdio MCP shim 和 REST API 服务不同 agent。
- **ma3** 是中心化 verified knowledge network：接口更少、更工作流化，强调可验证记录、case/thread、library 权限、write-back 审核、search explain 和远程 MCP。
- ma3 已经在 **schema 单一真源、结构化 MCP 错误、远程 MCP、权限隔离、case 聚合** 上比 agentmemory 更稳；agentmemory 则在 **本地集成、resources/prompts、hooks、渐进披露、多 agent 协作原语** 上有可参考空间。

## 接口差异概览

| 维度 | agentmemory | ma3 |
|---|---|---|
| 定位 | 本地/私有 persistent memory，自动捕获 agent 会话和工具上下文 | 远端/集中式 verified knowledge network，搜索已有经验并写回可复用结论 |
| 技术栈 | TypeScript + iii-engine；所有操作通过 `registerFunction` / `registerTrigger` / `sdk.trigger` | FastAPI + Pydantic；SQLite dev，PostgreSQL prod |
| REST 面 | 约 121 个 `/agentmemory/*` endpoint，能力很细 | 约 56 个 endpoint；v2 核心是 `/v2/agent/context`、`/v2/agent/report`、cases/stats/doctor |
| MCP 面 | 51 tools；默认 core 8，`AGENTMEMORY_TOOLS=all` 暴露全量；还有 resources/prompts | 7 个远程 MCP tools：`ma3_context`、`ma3_report`、`ma3_case`、`ma3_search_explain`、`ma3_validate`、`ma3_doctor`、`ma3_whoami` |
| MCP transport | 主要靠本地 stdio shim `@agentmemory/mcp`，可代理本地 server，也可 fallback 到 InMemoryKV 7 tools | 原生 remote MCP：`POST /mcp` JSON-RPC，支持 initialize/tools/list/tools/call/ping/batch/notification |
| schema/校验 | `tools-registry.ts` 手写 inputSchema，`server.ts` switch 手写校验，有 schema/runtime 漂移风险 | `models/mcp_payloads.py` 是单一真源；Pydantic 同时生成 schema 和 runtime validate；`extra=forbid`；有 `ma3_validate` dry-run |
| MCP 返回 | 多数 tool 返回 JSON 字符串 text content | 返回 text summary + `structuredContent`，更适合 agent/客户端直接解析 |
| 权限 | 单一可选 `AGENTMEMORY_SECRET` bearer，更偏本机私有服务 | admin key + library token + reader/writer/admin role + public/private library |
| 数据模型 | session/observation/memory/lesson/slot/action/signal/checkpoint 等 agent 运行态记忆 | library/record/case/relation/feedback，强调审核、可见性和 case 演化 |
| agent 集成 | hooks、plugin、skills、npx MCP shim、viewer、connect/doctor | `/agents.md`、install scripts、client manifest、CLI fallback、remote MCP |

## ma3 可借鉴点

### 1. 增加 MCP resources 与 prompts

agentmemory 暴露了 6 个 MCP resources 和 3 个 prompts，例如状态、project profile、latest memories、handoff prompt 等。ma3 当前 remote MCP 只暴露 tools。

可考虑为 ma3 增加只读 resources：

- `ma3://status`：服务、版本、library 可见性、索引状态摘要。
- `ma3://case/{case_id}`：case timeline 的资源化读取。
- `ma3://library/{library_id}/overview`：library 记录数、draft 数、case 覆盖率、质量指标。
- `ma3://topics`：产品、组件、tags、problem_family 分布。

可考虑增加 prompts：

- `ma3_context_for_task`：把用户任务包装成推荐的 `ma3_context` 调用思路。
- `ma3_report_after_fix`：引导 agent 在任务完成后形成高质量 `ma3_report`。
- `ma3_search_explain_review`：帮助维护者分析某次搜索结果为什么命中/漏召回。

价值：降低 agent 使用门槛，让支持 MCP resources/prompts 的客户端不必只靠 tool list 理解 ma3。

### 2. 提供轻量本地 MCP shim 与优雅 fallback

agentmemory 的 `@agentmemory/mcp` 会先探测本地 server，可用时代理完整接口，不可用时 fallback 到本地 InMemoryKV 的 7 个基础 tools，并给出清晰 stderr 诊断。

ma3 目前主推 remote MCP，这是正确方向；但可补一个轻量 stdio shim：

- remote `/mcp` 可用时，直接代理 JSON-RPC。
- remote 不可用时，仍提供 `ma3_doctor` / `warmup` / config diagnosis。
- 对 write-back 可选提供本地 queued draft，但必须明确标记未持久化，避免用户误以为已写入 ma3。

价值：改善不支持 remote MCP、网络受限、运行时尚未 reload MCP 配置的客户端体验。

### 3. 借鉴 hooks 自动采集，但进入 draft/candidate 流程

agentmemory 通过 hooks 自动捕获 session、prompt、tool use、tool output、文件触碰等上下文。ma3 不应直接把这些自动采集内容变成 verified record，但可以借鉴为：

- agent 任务结束后自动生成 `ma3_report` draft。
- 对可复用结论、失败路径、环境条件、证据进行候选抽取。
- 进入 redaction + review + promote 流程后再成为 active record。

建议落点：新增“candidate observation / draft report”概念，而不是把运行态日志塞进 `records`。

价值：减少 agent 忘记 write-back 的概率，同时保持 ma3 verified knowledge 的质量边界。

### 4. 支持 token budget 与渐进披露

agentmemory 的 search/context 有 `format`、`token_budget`、compact/full/narrative 等思路。ma3 MCP 目前已有 `include_full_json`，但还可以更精细：

- `response_format`: `compact | full | narrative`。
- `token_budget`: 限制返回正文长度。
- `expand_case_ids` / `expand_record_ids`: 第一跳只给摘要，第二跳按需展开。
- 对 `ma3_context` 默认保持 compact，把大字段放进 `structuredContent` 或后续 `ma3_case`。

价值：降低大 case / 大 library 下的上下文噪声和 token 成本。

### 5. 评估引入多 agent 协作原语

agentmemory 有 actions、leases、signals、checkpoints 等多 agent 协作能力。ma3 如果未来要支撑团队级 agent 协作，可参考但不应直接混入 verified record 模型。

可选方向：

- `case_actions`：围绕 case 的待办、验证、复现、清理任务。
- `case_leases`：避免多个 agent 同时处理同一 curation/action。
- `case_checkpoints`：记录外部条件门槛，例如等待部署、等待用户确认、等待指标稳定。
- `case_signals`：agent 对 case 维护者或其他 agent 的轻量通知。

价值：让 ma3 从“知识库”演进到“围绕知识演化的协作面”，但应保持与 `records` 的边界。

### 6. 继续增强安装、诊断和自修复体验

agentmemory CLI 的 `connect/status/doctor/remove` 更产品化。ma3 已有 `warmup`、`v2-doctor`、`ma3_doctor`，可继续增强：

- 明确检测 remote MCP 是否已被当前 agent runtime 加载，而不只是配置文件已写入。
- 对 auth、library visibility、role、server version、client manifest version 给出 actionable fix。
- 对常见错误输出下一步命令，例如 restart/reload MCP、换 reader/writer token、刷新 client。
- 在 `/client/manifest.json` 中暴露 remote MCP 配置建议和最低 client/skill 版本。

价值：减少“配置看似成功但 MCP tool 不出现”的调试成本。

## agentmemory 反向可借鉴 ma3 的点

虽然本文主要服务 ma3，但对比中也能看出 ma3 当前做得更好的接口原则：

- MCP payload model 是 schema 与 runtime validator 的单一真源。
- 每个 MCP payload `extra=forbid`，拼写错误能明确报字段。
- `-32602` 带 `error.data.validation_errors`，而不是只有模糊的 Invalid params。
- `ma3_validate` 作为 dry-run 工具，避免 agent 反复消耗写 quota 或产生脏数据。
- MCP tool 返回 `structuredContent`，便于客户端机器解析。
- remote MCP `/mcp` 遵循 JSON-RPC transport，支持 batch 和 notification。

这些原则后续 ma3 继续扩 MCP tools 时应保持不变。

## 建议优先级

1. **短期**：增加 MCP resources/prompts；扩展 `ma3_context` 的 compact/full/token budget；增强 doctor/warmup 的 MCP runtime 诊断。
2. **中期**：做 lightweight stdio MCP shim；把 write-back 自动草稿接入 agent hooks/skills，但默认进入 draft/candidate。
3. **长期**：围绕 case 引入 actions/leases/checkpoints/signals 等协作原语，并通过 stats/UI 暴露其状态。

## 设计边界

ma3 的核心差异化是 verified knowledge，而不是本地全量会话日志。借鉴 agentmemory 时建议遵守：

- 自动采集内容默认不是 active record。
- 新协作原语不应破坏 record/case/relation 的清晰边界。
- MCP schema 继续以 Pydantic payload model 为唯一真源。
- 任何新增 write path 都应保留 redaction、auth、review、op log 和 metrics。
