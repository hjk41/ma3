# ma3 触发机制实验计划（trigger 分支）

> 状态：草案 v1.0 ｜ 分支：`trigger` ｜ 负责人：待定 ｜ 创建日期：2026-07-08

## 0. 背景与问题陈述

ma3 是跨 Agent 的已验证知识网络（MCP server，挂载在 `/mcp`）。期望行为：

- **读**：Agent 在执行非平凡任务前调用 `ma3_context`，先查已验证经验；
- **写**：任务产出可复用的已验证结论后，调用 `ma3_feedback`（点赞/点踩）或 `ma3_report`（新增/verify/refute）。

当前唯一的触发手段是外置策略文件 `ma3-agent-policy.mdc`（`alwaysApply: true`，v1.5.1，见
`code/client/templates/ma3-agent-policy.mdc`），属于**纯提示词层**约束。实测约束力弱：
典型失败案例是让 Agent 安装 Factory Droid 时，Agent 直接走 Web 搜索，全程未调用
`ma3_context`，而知识库中已有相关记录。

此前 Fable 评审给出的 P0–P1 建议：

| 优先级 | 建议 | 说明 |
|---|---|---|
| P0 | 策略重排：FIRST-ACTION GATE | 把"先调 ma3_context"提到策略最前，并给出**客观触发条件**（web 搜索、安装软件、改配置等） |
| P0 | 发布门禁 T6 | 冷启动 + 中性提示词，验证 Agent 在第一条变更型 shell 命令前调用了 `ma3_context` |
| P1 | Cursor hooks | `beforeShellExecution` 单次拦截提醒 + `afterMCPExecution` 标记 context 已调用；fail-open |
| P1 | 服务端软信号 | 未先读就写时，在写入响应中返回 `context_skipped_hint` |
| P1 | 强化 MCP 工具描述 | 在 `tools/list` 的 description 里写明"何时必须调用" |

业界对比（Mem0 / OpenMemory / Membase）显示，可靠性从高到低的触发层级是：
**框架循环硬编码 > 确定性 hooks > 工具描述 > 会话启动注入 > 纯策略文本**。
本实验的目的就是在 ma3 的实际运行环境中，量化各层级（及其组合）的真实效果，
选出投入产出比最高的组合进入主干。

---

## 1. 实验目标与成功指标

### 1.1 目标

在 `trigger` 分支上，通过受控 A/B 实验回答三个问题：

1. 哪种机制（或组合）能最可靠地让 Agent **该读时读**（非平凡任务前调 `ma3_context`）？
2. 哪种机制能最可靠地让 Agent **该写时写**（产出已验证经验后调 `ma3_report`/`ma3_feedback`）？
3. 各机制的**误伤代价**是多少（平凡任务被强制读库、合法命令被 hook 拦截、Agent 被打断后跑偏）？

### 1.2 核心指标

| 指标 | 定义 | 目标值 | 测量方式 |
|---|---|---|---|
| **首动作读取率**（主指标） | 在触发型任务中，`ma3_context` 调用发生在**第一条变更型动作**（变更型 shell 命令 / 文件写入 / web 搜索）之前的会话占比 | ≥ 90%（基线预计 < 30%） | 服务端调用日志 + 会话转录时序分析 |
| **任务后写入率** | 产出可复用已验证结论的任务中，会话结束前调用了 `ma3_report` 或 `ma3_feedback` 的占比 | ≥ 80% | 同上 |
| **写入正确性** | 写入动作里选择正确（该 upvote 时 upvote 而非新建重复记录；verify/refute 带 `target_record_id`）的占比 | ≥ 80% | 人工评审 + 服务端记录去重检查 |
| **误触发率（读）** | 平凡任务（不应读库）中仍调用 `ma3_context` 的占比 | ≤ 20% | 转录分析 |
| **Hook 误拦截率** | hooks 实验组中，与 ma3 无关的合法 shell 命令被拦截/延迟的占比 | ≤ 5%，且拦截后任务完成率不下降 | hook 日志 |
| **任务完成率不回退** | 各实验组任务本身的完成率相对基线 | 下降 ≤ 5 个百分点 | 场景验收脚本（复用 `code/eval/scenarios/` 判分） |
| **KB 命中利用率** | KB 有匹配记录时，Agent 实际采用记录中方案的占比 | ≥ 70% | 转录分析 + `based_on_record_ids` |

### 1.3 统计口径

