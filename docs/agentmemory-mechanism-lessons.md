# agentmemory 机制研究与 ma3 可借鉴点

## 背景

本文补充 `docs/agentmemory-interface-lessons.md`：前一篇偏接口面，本文偏运行机制和产品机制。代码阅读对象是 `/root/code/agentmemory`，重点参考：

- `src/functions/observe.ts`
- `src/functions/compress*.ts`
- `src/functions/search.ts`
- `src/state/search-index.ts`
- `src/state/hybrid-search.ts`
- `src/functions/context.ts`
- `src/functions/summarize.ts`
- `src/functions/consolidation-pipeline.ts`
- `src/functions/lessons.ts`
- `src/functions/slots.ts`
- `src/functions/actions.ts`
- `src/functions/leases.ts`
- `src/functions/checkpoints.ts`
- `src/functions/signals.ts`
- `src/functions/audit.ts`
- plugin hook scripts under `plugin/scripts/`

## 机制总览

agentmemory 的核心不是单个 search API，而是一条后台记忆流水线：

```text
agent hooks
  -> REST /agentmemory/observe
  -> mem::observe
  -> dedup + privacy redaction + raw observation
  -> synthetic compression by default, optional LLM compression
  -> BM25 / vector / graph index
  -> session summary
  -> project context / lessons / slots
  -> consolidation / reflection / decay / eviction
  -> future SessionStart / PreCompact / MCP search 注入或检索
```

它有三个重要特征：

1. **capture 自动化**：agent 不需要主动写记忆，hooks 会持续捕获工具调用、prompt、失败、session 生命周期。
2. **retrieval 渐进化**：先返回 compact hit，再按需 expand；context 注入受 token budget 约束。
3. **memory 生命周期化**：观察、总结、长期记忆、lesson、insight、slot、decay、forget、audit 形成闭环。

ma3 的定位不同：ma3 是 verified knowledge network，不应该照搬“全量运行日志记忆”。但 agentmemory 的若干机制可以作为 ma3 的外围能力或 workflow 能力。

## 值得借鉴的机制

### 1. Hook 驱动的自动候选写回

agentmemory 的 hooks 做得很实用：

- `post-tool-use` 捕获工具名、输入、输出，输出有 8k 截断。
- `prompt-submit` 捕获用户 prompt。
- `session-start` 注册 session，并可选注入 context。
- `pre-compact` 在压缩前补一次 context。
- 所有 hook 都有 `AbortSignal.timeout()` 和 try/catch，失败不阻塞 agent。
- `sdk-guard` 避免 agent-sdk 子进程触发递归 hook。

ma3 可借鉴为 **自动 draft/report candidate**：

- agent 任务结束时自动汇总“问题、环境、采取步骤、最终结果、证据”。
- 默认只生成 draft 或 candidate，不直接成为 active record。
- 用户或 reviewer 确认后再调用 `/v2/agent/report` 或 promote。
- 保留超时、截断、递归保护、best-effort 设计。

不建议：把每一次 tool use 直接写入 ma3 record。那会污染 verified knowledge。

### 2. 写入前的隐私处理、截断和去重

`mem::observe` 会：

- 对 payload 做 privacy redaction：`<private>...</private>`、token、password、API key、Bearer、GitHub token、JWT 等。
- 对工具输出在 hook 层截断。
- 用 `DedupMap` 对短时间重复 tool input 去重。

ma3 已有 redaction_mode，但可以加强到 report/draft 生成链路：

- 在 client/skill/hook 侧先截断和 redaction，服务端再次 redaction。
- 对重复 report candidate 做 fingerprint 去重，避免 Stop hook 重复写草稿。
- 对敏感字段输出“发现了什么类型敏感值”的确认提示，而不是只悄悄替换。

### 3. Synthetic compression 默认、LLM compression 可选

agentmemory 早期每个 observation 都可 LLM 压缩，后来改成默认 **zero-LLM synthetic compression**，只有设置 `AGENTMEMORY_AUTO_COMPRESS=true` 才走 LLM。原因是 hooks 高频触发，LLM 压缩会大量消耗 token。

ma3 可借鉴这个成本边界：

- 自动候选 report 先用规则/模板生成结构化草稿。
- LLM 只用于低频、高价值环节：最终摘要、case 聚合、质量分析、搜索 explain 总结。
- 对任何自动 LLM 行为都加显式 feature flag 和成本提示。

### 4. Compact + expand 的渐进披露

`mem::smart-search` 的机制很适合 agent：

- 第一跳返回 compact：`obsId/sessionId/title/type/score/timestamp`。
- 第二跳用 `expandIds` 拉全文 observation。
- 这样避免一次性塞入大段历史。

ma3 已有 `include_full_json` 和 `ma3_case`，但可以进一步产品化：

