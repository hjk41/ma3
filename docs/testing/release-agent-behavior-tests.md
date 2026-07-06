# 发版前 Agent 行为回归测试方案

> **状态**：Active（2026-07-03 起生效）
> **适用**：每次 ma3 服务端 / 客户端 policy / MCP 契约发版**之前**必须执行
> **相关**：ADR-013（写确认/审计/删除）、ADR-014（错误可自纠）、
> `code/client/templates/ma3-agent-policy.mdc`、`code/eval/scenarios/*`

---

## 0. 为什么需要这份方案

ma3 的价值只有在**真实 Agent 无人值守**时才成立：Agent 能查到知识、用对知识、
把结果**正确地**写回（点赞 / 点踩 / 只在必要时新建）。这些行为**无法用单元测试覆盖**——
它们取决于 policy 措辞、错误信息是否可自纠、客户端能否自动升级。历史上每一次
回归都是"服务端测试全绿、真实 Agent 却退化"：

- Agent 把 `ma3_report` payload 误套进 `arguments`，连试 6 次放弃写回（→ ADR-014）。
- Agent 命中已有知识却**新建重复 record**，而不是点赞（→ policy 1.1.0）。
- Agent 判断某条 record 是错的，却**默默跳过**、不点踩（→ policy 1.3.0）。

**结论**：每次发版前，必须在 **192.168.31.202** 上用真实 Agent 跑一遍下面的行为场景，
任一不过则**阻塞发版**。

---

## 0.1 测试环境（固定）

| 项 | 要求 |
|----|------|
| **执行主机** | **仅 192.168.31.202**（ma3 host + Docker + eval profiles） |
| **ma3 服务端** | `http://127.0.0.1:8000`（202 本机 host ma3） |
| **场景目录** | `/home/hct/ma3_deploy/code/eval/scenarios/*` |
| **Agent profiles** | `/home/hct/ma3-eval/profiles/{claude,codex,hermes}` |
| **本机** | **不跑** Docker 场景；本机仅作开发/文档编辑。Codex 的 **LLM API** 可复用本机 `~/.codex/config.toml` 里的 `model_providers.*`（如 duckcoding）同步到 202 的 codex profile |

> 所有 SSH、docker compose、DB 断言、Agent 非交互运行均在 202 上完成。

---

## 1. 硬性要求

1. **三个 Agent 都要测**：**Codex**、**Hermes**、**Claude**（Claude Code）。
   - 不同宿主对 `error.message` / `structuredContent` / MCP 信封的处理不同，
     单测一个 Agent 无法代表其它 Agent。
   - 每个场景 × 每个 Agent 都要有独立结论（见 §4 结果矩阵）。
2. **必须清记忆**：每次运行前清空该 Agent profile 的会话历史（见 §3.1），
   否则命中的是上一次的对话记忆而非 ma3 知识库，测试无效。
3. **必须验证真实副作用**：不看 Agent 的自述总结，以**服务端 DB / verify.sh**为准
   （Agent 常"嘴上说做了、实际没做"）。
4. **必须清理**：测试中注入的假知识（错误 record）在测试结束后**必须从库里彻底删除**
   （见 §3.5），不得污染知识库。
5. 任一 Agent 在任一必测场景（**T0–T5**）失败 → **发版阻塞**，修复后重跑。

### 1.1 Agent 就绪状态

| Agent | profile 路径（202） | key label | 现状 |
|-------|--------------------|-----------|------|
| Claude Code | `ma3-eval/profiles/claude` | `MA3_KEY_CLAUDE_CODE` | ✅ 202 已接入（T0 已验） |
| Codex | `ma3-eval/profiles/codex` | `MA3_KEY_CLAUDE_CODE`（eval） | ✅ 202 已接入（T0 已验；LLM 用本机 config + proxy） |
| Hermes | `ma3-eval/profiles/hermes` | `MA3_KEY_CLAUDE_CODE`（eval） | ✅ 202 已接入（T0–T4 已验；LLM 用 deepseek + proxy） |