- 每个"实验组 × Agent × 提示词"组合至少跑 **5 次**独立会话（LLM 非确定性，单次结果无意义）。
- 首动作读取率按会话计；一个会话内多任务只计第一个触发点。
- "变更型动作"客观定义（与 FIRST-ACTION GATE 触发条件一致）：
  `curl/wget/pip/npm/apt/docker` 等安装下载、写系统或项目配置文件、web 搜索、`systemctl`/服务重启。
  纯只读命令（`ls`、`cat`、`git status`）不算。

---

## 2. 实验变体（Arms）

| # | 代号 | 机制层级 | 内容 | 预期 |
|---|---|---|---|---|
| A0 | `baseline` | 纯策略文本 | 现行 policy v1.5.1 原样安装，不做任何其他改动 | 对照组；预计首动作读取率低 |
| A1 | `policy-1.6` | 纯策略文本（重排） | 策略升级到 1.6.0：文件**开头第一节**即 FIRST-ACTION GATE，列出客观触发条件清单（web 搜索前 / 安装前 / 改配置前必须先调 `ma3_context`），其余章节顺延 | 验证"同样是提示词，位置和措辞是否有显著差异" |
| A2 | `tooldesc` | 工具描述 | 策略保持 v1.5.1 不动，只重写 MCP `tools/list` 中四个工具的 description：`ma3_context` 描述首句写 "MUST be called before web search / installing software / editing config on any non-trivial task"；`ma3_report`/`ma3_feedback` 描述写明结束前触发条件 | 验证工具描述这一层的独立贡献（对 droid/claude 等不读 Cursor rules 的运行时尤其重要） |
| A3 | `hooks` | 确定性 hooks | 策略保持 v1.5.1；新增 Cursor hooks：`beforeShellExecution` 检测变更型命令且本会话尚未调用 `ma3_context` 时，**deny 一次**并返回提示"先调用 ma3_context"；`afterMCPExecution` 检测到 `ma3_context` 调用后在会话状态文件打标记，之后放行所有命令。全程 fail-open（hook 自身报错时放行） | 验证确定性拦截的效果与误伤 |
| A4 | `policy+hooks` | 组合 | A1 的策略 1.6.0 + A3 的 hooks | 预期最佳组合；验证是否有叠加收益 |
| A5 | `soft-signal` | 服务端软信号 | 策略保持 v1.5.1；服务端改动：`ma3_report`/`ma3_feedback` 请求到达时，若该 principal 最近 N 分钟（默认 30）内无 `ma3_context` 调用，在响应 `structuredContent.server` 中追加 `context_skipped_hint`，**不拒绝写入**。同时在 `ma3_context` 响应中追加 `write_back_reminder`（提示任务结束前回写） | 主要作用于"写"侧与下一轮会话的习惯养成；对"读"侧首动作预计无直接效果 |
| A6 | `session-prompt`（可选） | 会话启动注入 | 利用 MCP prompts 能力（或等价方案：Cursor 的 `beforeSubmitPrompt` hook 注入一行系统提醒），在会话第一条用户消息前注入"本环境接入 ma3，非平凡任务先调 ma3_context"的简短提示 | 对标 Mem0/OpenMemory 的 session-start 注入；仅在 A1–A4 结果不理想或需要覆盖非 Cursor 运行时时执行 |
| B0 | `local-skill-mcp` | 本地 skill + 本地 MCP | 与 A0 相同机制层级（纯 policy），但 **MCP 端点**与 **skill sync 源**均为 `http://127.0.0.1:8000`（本机 ma3），API key 用 dev/eval key；对照 A0（远程 ma3.io）以分离「远程 SaaS 路径 vs 本地部署路径」对触发率的影响 | 验证本地 skill bundle 版本/延迟/可达性是否改变 Agent 读写的及时性 |

补充说明：

- A2 与 A1 刻意分离，因为 droid exec、claude code 不读 `~/.cursor/rules/`，工具描述是它们能收到的**唯一**服务端可控提示词，独立测量其贡献对多运行时策略至关重要。
- A3 的 hooks 仅覆盖 Cursor；droid/claude 的对应机制（如 claude code 的 hooks）如时间允许在第 3 周补测，不阻塞主实验。
- 所有组的"写"侧行为都会被记录，但 A5 是唯一直接干预写侧的组。

---

## 3. 测试矩阵

### 3.1 Agent 运行时

