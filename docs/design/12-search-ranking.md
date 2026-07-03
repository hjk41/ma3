# 12 — 搜索排序：内容相关度 × 正确性（投票）

> **状态**：设计草案 v2（2026-07-03）  
> **动机**：202 eval 环境 `MA3_DISABLE_EMBEDDINGS=1` 时，搜索退化为 `_like_search_records` 的 **`created_at DESC`**，既不反映 query 相关度，也不应用 `record_feedback`。导致 mihomo 场景里 policy/hermes 等无关新 record 压在正确 fix 之上。  
> **共识**（用户 + fable / gpt-5.5 / composer-2.5-fast / sonnet-5 四方 agent 视角咨询，2026-07-03）：  
> **`ma3_context` 是 query 检索，不是「库里最好的事实」** — 相关度是主闸门；正确性在「可检索集合」内作软修正；**仅 clearly-wrong 设硬地板**。

```text
目标排序（agent 视角）：

  相关 且 正确/未知     >   相关 但 可能不正确（争议/冷启动）
                        >   不相关 但 正确（verified 也仍是噪声）
  clearly-wrong         →   沉底 / 默认不出现在 agent top-k
```

**相关 ADR/文档**：`04-target-architecture-draft.md`（Q9 vector 默认开）、`07-kb-read-write-review.md`、`ma3-agent-policy.mdc` §1.7 / §3.0（rank-based downvote）。

---

## 1. 现状审计

| 路径 | 触发条件 | 相关度 | 投票 | 问题 |
|------|----------|--------|------|------|
| `_hybrid_search` | Postgres + embeddings **开** | `0.4·FTS_norm + 0.6·vector`，再 × context_boost | × `_feedback_multiplier` | 乘子无法表达「相关优先」；净票/Wilson 与相关度纠缠 |
| `_like_search_records` | `disable_embeddings=1` 或 hybrid 无候选 | **无**（`ORDER BY created_at DESC`） | **不应用** | 完全错误 |
| superseded | 两路径 | — | refute/supersede | 已过滤，保留 |

`context_boost`（`search_context_service.py`）保留，作为 **relevance 的一部分**。

---

## 2. 设计原则（v2）

1. **相关度优先（主排序轴）**：对当前 query 不相关的 record，即使 crowd 已验证正确，也不应占 top slot — agent 会跳过，只占阅读预算。
2. **唯一硬边界 = clearly-wrong**：Wilson 上界 `U ≤ t_floor` 或 superseded/refute → **沉底或过滤**；不得因「高相关」排到 unknown/contested 之前。
3. **中间档软加权**：unknown / contested / leaning-wrong（未达 clearly-wrong）在**相关度相近时**用 Wilson `L` 微调，**不得**让不相关 verified record 压过相关 record。
4. **反馈闭环**：相关但可能错误的 record 必须能被 agent **看见**，才能触发 rank-based downvote、让 Wilson 区间收窄。
5. **统一管线**：embedding 开/关只变 relevance 子分数；correctness 信号与 explain **共用**。
6. **可解释**：每条 hit 输出 `relevance`、`wilson_L/U`、`correctness_label`、`final_score` 及分解项。

---

## 3. 信号定义

### 3.1 投票 → Wilson 区间（不用净票分档）

净票 `up−down` 混淆比例、样本量、争议度。用 Wilson 区间（z 可配置，默认 1.96）：

```text
L = wilson_lower(up, down)   # 正向下界：有把握 p ≥ L
U = wilson_upper(up, down)   # 负向上界：有把握 p ≤ U
n = up + down
```

**标签**（用于 explain 与软加权，非主排序硬键）：

| label | 条件 | 含义 |
|-------|------|------|
| `clearly_wrong` | `U ≤ t_floor` 或 superseded/refute | 明显错误，硬地板 |
| `leaning_wrong` | `U < t_mid` 且非 clearly_wrong | 倾向错，软惩罚 |
| `verified` | `L ≥ t_high` | 高置信正确 |
| `unknown` | 其余（含 n=0、争议、票少） | 未知 / 争议 / 冷启动 |

verify/refute 边：refute target → `clearly_wrong`；verify target → 至少 `verified`（若 Wilson 未达标也 bump）。