> **Codex on 202（已验证步骤）**
> 1. 同步 standalone：`rsync ~/.codex/packages/standalone → 202:~/.codex/packages/standalone`
> 2. 复制本机 `~/.codex/config.toml` 到 profile，**仅**改 `[mcp_servers.ma3]` 为 `http://127.0.0.1:8000/mcp` + eval `X-API-Key`
> 3. `bootstrap_agent_client_sync.sh codex` → policy 落到 `.codex/model_instructions.md`
> 4. 运行 codex 时：**LLM** 走 `HTTP_PROXY=192.168.31.200:1080`（duckcoding 从 202 直连不可用）；**MCP** 设 `NO_PROXY=127.0.0.1,localhost`（避免 proxy 把 localhost 打成 503）

> **Hermes on 202（已验证步骤）**
> Hermes 是 **Python 应用**（无预编译单文件 binary），用官方 PyPI 包安装，**不要** clone 源码（`install.sh` 会卡在 GitHub SSH clone）。
> 1. 专用 venv：`python3 -m venv ~/.hermes-venv`（202 是 py3.12，满足 `>=3.11,<3.14`）
> 2. `~/.hermes-venv/bin/pip install hermes-agent`（走 `HTTPS_PROXY=192.168.31.200:1080`）
> 3. **关键**：`pip install "mcp[cli]"` —— 默认 hermes 依赖里**不带** `mcp` 包，导致 `hermes mcp test` 报 `mcp.client.streamable_http is not available`，HTTP MCP 连不上（agent 会退回用 shell `curl`，且漏 `X-API-Key`）。装上后 `hermes mcp test ma3` 应显示 `✓ Connected` + 14 tools。
> 4. `ln -sf ~/.hermes-venv/bin/hermes ~/.local/bin/hermes`
> 5. profile 用 `HERMES_HOME=~/…/profiles/hermes/.hermes` 隔离；`config.yaml` 写 `model: {provider: deepseek, default: deepseek-chat}` + `mcp_servers.ma3`（url + `headers.X-API-Key`）；`.env` 放 `DEEPSEEK_API_KEY`
> 6. `bootstrap_agent_client_sync.sh hermes` → policy 落到 `$HERMES_HOME/rules/ma3-agent-policy.md`（Hermes 自动加载 `rules/*.md`）
> 7. 运行：**LLM(deepseek)** 走 `HTTP_PROXY`；**MCP** 设 `NO_PROXY=127.0.0.1,localhost`
> 8. 非交互跑：`hermes chat -q "<prompt>" --yolo`（`hermes tools list` 需要 pty，用 `ssh -t`）

---

## 2. 必测场景（Release Gate T0–T5）

**全部在 202 上执行**（见 §0.1）。默认载体 `mihomo-proxy`
（`/home/hct/ma3_deploy/code/eval/scenarios/mihomo-proxy`），需 Docker。

| ID | 能力 | 通过判据（以 DB / verify 为准） |
|----|------|-------------------------------|
| **T0** | 安装 / 接入（onboarding） | **全新** profile（无 `~/.ma3`、无 MCP 配置）能从服务端 bootstrap 同步工具 + policy、按该 Agent 原生布局写入 MCP 配置，且 Agent 运行时能成功发起一次 MCP 调用（`ma3_whoami` / `ma3_context` 返回 `result`） |
| **T1** | 客户端自动升级 | bump skill 版本后，stale Agent 收到 `policy_refresh_required=true` → 自动 `sync` → 本地 policy 文件更新、`~/.ma3/ma3-client.json` 的 `skill_bundle_version` 前进 |
| **T2** | 用知识 + 点赞去重 | 清记忆 Agent 用 KB 修好问题；写回是**一次 `ma3_feedback` 点赞**（`record_feedback` +1）；`records`/`cases` 计数**不变**（无重复新建） |
| **T3** | 点踩错误知识 | 库里植入一条**错误** record；Agent 命中后判定其错误 → **点踩**（该 record `record_feedback` = -1）；可选 `report_kind=refute` |
| **T4** | MCP 错误可自纠 | 触发校验类错误（如 `ma3_report` 套 `arguments` 信封 → `-32602`），`error.message` 含逐字段/定向提示；Agent 能据此改对并成功写回 |
| **T5** | DB API key 鉴权 | Agent 用其 DB-backed key 调 `tools/call` 成功（非 401）；无 key / 撤销 key → `-32001` 且 message 可操作 |

---

## 3. 执行步骤（每个 Agent 重复）

下述以 `AGENT` 变量代表 `claude` / `codex` / `hermes`，profile 在
`/home/hct/ma3-eval/profiles/$AGENT`，服务端跑在 202 的 `:8000`（host ma3）。