| 运行时 | 接入方式 | 策略可达性 | Hooks 可达性 |
|---|---|---|---|
| Cursor agent（CLI/IDE） | MCP + `~/.cursor/rules/ma3-agent-policy.mdc` | ✅ | ✅（`~/.cursor/hooks.json`） |
| droid exec（Factory） | MCP + AGENTS.md / droid 配置合并策略 | ⚠️ 需按 droid 方式合并 | ❌（无等价 hook，A3/A4 跳过） |
| claude code | MCP + `CLAUDE.md` 合并策略 | ⚠️ 需合并 | ⚠️（有 hooks 机制，第 3 周选测） |

复用 `code/eval/scenarios/` 中已有的 `claude-deepseek-byok`、`droid-deepseek-byok` 场景配置作为运行时接入参考。

### 3.2 提示词（任务类别）

| 编号 | 类别 | 示例提示词（中性，不提 ma3） | 期望行为 | 检验点 |
|---|---|---|---|---|
| P1 | 安装任务（触发型） | "帮我在这台机器上安装 Factory Droid CLI" | 先调 `ma3_context`，命中预埋记录，按记录方案执行，结束后 upvote | 读 + 写（feedback）|
| P2 | 排障任务，KB 有命中（触发型） | "docker compose 起来的服务容器间互相 ping 不通，帮我修一下"（KB 预埋 compose 网络修复记录，可复用 `compose-network-fix` 场景） | 先读、采用记录方案、结束后 upvote | 读 + KB 利用率 + 写 |
| P3 | 排障任务，KB 无命中（触发型） | 一个 KB 中确认不存在的新问题（如特定版本 nginx 配置报错） | 先读（查空）、自行解决、结束后 `ma3_report report_kind:"new"` | 读 + 写（report）|
| P4 | 平凡问题（**不应触发读**） | "Python 里怎么反转一个列表？" | 直接回答，**不**调用 `ma3_context`，不写 | 误触发率 |
| P5 | 配置修改（触发型，hook 敏感） | "前端 npm 安装很慢：查 ma3 后只改 workspace/.npmrc 为国内 registry，并 upvote"（场景目录 `trigger-p5`；验收文件含 `registry.npmmirror.com`；**不要**改 `/etc` 或全局 npm） | 先读命中预埋记录、按记录改项目 `.npmrc`、结束后 upvote；hooks 组可验证拦截→读→放行 | 读 + KB 利用率 + 写（feedback）+ hook 行为 |
| P6 | 纯只读操作（**不应被 hook 拦**） | "看一下这个项目的目录结构，讲讲代码组织" | 正常执行，hook 不拦截 | Hook 误拦截率 |

### 3.3 组合规模

- 全量矩阵：7 组（A0–A6）× 3 运行时 × 6 提示词 × 5 次 ≈ 630 会话，不现实。
- **裁剪原则**：
  1. 第一优先级：**Cursor agent 全矩阵**（7 × 6 × 5 = 210 会话，可用 `code/eval/orchestrator/` 批量驱动）；
  2. droid / claude 只跑 A0、A2、A5（它们收不到 Cursor 策略与 hooks），提示词取 P1、P2、P4（3 × 3 × 3 × 5 = 135 会话）；
  3. A6 仅在阶段二决策时按需追加。

---

## 4. 单次运行流程（Runbook）

每次运行是一个独立会话，步骤如下：

### 4.1 准备（每次运行前）

1. **干净会话**：新开 Agent 会话，不带任何历史上下文；Cursor 用 `cursor-agent` 新会话，droid 用 `droid exec` 新进程，claude 用 `claude -p` 新进程。
2. **环境重置**：
   - hooks 组：清空会话状态标记文件（如 `~/.ma3/session-state/`）；
   - 确认 `~/.ma3/ma3-client.json` 版本与实验组要求一致；
   - 目标机使用可回滚的容器/快照（复用 `code/eval/` 的容器化场景环境）。
3. **预埋 KB 记录**：向测试库写入本轮提示词对应的记录（P1 埋 droid 安装记录、P2 埋 compose 网络修复记录、P5 埋「`workspace/.npmrc` → `registry.npmmirror.com`」记录），并记录其 `record_id` 供事后核对。Eval 种子经 `seed_trigger_kb.sh` **publish 为 active**（buffered 整句 ILIKE 无法支撑改写查询）。P3 需确认 KB 检索该问题返回空。
4. **登记运行元数据**：实验组、运行时、提示词编号、时间戳、KB 预埋 record_id，写入 `code/eval/results/trigger/runs.csv`。

### 4.2 执行