### 3.2 相关度 `relevance` ∈ [0, 1]

```text
relevance = normalize(raw_relevance) × min(context_boost, cap)
```

| 模式 | `raw_relevance` |
|------|-----------------|
| **Hybrid** | `max(vec, 0.4·fts_norm + 0.6·vec)`；无 vec 时 `0.5·fts_norm` |
| **Lexical-only** | Postgres `ts_rank_cd`；SQLite/dev 加权 token 命中（§3.4） |
| **Fallback** | token overlap |

**禁止** lexical 路径用 `created_at DESC` 作主排序。

### 3.3 Lexical-only 打分（§3.4 保留）

```text
score_lex = Σ_t [ 2·1[problem∋t] + 1·1[summary∋t] ] / (|T|·3)
```

### 3.4 时效（可选，仅 unknown 且 relevance 接近时 tie-break）

```text
recency = exp(−age_days / τ)    # τ 默认 180
```

---

## 4. 排序模型（定稿：方案 B — Gate-Then-Nudge）

> **决定（2026-07-03）**：采用 **方案 B / GTN**（详见 §10）。单一 `final_score` 浮点排序 +
> clearly-wrong 相关度 cap + fable 变体的 wrong `tier` 结构保险。

### 4.1 公式

```text
# 超参（config，§6）
rel_min    = 0.35          # 相关度「有效」阈值
epsilon    = 0.05          # 相关度「接近」带宽
delta      = 0.10          # clearly-wrong cap 安全边距
cap        = rel_min − delta = 0.25
q_verified = 0.02          # 正幅值；符号在 Q(r) 里给
q_lean     = 0.02          # 正幅值；符号在 Q(r) 里给
L_verified = 0.65          # = t_high
# 核心不变量（回归测试锁死）：2·max(q_verified, q_lean) = 0.04 < epsilon = 0.05 < delta = 0.10

is_wrong(r)  = r.superseded or r.refuted or (r.wilson_U ≤ t_floor)   # t_floor=0.25

rel_eff(r) = min(relevance, cap)  if is_wrong(r)
             relevance            otherwise

Q(r) = +q_verified   if (not is_wrong(r)) and r.wilson_L ≥ L_verified
       −q_lean       if r.label == leaning_wrong          # U < t_mid 且非 wrong；净效果 −0.02
       0             otherwise                            # unknown / 冷启动

final_score(r) = rel_eff(r) + Q(r)

# 结构保险（fable 变体）：wrong 永远沉底，避免纯数值 cap 在边界被 Q 抬过线
wrong_tier(r)  = 1 if is_wrong(r) else 0
recency(r)     = exp(−age_days / τ)     # τ = MA3_SEARCH_RECENCY_TAU_DAYS，仅平票 tie-break（D4）
sort_key(r)    = ( wrong_tier(r) ASC , final_score(r) DESC , recency(r) DESC , record_id ASC )
```

排序：先按 `wrong_tier` 升序（非 wrong 在前），再按 `final_score` 降序。
`MA3_SEARCH_HIDE_CLEARLY_WRONG=1` 时把 `is_wrong` 记录从 agent top-k 过滤（explain 仍可见）。

### 4.2 约束满足

| 约束 | 如何满足 |
|------|----------|
| **C1 相关 > 不相关** | Q 最大摆幅 0.04 < ε=0.05；relevance 差 ≥ ε 时 Q 翻不了盘 |
| **C2 clearly-wrong 地板** | wrong 进 `wrong_tier=1` 恒沉底；即使不用 tier，cap 后 ≤0.27 < 非 wrong 下限 ≈0.33 |
| **C3 软正确性** | \|Δrel\| < ε 时由 Q 决定 verified ≻ unknown ≻ leaning_wrong |
| **C4 冷启动可发现** | n=0 → label=unknown → Q=0 → `final_score=relevance`，纯相关度不受罚 |
| **C5 explain** | 输出 `{relevance, rel_eff, capped, label, wilson_L, wilson_U, Q, final_score, wrong_tier}` |

**与 agent policy 1.5.0**：agent 采用的「正确答案」= 其最终选用且 upvote 的 record；只 downvote **排在该 record 之前**且 agent 判定错误的 record（通常 relevance 也不低）。