- `ma3_context` 默认只返回 compact case/record 摘要。
- 增加 `expand_record_ids` 或 `expand_case_ids` 参数。
- 对 MCP result 保持 text summary 简短，完整结构放 `structuredContent`。
- 加 `token_budget`，在服务端做 hard cap。

### 5. 多路检索融合和结果多样性

agentmemory 的 `HybridSearch` 使用：

- BM25：关键词、stem、synonym、prefix match、CJK segmentation。
- Vector：embedding cosine。
- Graph：实体命中和图扩展。
- RRF 融合。
- session diversification：默认每个 session 最多 3 条，避免一个 session 淹没结果。

ma3 v2 已有 PostgreSQL/FTS/embedding/case/relation 排名路径，可借鉴的不是具体实现，而是几个策略：

- 对不同来源的候选做 rank-level fusion，而不只拼一个线性分数。
- 对同一 case/library/source 做 diversity cap，避免单一 case 霸屏。
- 对 explain 输出展示每个候选来自哪些 stream：text/vector/case/relation/feedback。
- 对中文或 CJK query 明确做分词策略，不要只依赖英文 tokenizer。

### 6. Context assembler 作为独立层

`mem::context` 不是直接 search 返回，而是组装：

- pinned slots
- project profile
- lessons
- recent session summaries
- high-importance observations
- token budget
- XML wrapper

ma3 可借鉴为 `ma3_context` 的内部架构：

- 把“检索候选”和“agent-ready context 组装”拆开。
- context 组装器明确处理预算、排序、警告、冲突、适用条件和来源 ID。
- 对用户/团队/library 级的固定说明或偏好，使用类似 pinned slots 的 profile，而不是每次让 agent 重写在 prompt 里。

### 7. Slots：可编辑、可 pin 的长期上下文

agentmemory slots 是介于配置和记忆之间的结构：

- global/project 两种 scope。
- `persona`、`user_preferences`、`tool_guidelines`、`project_context`、`guidance`、`pending_items` 等默认槽。
- pinned slots 会进入 context。
- 每个 slot 有 sizeLimit、readOnly、audit。
- `slot-reflect` 会从近期 observations 中补 pending items、files touched、session patterns。

ma3 可以借鉴成更适合 ma3 的概念：

- `library_profile`：library 级固定说明、适用范围、写入规范、敏感信息策略。
- `case_notes`：case 级 pending follow-up、canonical guidance、known pitfalls。
- `agent_guidance`：某个 token/library 对 agent 的使用偏好。

注意：slots 应该是辅助上下文，不应替代 verified records。

### 8. Lesson 的强化、衰减、软删除

agentmemory lessons 使用 content fingerprint 去重：

- 重复保存同一 lesson 会 strengthen，而不是产生新记录。
- confidence 随 reinforcement 上升。
- 定时 decay sweep 会降低长期未强化 lesson 的 confidence，低 confidence 且无 reinforcement 的 lesson 会 soft-delete。

ma3 已有 feedback、verification_level、risk_level，可借鉴成 **usefulness 动态层**：

- 每次 search result 被引用、report 关联、用户标记 helpful，都增强 usefulness。
- 长期未使用且低验证等级的 record/case 进入 stale/quality action，而非直接删除。
- 对重复 report 用 fingerprint 合并或提示“strengthen existing record/case”。

### 9. 记忆演化、supersession 和 provenance

agentmemory 的 `remember/evolve/relations/verify` 有这些点：

- 新 memory 与旧 memory 相似度高时，旧版 `isLatest=false`，新版 supersedes 旧版。
- relation 记录 `supersedes/contradicts/derives/related`。
- `verify` 能从 memory 追到 source observations 和 session。

ma3 已有 case/record/relation，更适合把这套机制做强：

- report 写入时如果与已有 record 高相似，应进入 same-case evolution，而不是平铺记录。
- `supersedes/conflicts_with/invalid_under` 应进入 ranking 和 warning。
- `ma3_case` / UI 应突出 canonical、superseded、conflicting、invalid-under 条件。
- `ma3_verify` 可作为未来 tool：解释某条 record 的证据、关系、feedback、review 历史。

### 10. Actions / leases / checkpoints / signals：协作控制面

agentmemory 有一套多 agent 协作原语：

- action graph：requires/unlocks/gated_by/conflicts_with。
- frontier：根据优先级、年龄、解锁数量、租约计算下一步。
- lease：一个 action 同时只允许一个 agent 处理，TTL 可 renew/release。
- checkpoint：等待 CI、审批、部署、外部条件。
- signal：agent 间消息和 thread。

ma3 不需要照搬为通用任务系统，但非常适合用于 **case curation workflow**：