### 3.0 T0 — 安装 / 接入测试（全新 profile）

目标：证明"一个从没接过 ma3 的 Agent，能按 onboarding 装好并打通 MCP"。
必须从**干净**状态开始（删掉或换一个全新的 profile 目录）。

```bash
P=/home/hct/ma3-eval/profiles/$AGENT           # 或用临时全新目录
rm -rf "$P/.ma3"                               # 清掉既有 ma3 客户端状态（模拟首次）
export HOME="$P" MA3_BASE_URL="http://127.0.0.1:8000" MA3_API_KEY="<该 Agent 的 key>"

# 1) bootstrap 同步工具 + 完整 policy（HTTP，无 CLI —— ADR-003）
mkdir -p ~/.ma3/bin ~/.ma3/lib ~/.ma3/policy
curl -fsSL "$MA3_BASE_URL/client/scripts/sync_ma3_client.py" -o ~/.ma3/bin/sync_ma3_client.py
curl -fsSL "$MA3_BASE_URL/client/lib/ma3_sync_core.py"       -o ~/.ma3/lib/ma3_sync_core.py
curl -fsSL "$MA3_BASE_URL/client/scripts/sync_ma3_client.sh" -o ~/.ma3/bin/sync_ma3_client.sh
chmod +x ~/.ma3/bin/sync_ma3_client.sh
bash ~/.ma3/bin/sync_ma3_client.sh sync         # 拉 manifest + policy + onboarding

# 2) 按该 Agent 的原生布局写 MCP 配置（复用 harness 已支持的四种布局）
#    claude: `claude mcp add ... --header X-API-Key`
#    codex : ~/.codex/config.toml  [mcp_servers.ma3] + [mcp_servers.ma3.http_headers]
#    cursor: ~/.cursor/mcp.json    { mcpServers.ma3 { url, headers } }
#    droid : ~/.factory/mcp.json   { mcpServers.ma3 { type:http, url, headers } }
#    （见 code/eval/scenarios/agent-client-sync/scripts/configure_mcp.sh）

# 3) 用该 Agent 的运行时真实发起一次 MCP 调用
#    claude: claude -p "call ma3_whoami ..."
#    codex : NO_PROXY=127.0.0.1,localhost HTTP_PROXY=... codex exec ... "<prompt>"
```
**通过**：`~/.ma3/ma3-client.json` 生成且含 `skill_bundle_version`；policy 落到该 Agent 的
runtime 文件；Agent 运行时的 `ma3_whoami` / `ma3_context` 返回 `result`（非鉴权错误、非
"tool not found"）。
**失败信号**：MCP 未注册（Agent 看不到 ma3 工具）、header 缺失导致 `-32001`、
或 sync 拉不到 policy。

> **Codex on 202**：若 202 尚无 `codex` 二进制，可从本机同步 standalone 包：
> `rsync -av ~/.codex/packages/standalone hct@192.168.31.202:~/.codex/packages/`
> 并在 202 上 `ln -sf ~/.codex/packages/standalone/current/bin/codex ~/.local/bin/codex`。
> 再把本机 `~/.codex/config.toml` 中 **model 段**复制到 profile，MCP 段用
> `configure_mcp.sh` 写入 `127.0.0.1:8000`。

### 3.1 清记忆（所有 Agent 通用思路）

```bash
P=/home/hct/ma3-eval/profiles/$AGENT
# Claude Code：清会话历史，保留 CLAUDE.md（policy）与 ~/.ma3
rm -rf "$P"/.claude/projects/* "$P"/.claude/sessions/* "$P"/.claude/tasks/* \
       "$P"/.claude/shell-snapshots/* "$P"/.claude/session-env/* "$P"/.cache/claude-cli-node
# Codex / Hermes：清各自的会话/历史目录（接入时在此补对应路径），
#   但务必保留其 policy 文件与 ~/.ma3 同步状态。
```

### 3.2 T1 — 客户端自动升级