> **explain 为内部接口**：排序分解（relevance/Wilson/Q/final_score）**只经内部 / Observatory 暴露**，
> **不**作为 MCP 工具或 `ma3_context` 字段返回给 agent —— 防止贡献者反推排序公式做 SEO / 刷榜（见 §6、ADR-005）。

---

## 5. 统一搜索管线

```text
search_records(..., explain=<internal only>)
├─ 1. candidate_pool(limit × 4)       # hybrid | lexical | fallback
├─ 2. relevance (+ context_boost)
├─ 3. feedback → Wilson L/U + label
├─ 4. final_score = GTN(...)          # §4 方案 B
├─ 5. sort by (wrong_tier ASC, final_score DESC)
├─ 6. hide is_wrong if MA3_SEARCH_HIDE_CLEARLY_WRONG, truncate
└─ 7. explain._rank { relevance, rel_eff, capped, label, L, U, Q, final_score }
       # explain 仅内部 / Observatory；不经 MCP 返回 agent
```

---

## 6. 配置

| 变量 | 默认 | 说明 |
|------|------|------|
| `MA3_DISABLE_EMBEDDINGS` | `0` | 关→hybrid；开→lexical（仍打分） |
| `MA3_SEARCH_WILSON_Z` | `1.96` | Wilson z |
| `MA3_SEARCH_T_HIGH` | `0.65` | `L ≥` → verified |
| `MA3_SEARCH_T_MID` | `0.5` | `U <` → leaning_wrong |
| `MA3_SEARCH_T_FLOOR` | `0.25` | `U ≤` → clearly_wrong |
| `MA3_SEARCH_REL_MIN` | `0.35` | 相关度「有效」阈值（= cap 基准） |
| `MA3_SEARCH_EPSILON` | `0.05` | 相关度「接近」带宽（> 2·\|q\|） |
| `MA3_SEARCH_Q_VERIFIED` | `0.02` | verified nudge（不变量：2·q < ε） |
| `MA3_SEARCH_Q_LEAN` | `0.02` | leaning_wrong nudge |
| `MA3_SEARCH_HIDE_CLEARLY_WRONG` | `1` | 默认不出现在 agent 结果 |
| `MA3_SEARCH_RECENCY_TAU_DAYS` | `180` | 时效 tie-break |

> **explain 不暴露给 agent**：`ma3_search_explain` MCP 工具**删除**；`ma3_context` 的 `include_explain`
> 字段**移除**。排序分解只经内部调用 / Observatory 只读面获取，避免贡献者反推公式刷榜（ADR-005）。

---

## 7. 测试计划（gpt-5.5 起草 → fable / sonnet-5 / composer-2.5 review 定稿）

> **审阅共识**：本算法的最大「假信心」风险是**在合成 relevance 上测 GTN，而 202 的 lexical 路径根本不跑 GTN**。
> 因此测试重心是 *真实 `search_records` 路径*（尤其 `disable_embeddings=1`）+ 少量确定性 oracle + 结构不变量，
> **不是**大规模 golden / NDCG / property 套件。

### 7.0 前置阻塞（写测试前必须先修 / 定案）

| # | 事项 | 说明 |
|---|------|------|
| **B1** | `search.py:263` 短路 | `disable_embeddings` 时直接 `return _like_search_records(...)`，**绕过** feedback/GTN。slice 1 必须让 lexical 路径也进 GTN，否则 202 上所有 GTN 测试形同虚设 |
| **B2** | 符号 bug（已修） | §4.1 原 `q_lean=−0.02` 且 `Q=−q_lean` → +0.02（反向奖励）。已改为**正幅值 + 符号在 Q 内给** |
| **B3** | superseded 语义 → **D3 已定：cap+sink** | 改为 `is_wrong`+`wrong_tier` 沉底（可被 `HIDE_CLEARLY_WRONG` 隐藏），**不再硬过滤**——agent 仍能看到并 downvote，收窄 Wilson。C2/C3/Sup 测试按此写 |
| **B4** | tie-break 语义 → **D4 已定：recency-τ** | `sort_key = (wrong_tier ASC, final_score DESC, recency-τ DESC, record_id ASC)`；测试须**冻结时间戳**并对近似平票 unknown 断言 recency 生效 |
| **B5** | lexical 打分公式（§3.4）欠定 | 目前只定义 `problem 2x / summary 1x`；review 提到的 tag / 多 token 权重**未在设计里**。要么补 §3.4，要么测试不得断言未设计的行为 |