5. 发送**中性用户提示词**（表 3.2 原文，严禁出现 "ma3"、"知识库"、"先查一下" 等引导词）。
6. 不干预，让 Agent 自主运行至任务结束（或超时 15 分钟）。
7. hooks 组若发生拦截，记录拦截时刻、Agent 的后续反应（是否转向调 `ma3_context`、是否绕过、是否卡死）。

### 4.3 判定

| 判定项 | Pass 条件 |
|---|---|
| 读-时序 | `ma3_context` 的调用时间戳早于第一条变更型动作（P4/P6 反向：未调用才算 Pass） |
| 读-质量 | `ma3_context` 参数包含真实的 `problem`/`target`/`task_type`（非空壳调用） |
| KB 利用 | 预埋记录被返回且 Agent 实际采用其方案（转录中可见引用） |
| 写-发生 | 会话结束前有 `ma3_feedback` 或 `ma3_report` 调用 |
| 写-正确 | P1/P2 应为 upvote 而非新建重复记录；P3 应为 `report_kind:"new"` 且通过 `ma3_validate` |
| 任务完成 | 场景本身的验收脚本通过（复用 eval 场景判分逻辑） |
| Hook 无误伤 | P6 全程无拦截；其他提示词中非变更型命令无拦截 |

每项记 0/1，汇总进 `runs.csv`；争议样本（如 Agent 调了 `ma3_context` 但参数敷衍）由人工复核并在备注列说明。

---

## 5. 观测与埋点（Instrumentation）

判定依赖三个互补数据源，**服务端日志为准，转录用于确定时序**：

### 5.1 服务端工具调用日志（需在 trigger 分支新增）

在 `code/server/app/` 的 MCP 分发层添加结构化调用日志（建议独立表或 JSONL）：

```json
{"ts": "...", "principal_id": "...", "tool": "ma3_context", "session_hint": "...",
 "args_digest": {"task_type": "...", "target": "..."}, "result": "ok",
 "returned_record_ids": ["rec_..."]}
```

- 字段最小集：时间戳、principal、工具名、成功/失败、返回的 record_id 列表（读）或写入的 record_id（写）。
- **不落盘完整参数**（可能含用户环境细节），只存摘要字段。
- 该日志同时是 A5（软信号）"最近 N 分钟内有无 context 调用"的判断依据，一举两得。

### 5.2 会话转录分析

- Cursor agent：会话 JSONL 转录（agent transcripts 目录），可精确还原工具调用顺序、shell 命令内容与时间戳；写解析脚本 `code/eval/scripts/analyze_trigger_run.py` 自动提取"第一条变更型动作时刻"与"ma3_context 调用时刻"并比较。
- droid exec / claude code：使用各自的 `--output-format json` / 会话日志能力落盘转录；解析器按运行时适配。

### 5.3 Hook 日志

hooks 脚本自身向 `~/.ma3/logs/hooks.jsonl` 追加每次触发记录（命令、判定结果 allow/deny、耗时），用于计算误拦截率和验证 fail-open（hook 抛异常时必须写 `"result": "fail_open_allow"` 并放行）。

### 5.4 汇总

`code/eval/scripts/aggregate_trigger_results.py` 读取 `runs.csv` + 三类日志，输出各组指标表（1.2 节全部指标），结果存 `code/eval/results/trigger/summary.md`。

---

## 6. 分阶段推进

### 第 1 周：速赢层（提示词与描述）

| 事项 | 产出 |
|---|---|
| 冻结基线：跑 A0 全提示词，确立对照数据 | 基线指标表 |
| 编写 policy 1.6.0（FIRST-ACTION GATE 置顶 + 客观触发条件清单） | `code/client/templates/ma3-agent-policy.mdc` 1.6.0 草案 |
| 重写四个 MCP 工具 description | 服务端 `tools/list` 改动 |
| 搭建埋点：服务端调用日志 + 转录解析脚本 | 5.1 / 5.2 的代码 |
| 跑 A1、A2（Cursor 全提示词；droid/claude 跑 A2） | 第 1 周指标对比 |
| 把 T6 冷启动检查写入发布门禁草案 | `docs/08-quality/release-checklist.md` 增补草案 |

**第 1 周决策点**：若 A1 或 A2 已使首动作读取率 ≥ 90%，hooks 降级为可选加固，第 2 周重心转向写侧。

### 第 2 周：确定性层（hooks）