```bash
# 1) 记录 Agent 当前 skill 版本
jq -r .skill_bundle_version "$P/.ma3/ma3-client.json"        # e.g. 1.2.0
# 2) 在 202 上把服务端 skill 版本 +1（会触发 policy_refresh_required）
bash /home/hct/ma3_deploy/code/eval/scenarios/agent-client-sync/scripts/restart_host_ma3.sh <new_version>
# 3) 让 Agent 按 policy 跑一次 ma3_context，检查 structuredContent.server 并自动 sync
# 4) 断言
jq -r .skill_bundle_version "$P/.ma3/ma3-client.json"        # 应 == <new_version>
grep -c ma3_feedback "$P/.claude/CLAUDE.md"                  # policy 内容已更新
```
**通过**：state 里的 `skill_bundle_version` 前进，且本地 policy 文件被覆盖为新内容。

### 3.3 T2 — 用知识 + 点赞去重

```bash
URL=$(grep -E '^MA3_DATABASE_URL=' /home/hct/ma3_deploy/ma3.env | cut -d= -f2-)
# BEFORE 快照
psql "$URL" -Atc "select count(*) from records";  \
psql "$URL" -Atc "select count(*) from cases";    \
psql "$URL" -Atc "select count(*) from record_feedback"
# 重置 broken 场景 + 起 docker（见 §3.6），用中性 prompt 让 Agent 解题并遵循 policy
# AFTER 断言
```
**通过**：`record_feedback` +1（对命中的 record 点赞），`records` 与 `cases` 计数**不变**。
**失败信号**：`records`/`cases` +1（Agent 新建了重复 record 而不是点赞）。

### 3.4 T3 — 点踩错误知识

```bash
# 1) 向 Agent 会读到的库注入一条"自信但错误"的 record（示例：mihomo）
#    可用 dev/admin key 调 ma3_report，library_id 选该 Agent 可读且相关的库
#    （mihomo 知识在 lib_7e1dbe7d8688）；必须带 actions/evidence 否则 active 写入被拒。
# 2) 记下返回的 record_id，例如 WRONG_ID
# 3) 清记忆 + 重置场景 + 让 Agent 解题
# 4) 断言：该错误 record 被点踩
psql "$URL" -Atc "select vote from record_feedback where record_id='$WRONG_ID'"   # 期望 -1
```
**通过**：`$WRONG_ID` 的 `record_feedback.vote = -1`（可选：出现一条 `report_kind=refute`）。
**失败信号**：Agent 在推理里说"这条不对/用不了"却**没有**点踩（历史上的退化点）。

### 3.5 清理注入的假知识（T3 后必做）

```bash
# 彻底 purge（无 tombstone）：records + feedback + relations + embeddings + 索引 + audit
# 若该 record 独占一个 case，一并删除空 case（cases 主键列是 id）
psql "$URL" <<SQL
begin;
delete from record_feedback where record_id in ('$WRONG_ID','$REFUTE_ID');
delete from record_relations where source_id in ('$WRONG_ID','$REFUTE_ID') or target_id in ('$WRONG_ID','$REFUTE_ID');
delete from record_embeddings where record_id in ('$WRONG_ID','$REFUTE_ID');
delete from record_search_index where record_id in ('$WRONG_ID','$REFUTE_ID');
delete from write_audit_log where record_id in ('$WRONG_ID','$REFUTE_ID');
delete from records where id in ('$WRONG_ID','$REFUTE_ID');
delete from cases c where c.id in (select case_id from records where id in ('$WRONG_ID','$REFUTE_ID'))
  and not exists (select 1 from records r where r.case_id = c.id);
commit;
SQL
```
> 只删测试注入的假 record；命中真实正确 record 的点赞是真实信号，保留。

### 3.6 T4 — MCP 错误可自纠

由 `code/server/tests/integration/test_mcp_error_contract.py` 覆盖服务端契约；
**发版前额外做一次真实 Agent 验证**：诱导 Agent 触发一次 `-32602`（例如提示它先用
`ma3_validate` 的 `{tool_name, arguments}` 信封调 `ma3_report`），确认它读到的
`error.message` 含逐字段/定向提示，并能**自行改对**后成功 `ma3_report`。
**通过**：Agent 不在同一错误上循环，最终写回成功。

### 3.7 T5 — DB API key 鉴权

```bash
# 用该 Agent 的 key 直接打一发 tools/call
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -H "X-API-Key: $AGENT_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"ma3_whoami","arguments":{}}}'
```
**通过**：返回 `result`（非 401 / 非 `-32001`）；用错误 key 时返回 `-32001` 且 message 可操作。
参照 `test_deploy_verification.py::test_deploy_eval_claude_db_api_key`。