### 7.1 CI 分级

- **每个 PR（cheap / 确定性 / 阻塞合并）**：7.2 全部。
- **Nightly / 发版前**：7.3。
- **移交 agent eval**（不进 pytest search 套件）：R7 rank-downvote 属于 policy+feedback 行为，放 `code/eval/`。

### 7.2 必测（每 PR）

**A. 纯函数单测（无 DB，`RankInput` dataclass）**
- Wilson `L/U`：**n=0 钉死 `L=0,U=1`**（除零高发 bug）；n=1；U 跨 0.25 / 0.5；L 跨 0.65。
- label 划分：每组 `(up,down,flags)` 恰好落一个 label（partition 属性）；**refute→clearly_wrong、verify→≥verified 的图边 bump**（不能只测票数）。
- `is_wrong / rel_eff / Q / final_score / sort_key`：含 **wrong_tier 压过高 final_score**（低 rel 非 wrong vs 高 rel clearly-wrong → tier 赢，证明 C2 靠 tier 而非 cap 算术）。
- **边界表**（确定性，非随机）：Δrel 恰 = ε（0.049 vs 0.051）；relevance 恰 = cap 的 wrong record；U=0.25（闭）、U=0.5（开）、L=0.65（闭）。

**B. 配置不变量守卫**
- 对**运行时加载的 settings**（非字面量）断言 `2·max(q_verified,q_lean) < ε < δ`、`cap == rel_min−δ`、阈值序 `0≤t_floor<t_mid<t_high≤1`、符号。
- **负例（mutation）**：把 `q_verified=0.03` → 守卫必须 fail（防守卫写成自证式空操作）。
- 该断言同时在 **app 启动时**跑（坏 env 立即失败，不只 CI）。

**C. lexical 打分单测（202 热路径）**
- §3.4 权重 / 归一 / 确定性（依 B5 定案后写）。
- **CJK query**（本库内容多为中文；whitespace 分词会把中文当一个 token）→ 至少一条中文 query 命中。

**D. 集成（真实 `search_records`，SQLite，`disable_embeddings=1`，冻结时间戳）**
- **1 条 mihomo 有序 fixture**：mihomo fix / policy 噪声 / 更新的无关 record（可选 clearly-wrong），断言 **有序 record_ids**（非「命中即可」）。这是 202 实际 bug。
- **回归钉子**：断言 lexical 路径主排序 **不是** `created_at DESC`。
- **pool-composition 稳定性**：`_normalize_scores` 按池内 max 归一 → 加一条无关 record 会整体缩放 relevance、可能把 pair 推过 ε。加/减一条无关 record，protected pair 不得翻转。
- **HIDE_CLEARLY_WRONG × limit**：过滤发生在候选池（limit×4）之后，返回页不得因隐藏 wrong 而少于 limit；wrong 不得漏进第 N 位。

**E. MCP explain 边界（契约/安全，PR 阻塞）**
- 用 **key 集合不相交**断言（`internal_explain_keys ∩ mcp_ctx_keys == ∅`），**不**用硬编码 9 字段名（加字段时能自动兜住）。
- **happy path + error path 都测**（空库 / 畸形 query），防异常序列化泄漏 `_rank`。
- 复用已有 `test_search_explain_is_not_exposed`（工具已删）。

### 7.3 Nightly / 发版前（不阻塞 PR）

- **property 测试（hypothesis，D1 defer — 不纳入 v1 PR）**：hybrid slice 后再考虑 nightly，仅 C1/C3 且 `Δrel ≥ ε + tol`；v1 边界由 §7.2 确定性 oracle + 边界表覆盖。
- **embeddings-on 接线 smoke（1 条）**：monkeypatch `embed_text` 返回固定向量，`disable_embeddings=0`，断言 GTN 顺序——只验接线，不测召回质量，期望顺序须来自**票/flag/protected-pair**，绝不来自假向量几何。
- **golden 语料（D5 已定：延后）**：hybrid slice 落地后再建 **~30 record × 10–15 query**（含 CJK / 单 token / 多 token / 无命中 / 近义重复）；届时**仅** protected-pair 零反转作门（**D2 已定**），NDCG 仅诊断趋势、**不作门**、**不**做 exact-full-order 快照。
- **Postgres+pgvector（D5 已定：延后）**：hybrid slice 后加，仅 *候选召回* smoke（hybrid 返回大致正确候选集）；排序数学在 SQLite 已覆盖（final_score/sort_key 与 DB 无关）。