- `case_action`: 补证据、复测、迁移、合并重复、处理冲突、提升 canonical。
- `case_lease`: 防止两个 agent 同时改同一个 case/record。
- `case_checkpoint`: 等用户确认、等部署完成、等指标稳定。
- `case_signal`: 给维护者或下一位 agent 的短消息。

这会让 ma3 从“知识检索”进一步支持“知识治理”。

### 11. 诊断与 self-healing

agentmemory 的 `mem::diagnose` 会检查：

- active action 是否没有 lease。
- blocked action 的依赖是否都已完成。
- expired lease/sentinel/sketch/signal。
- abandoned session。

`mem::heal` 可修复部分可修复问题。

ma3 可借鉴到：

- `/v2/doctor` 不只检查数据库和索引，也检查知识图健康：orphan records、case 无 canonical、relation 指向不存在、draft 积压、低质量高访问 record、冲突未处理。
- 提供 dry-run repair/quality-action，不自动破坏数据。
- UI 中把这些作为 Quality Actions。

### 12. Audit policy 明文化

agentmemory 在 `audit.ts` 中把删除审计策略写得很明确：结构性删除必须 audit，bulk sweep 可以一条 audit 批量记录。虽然它的具体实现还有可改进空间，但“把审计政策写在代码旁边并测试覆盖”的做法值得保留。

ma3 已有 op_log 和 review workflow，可进一步明确：

- 每个 write path、promote/reject/delete、case assignment override、relation mutation 都要有 op log 或 audit row。
- 批量质量修复必须有 dry-run 和 audit summary。
- MCP write tool 的 result 返回 audit/op id，便于 agent 引用。

### 13. Health、metrics、索引保护

agentmemory 的机制包括：

- health monitor 定时写最新快照：内存、CPU、event loop lag、KV probe、worker 状态。
- LLM provider circuit breaker + fallback chain。
- BM25/vector index debounce 持久化。
- vector dimension mismatch 时拒绝加载，避免静默召回损坏。

ma3 可借鉴：

- 对 embedding index 增加 schema/version/dimension/model identity 检查。
- `/v2/doctor` 明确显示 index model、dimension、record_count vs indexed_count、最后 backfill 时间。
- 对外部 LLM/embedding provider 加 circuit breaker 和 fallback 状态。
- 对 op_log/metrics 加“近一小时错误类型”摘要。

## 不建议 ma3 照搬的机制

1. **不要把本地全量 tool log 作为 ma3 active knowledge**。ma3 的核心是 verified/reviewed/reusable record。
2. **不要扩成 50+ MCP tools**。ma3 当前 7 个高层 tools 更适合 agent；新增能力优先聚合到 workflow，而不是暴露很多底层 CRUD。
3. **不要用手写 MCP schema**。ma3 当前 Pydantic 单一真源比 agentmemory 更安全，必须保持。
4. **不要默认每个 hook 调 LLM**。agentmemory 已经把这件事改为 opt-in；ma3 更应控制成本。
5. **不要把 actions/leases/signals 做成 ma3 的主模型**。它们应服务 case curation，而不是取代 record/case/relation。
6. **不要在 ma3 prod 回到本地 KV/SQLite 思维**。agentmemory 是本机 runtime，ma3 prod 应坚持 PostgreSQL-first。

## 建议落地优先级

### P0：低风险、直接提升体验

- 给 `ma3_context` 增加 compact/full/token_budget/expand 机制。
- 在 `/v2/doctor` 增加 index identity、embedding dimension、record/index parity、recent error summary。
- 在 client/skill 的 write-back 草稿生成中加入 truncation、redaction、fingerprint 去重。

### P1：增强知识质量闭环

- 增加 record/case usefulness 信号：引用、关联 report、helpful feedback 强化；长期未用进入 stale/quality action。
- 增加 `ma3_verify` 或在 `ma3_case` 中强化 provenance：证据、review、relations、feedback、supersession。
- 增加 library/case profile 或 pinned notes，进入 `ma3_context` 组装。

### P2：自动化候选写回

- 设计 hook/skill 侧自动 draft report，不直接 active。
- 结合 review/promote 流程进入 ma3。
- 对敏感内容必须 user confirmation 或保留 `redaction_mode=auto` 默认。

### P3：case curation 协作层

- 引入 case-scoped actions、leases、checkpoints、signals。
- UI 暴露 frontier/quality actions。
- MCP 提供少量聚合工具，而不是大量 CRUD 工具。

## 一句话结论

agentmemory 最值得 ma3 借鉴的不是“记忆数据库”本身，而是 **自动候选生成、渐进披露、上下文组装、使用反馈强化、生命周期治理、诊断自修复、协作控制面**。这些机制如果套在 ma3 的 case/record/review 模型外层，会增强 ma3；如果直接照搬全量本地日志和大量底层工具，则会削弱 ma3 的 verified knowledge 定位。