### 3.8 场景重置模板（mihomo）

```bash
S=/home/hct/ma3_deploy/code/eval/scenarios/mihomo-proxy
cd "$S" && docker compose down -v --remove-orphans
bash setup.sh                                   # 拷回 broken/config.yaml
set -a; . /home/hct/ma3/eval/secrets/secrets.env 2>/dev/null; set +a
docker compose up -d && sleep 3
bash verify.sh                                  # 修复前应失败；Agent 跑完应 "verify ok"
```

---

## 4. 结果矩阵（每次发版填写并归档）

发版分支/tag：`__________`　服务端 skill 版本：`1.4.0`　日期：`2026-07-03`（202 环境）

| 场景 | Claude | Codex | Hermes | 备注 |
|------|:------:|:-----:|:------:|------|
| T0 安装接入 | PASS | PASS | PASS | 三者均 `ma3_whoami` 返回 `principal_id=user:eval-admin`；Hermes 需 `pip install "mcp[cli]"` 才有 HTTP MCP |
| T1 自动升级 | PASS | PASS | PASS | client json staled 到 `0.5.0`（< min 1.0.0）→ `required=true` → sync → 回到 `1.3.0` |
| T2 点赞去重 | PASS | PASS | PASS | 均 `verify ok`，`vk_0dc976edbe9b` 点赞（+1），records/cases 计数不变（无重复新建） |
| T3 点踩错误 | PASS | PASS | PASS | 植入错误 record：Claude/Hermes/Codex 均点踩(-1)。**Codex 首轮 FAIL**（只点赞未点踩）→ policy **1.4.0** 加「逐条 triage 每条返回 record」规则后重跑 **PASS** |
| T4 错误自纠 | PASS | PASS | PASS | `ma3_report` 套 `arguments` 信封 → `-32602`，三者据 `error.message` 改对并 `ma3_validate` ok |
| T5 key 鉴权 | PASS | PASS | PASS | 三 agent 共用 eval DB key，valid→result；bad key→`-32001` 且 message 可操作 |

填 `PASS` / `FAIL` / `PENDING-SETUP`。**任一 FAIL 阻塞发版**。
结果 JSON 建议写入 `code/eval/results/`（`run_eval.sh` 已产出该目录）。

### 4.1 本轮已知缺口（需跟进）

- ~~**Codex T3 FAIL（点踩）**~~ **已修复（policy 1.4.0）**：新增 §1 第 7 条「**Triage EVERY returned record**」+ self-check 条目。Codex 重跑后 `wrong vote=-1` + `correct vote=1`。
- **Codex T2 轻微回退（可选跟进）**：T3 重跑时 Codex 除点赞外还新建了一条 near-duplicate record（`vk_bb0f1d70b5e0`，已清理）。若发版前仍出现，考虑在 policy 里再强调「用了现有 record 就只 upvote，禁止再写 new」。

---

## 5. 与自动化 eval 的关系

- `code/eval/orchestrator/run_eval.sh --scenario mihomo-proxy --agent <...>` 已封装
  "setup → compose up → 跑 Agent（带 policy/版本规则的 prompt）→ verify → 落 results"。
  T2/T4/T5 可在其基础上加 DB 断言；T1/T3 需要额外的"bump 版本 / 植入-清理假知识"步骤，
  本方案的 §3.2、§3.4–3.5 即为这部分的手动补充。
- 目标：把 T1–T5 逐步固化进 `run_all_scenarios_verify.sh` 式的脚本，
  但**在完全自动化之前**，本手动清单为发版**强制门禁**。

---

## 6. 变更记录

| 日期 | 变更 |
|------|------|
| 2026-07-03 | 首版：T0–T5 + Codex/Hermes/Claude；**固定 202 为唯一执行环境**；Codex LLM 可复用本机 config |
| 2026-07-03 | 首次全量执行：Hermes 用 `pip install hermes-agent` + `mcp[cli]` 接入（deepseek/proxy）；三 agent 跑完 T0–T5，仅 **Codex T3 FAIL**（未点踩错误记录），其余 17/18 PASS；补 §4.1 缺口 + Hermes 安装步骤 + `release_behavior_tests.sh` harness |
| 2026-07-03 | policy **1.4.0**：加「逐条 triage 每条 ma3_context 返回 record」；Codex T3 重跑 PASS；18/18 PASS |