### 7.4 不写（成本 > 价值）

真实 embedding API、每 PR 性能基准、大语料 exact-full-order 快照、UI 测、Kendall-τ（无阈值＝没人看）、穷举 Wilson 快照、permutation-invariance 独立属性。

### 7.5 用例表（R1–R7 扩展）

| ID | 层 | setup | 断言 | 约束 |
|----|----|-------|------|------|
| R1 | oracle | rel=0.8 unknown vs rel=0.1 verified | 前 ≻ 后 | C1 |
| R2 | oracle | rel=0.8 verified vs rel=0.75 unknown | 前 ≻ 后 | C3 |
| R3 | oracle | rel=0.9 clearly_wrong vs rel=0.5 unknown | 后 ≻ 前（需 tier） | C2 |
| R3b | oracle | rel=0.2 unknown vs rel=0.9 clearly_wrong | 前 ≻ 后（低相关非 wrong 仍在 wrong 前） | C2/tier |
| R4 | oracle | 同 rel，up2/0 vs up10/0 | 后 = verified ≻ | Wilson |
| R5 | oracle | up=100,down=98 高 rel | label=unknown（U≈0.57>0.5） | Wilson |
| R5b | oracle | 中样本 U 恰跨 0.5 / L 恰跨 0.65 | label 正确 | 边界 |
| R6 | 集成 | lexical mihomo，冻结时间 | **fix ≻ policy 噪声（有序）** | C1/lexical |
| R6b | 集成 | 加一条无关 record | R6 顺序不变 | pool-stability |
| R7 | **eval** | rank-downvote 场景 | 错误 record 仅在排采用答案前时被 downvote | policy |
| Wn0 | unit | up=0,down=0 | L=0,U=1,label=unknown,Q=0,final=rel | C4 |
| Sup | unit | superseded + up=20/0 | is_wrong=True（压过 verified） | B3 |
| Ref | unit | refute 边 | label=clearly_wrong | 图边 |
| Cap | unit | wrong, rel=0.9 | rel_eff=cap=0.25, capped=True | cap |
| Cfg+ | unit | 加载 settings | 不变量成立 | 守卫 |
| Cfg− | unit | q_verified=0.03 | 守卫 fail | 守卫负例 |
| Lex | unit | §3.4 打分 + CJK query | 确定性 & 中文命中 | B5 |
| Mcp | 集成 | ctx happy + error | explain keys ∩ mcp keys = ∅ | C5/契约 |
| Hide | 集成 | HIDE=1, limit=5, 池含 wrong | 返回满 5 且无 wrong | pool/limit |

### 7.6 决策记录

| # | 决策 | 结果 |
|---|------|------|
| D2 | 回归门指标 | **只用 protected-pair 零反转作硬门**；NDCG 仅 nightly 诊断趋势，不作门 |
| D3 | superseded 语义 | **cap+sink wrong_tier**（不再硬过滤，可被 HIDE 隐藏） |
| D4 | tie-break | **recency-τ 再 record_id**（`sort_key` 见 §4.1） |
| D5/D6 | golden 语料 & Postgres CI | **延后**到 hybrid slice 落地；v1 仅 oracle + 1 条 mihomo 有序集成 |
| D1 | property/hypothesis 层 | **defer**：v1 只用确定性 oracle + 边界表；hybrid slice 后再考虑 nightly hypothesis（C1/C3，带容差） |

---

## 8. 实现切片

1. ✅ relevance 统一 + lexical 修复（去 created_at）+ **打通 GTN**（`search.py` 短路已修，lexical 也进 GTN 管线，见 §7 B1）  
2. ✅ Wilson label + explain（`ranking.py`，explain 仅内部）  
3. ✅ 接入方案 B（`ranking.py` + `search_records` 统一管线；superseded cap+sink；HIDE 过滤尊重 limit）  
4. ⏳ hybrid（Postgres FTS+vector）路径 golden / parity（延后，见 D5/D6）  
5. ⏳ eval / release gate 重跑（T0–T5 + mihomo 有序）  