| 事项 | 产出 |
|---|---|
| 实现 Cursor hooks（`beforeShellExecution` deny-once + `afterMCPExecution` 标记），fail-open，含单元测试 | `code/client/templates/hooks/` 脚本 + `hooks.json` 模板 |
| 跑 A3、A4（Cursor 全提示词），重点观测 P6 误拦截与拦截后 Agent 行为 | 第 2 周指标对比 |
| 分析拦截后跑偏案例（Agent 被 deny 后放弃任务/绕过等） | 案例清单与提示语改进 |

### 第 3 周：服务端层与收尾

| 事项 | 产出 |
|---|---|
| 实现 A5 软信号（`context_skipped_hint` + `write_back_reminder`），含服务端测试 | `code/server/app/` 改动 + `code/server/tests/` 用例 |
| 跑 A5（三个运行时），观测写侧指标变化 | 第 3 周指标 |
| （视 A1–A4 结果）选测 A6 会话注入、claude code hooks | 可选补充数据 |
| 汇总报告：各组全指标对比、推荐组合、上线建议 | `code/eval/results/trigger/summary.md` + 本文档"结论"章节 |
| 将胜出组合整理为可合入 main 的 PR 序列 | PR 清单 |

---

## 7. 风险与伦理约束

| 风险 | 约束 / 缓解 |
|---|---|
| Hook 误拦截阻塞用户正常工作 | 所有 hook **fail-open**：脚本异常、超时（> 2s）、状态文件缺失一律放行；deny 仅一次，之后同会话不再拦截 |
| 用户被强制走 ma3 流程 | 保留 opt-out：用户在提示词中明确拒绝（"不用查知识库"）时策略与 hooks 均放行；hooks 模板提供环境变量开关（如 `MA3_HOOKS_DISABLED=1`） |
| 服务端硬拒绝造成数据丢失 | 实验期**不对写路径做任何硬拦截**：`context_skipped_hint` 只是响应中的提示字段，写入照常成功；未来若考虑硬门禁，需另立实验并有回滚开关 |
| 提示词污染（实验提示词泄露 ma3 意图） | 中性提示词经第二人复核，禁止出现引导词；判定人不参与提示词编写（简单盲评） |
| 预埋记录污染生产 KB | 实验使用独立测试库/独立 principal，或实验结束后按登记的 record_id 清理 |
| deny 提示语诱导 Agent 敷衍调用（空壳 `ma3_context`） | 判定含"读-质量"项；deny 提示语只说明要求，不给可复制的参数模板 |
| 隐私 | 调用日志只存参数摘要与 record_id，不存完整用户参数与 shell 命令原文 |

---

## 8. trigger 分支交付物清单

| 类型 | 路径 | 说明 |
|---|---|---|
| 新增 | `docs/09-engineering/experiments/trigger-mechanisms.md` | 本文档（含最终结论章节） |
| 修改 | `code/client/templates/ma3-agent-policy.mdc` | 1.6.0：FIRST-ACTION GATE 置顶 + 客观触发条件（A1/A4 用） |
| 修改 | `code/server/app/` MCP 工具注册处 | 四个工具 description 重写（A2）；`context_skipped_hint` / `write_back_reminder` 软信号（A5） |
| 新增 | `code/server/app/` 调用日志模块 | 结构化工具调用日志（5.1），软信号复用同一数据 |
| 新增 | `code/server/tests/test_trigger_signals.py` | 软信号与调用日志的单元测试 |
| 新增 | `code/client/templates/hooks/hooks.json` + `ma3_gate.py`（或 .sh） | Cursor hooks 模板（A3/A4），fail-open，含 opt-out 开关 |
| 新增 | `code/eval/scenarios/trigger-*/` | P1–P6 提示词场景定义与 KB 预埋数据 |
| 新增 | `code/eval/scripts/analyze_trigger_run.py` | 转录解析：提取工具调用与变更型动作时序 |
| 新增 | `code/eval/scripts/aggregate_trigger_results.py` | 指标汇总 |
| 新增 | `code/eval/results/trigger/runs.csv` + `summary.md` | 原始运行台账与汇总报告 |
| 修改 | `docs/08-quality/release-checklist.md` | 新增 T6 冷启动门禁：中性提示词下首条变更型 shell 前必须出现 `ma3_context` 调用 |
| 修改 | `docs/05-agent/policy-and-client-sync.md` | 记录 1.6.0 策略变更与 hooks 分发方式 |
| 修改 | `docs/09-engineering/changelog.md` | 实验与结论摘要 |

---

## 9. 结论（实验完成后回填）

- 各组指标对比表：待回填
- 推荐组合与理由：待回填
- 合入 main 的 PR 序列：待回填