> **本次已落地**：`app/core/config.py`（`MA3_SEARCH_*` + `validate_ranking_config` 启动断言）、
> `app/storage/ranking.py`（GTN 纯函数）、`app/storage/search.py`（统一管线 + `_lexical_relevance`）；
> 测试 `tests/unit/test_ranking.py`（31）+ `tests/integration/test_search_ranking.py`（9）+ MCP 边界断言。
>
> **已知范围外（follow-up）**：`is_wrong` 目前由 **superseded + Wilson U≤t_floor** 驱动；
> §3.1 的「显式 refute→clearly_wrong / verify→verified bump」需把 `report_kind` 的 `target_record_id`
> 持久化为关系（当前只进 `write_audit_log`，`record_id`=新记录）。`ranking.py` 已预留
> `refuted` / `verified_override` 入参，接线待该关系落库后补。

---

## 9. 变更记录

| 日期 | 变更 |
|------|------|
| 2026-07-03 | v1：字典序 tier×relevance（已废弃） |
| 2026-07-03 | Wilson 替代净票分档 |
| 2026-07-03 | **v2**：四方 agent 咨询 → 相关度优先 + clearly-wrong 硬地板；§4 方案待算法讨论定稿 |
| 2026-07-03 | **v2.1**：排序目标改为「相关 > 不相关（即使 verified）」；§10 填入方案 A（三档分桶）/ B（GTN 微调）供择一 |
| 2026-07-03 | **v2.2 定稿**：选 **方案 B（GTN）** + wrong_tier；§4 正式公式。explain 改为**内部接口**：删除 MCP `ma3_search_explain` 工具 + `ma3_context.include_explain` 字段（防刷榜/SEO） |
| 2026-07-03 | **v2.3**：§7 测试计划经 gpt-5.5 起草 + fable/sonnet-5/composer review 定稿。修 §4.1 `q_lean` 符号 bug（正幅值）。标注 B1 lexical 短路（`search.py:263` 绕过 GTN）为前置阻塞。列 D1–D6 冲突待决策 |
| 2026-07-03 | **v2.4 实现**：D1–D6 定案（见 §7.6）。落地方案 B：`ranking.py` + 统一 `search_records` 管线（lexical 进 GTN、superseded cap+sink、HIDE 尊重 limit、recency tie-break）+ 配置守卫启动断言。40 新测试通过（含 CJK / pool-stability / MCP 边界）。refute/verify 显式 bump 列为 follow-up（需持久化 target 关系） |
| 2026-07-03 | **v2.5 sonnet-5 验收**：ACCEPT-WITH-NITS。补 recency tie-break 测试、边界表测试（t_floor 闭 / t_high 闭 / t_mid 开 / Δrel=ε）、删除死代码 `_like_search_records`（防 created_at DESC 回潮）、MCP 泄露键集从 `RankResult.explain()` 动态派生。全量 **145 passed** |

---

## 10. 算法方案（四方讨论汇总 → 择一）

> fable / gpt-5.5 / composer-2.5-fast / sonnet-5 均给出可落地公式。收敛为 **两类**；推荐在 **方案 A / B** 中择一。

### 方案 A：三档分桶排序（Structural Three-Tier）

**别名**：TGRB（composer）+ Trust Ladder（gpt-5.5）  
**思路**：用**整数 bucket** 保证 C1/C2 不可被调参打破；桶内再比细项。

```text
bucket(r):
  0  SINK      — clearly_wrong / superseded / refuted
  1  IRRELEVANT — 非 wrong 且 relevance < rel_min
  2  RELEVANT   — 非 wrong 且 relevance ≥ rel_min

trust_tier(r):                    # 仅 bucket=2 内有意义
  2  verified     (L ≥ t_high)
  1  unknown      (含 n=0、争议)
  0  leaning_wrong (U < t_mid)

sort_key(r) = (
  bucket(r),           # 主键：2 > 1 > 0
  trust_tier(r),       # bucket=2 内：2 > 1 > 0
  relevance(r),        # 降序
  wilson_L(r)          # tie-break
)
```

**clearly_wrong**：进 bucket 0，**不硬删**（explain/诊断可见）；`MA3_SEARCH_HIDE_CLEARLY_WRONG=1` 时从 agent top-k 过滤。

**默认超参**：`rel_min=0.15~0.35`（小库偏高）；`t_floor=0.25, t_mid=0.5, t_high=0.65`。

| 约束 | 如何满足 |
|------|----------|
| C1 | bucket 2 永远 > bucket 1，与 verified 无关 |
| C2 | bucket 0 永远 < bucket 2 |
| C3 | 同 bucket 2 内 trust_tier 决定 verified ≻ unknown ≻ leaning_wrong |
| C4 | n=0 → unknown(1)，高 rel 仍进 bucket 2 |
| C5 | 输出 `{bucket, trust_tier, relevance, L, U, label}` |

**优点**：约束**结构性成立**，不用赌 `δ < ε` 不等式；易测、易 explain。  
**缺点**：`rel_min` 处 cliff（0.34 vs 0.36 跨桶）；同 relevance 带内不细分（可用 ±0.001 relevance 作第四键缓解）。

---

### 方案 B：相关度 + 有界信任微调（Gate-Then-Nudge）

**别名**：GTN（sonnet-5）+ Gate+ε-Nudge（fable，fable 对 wrong 用 tier 位）  
**思路**：**单一 `final_score` 浮点**排序；信任项幅度严格小于相关度「有效间距」。

```text
# 核心不变量：2 · max(|Q|) < ε  且  CAP + max(Q) < rel_min + min(Q)

rel_min = 0.35    ε = 0.05    δ = 0.10    CAP = rel_min − δ = 0.25
q_verified = +0.02    q_lean = −0.02    L_verified = 0.65

rel_eff(r) =
  min(relevance, CAP)     if clearly_wrong or superseded
  relevance               otherwise

Q(r) =
  +q_verified   if L ≥ L_verified and not wrong
  −q_lean       if leaning_wrong
  0             otherwise   # unknown / 冷启动

final_score(r) = rel_eff(r) + Q(r)
```

**fable 变体（更稳的 wrong 处理）**：wrong 额外设 `tier=1`，非 wrong `tier=0`，`sort_key = (tier, −final_score)` — 与 GTN 数值 cap 二选一或叠加。

**clearly_wrong**：**cap 相关度**（非过滤），保证 `final_score ≤ CAP + q_verified < rel_min + q_lean`。

| 约束 | 如何满足 |
|------|----------|
| C1 | Q 最大 swing 0.04 < ε；rel 差 ≥0.05 时 Q 无法翻盘 |
| C2 | cap 后上限 ≈0.32 < rel_min 非 wrong 下限 ≈0.38 |
| C3 | \|Δrel\| < ε 时由 Q 决定 verified ≻ unknown ≻ leaning |
| C4 | n=0 → Q=0，score=relevance 纯相关度 |
| C5 | `{relevance, rel_eff, capped, label, Q, final_score}` |

**优点**：实现**最简单**（一条 score + sort）；同 bucket 内 relevance 连续，无分桶 cliff。  
**缺点**：依赖超参不等式，调大 `q_*` 或缩小 `ε` 可能**静默破坏** C1/C2；需单元测试锁死不变量。

---

### 对比与推荐

| | **方案 A 三档分桶** | **方案 B GTN 微调** |
|--|---------------------|---------------------|
| 实现复杂度 | 中（bucket + trust + sort） | **低**（一个 float） |
| 约束保证 | **结构性**，调参难破坏 | 代数不变量，需测试守护 |
| C3 细粒度 | 桶内仅 3 档 trust | **连续 rel + ε 带内 Q** |
| wrong 处理 | bucket 0 沉底 | rel cap（+ 可选 tier） |
| 四方倾向 | composer、gpt-5.5 | fable、sonnet-5 |

**决定（2026-07-03）**：采用 **方案 B（GTN）** + fable 的 `wrong_tier` 结构保险。公式已升为 §4 正式定义。
上线前必须加**不变量回归测试**（`2·max(|q|) < ε < δ`）与 §7 的 R1–R7。

