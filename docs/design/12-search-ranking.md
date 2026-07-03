# 12 — 搜索排序：内容相关度 × 正确性（投票）

> **状态**：设计草案（2026-07-03）  
> **动机**：202 eval 环境 `MA3_DISABLE_EMBEDDINGS=1` 时，搜索退化为 `_like_search_records` 的 **`created_at DESC`**，既不反映 query 相关度，也不应用 `record_feedback`。导致 mihomo 场景里 policy/hermes 等无关新 record 压在正确 fix 之上；agent policy 1.5.0 的「按排名点踩」也因此建立在错误排名上。  
> **目标排序**（产品约束，用户确认）：

```text
相关 且 正确   >   不相关 但 正确   >   相关 但 不正确
（明显错误的 record 应落到后面，不能靠「沾 query 关键词」排到前面）
```

**相关 ADR/文档**：`04-target-architecture-draft.md`（Q9 vector 默认开）、`07-kb-read-write-review.md`、`ma3-agent-policy.mdc` §1.7 / §3.0（rank-based downvote）。

---

## 1. 现状审计

| 路径 | 触发条件 | 相关度 | 投票 | 问题 |
|------|----------|--------|------|------|
| `_hybrid_search` | Postgres + embeddings **开** | `0.4·FTS_norm + 0.6·vector`，再 × context_boost | × `_feedback_multiplier`（净票 ≤-3→0.3 … ≥3→1.15） | 投票是**乘子**，高相关 × 强踩 仍可能高于低相关 × 无票；**不能**保证「不相关但正确 > 相关但不正确」 |
| `_like_search_records` | `disable_embeddings=1` 或 hybrid 无候选 | **无**（`ORDER BY created_at DESC`） | **不应用** | 完全错误：最新 record 赢，与 query 无关 |
| superseded | 两路径 | — | refute/supersede 关系 | 已过滤，保留 |

`context_boost`（`search_context_service.py`）已存在：task_type / target / tags / applicable_if 乘性加权，**保留**作为相关度的一部分。

---

## 2. 设计原则

1. **正确性优先于相关度（跨档）**：一旦有足够证据表明 record **错误**，即使用户 query 高度匹配，也不得压过「不相关但正确」的 record。
2. **相关度优先于正确性（同档内）**：在「正确」或「未知」档内，更贴 query 的 record 排前。
3. **统一管线**：embedding 开/关只改变 **相关度子分数** 的计算方式；正确性档、Wilson、时效、explain 输出**共用**。
4. **可解释**：`ma3_search_explain` / Observatory 必须输出 `relevance`、`correctness_tier`、`quality`、各因子，供 agent policy「按最终排名点踩」与人工审计。
5. **抗刷 + 冷启动**：每 principal 每 record 一票（已有）；少量票用 Wilson 下界保守估计；新 record 在「未知」档内有时效 grace，避免被老高票无关 record 永久压制。

---

## 3. 排序模型（两轴 + 字典序）

### 3.1 正确性档 `correctness_tier`（整数，越大越好）

由 `record_feedback` 汇总（up/down）+ 关系（superseded/refute）决定：

| tier | 条件 | 语义 |
|:----:|------|------|
| **3** | `net = up − down ≥ 1` **或** 存在未 supersede 的 verify 边 | **已验证正确** |
| **2** | `net = 0` 且无 supersede | **未知 / 争议**（冷启动默认在此档） |
| **1** | `net < 0` 且 `net > −3` | **倾向错误** |
| **0** | `net ≤ −3` **或** superseded / 强 refute | **明显错误 / 已废止**（仍可在 explain 中展示，但默认沉底；可选 hard-filter） |

**Wilson 下界**（抗刷，用于档内微调与 explain，**不单独决定跨档**）：

```text
quality = wilson_score_lower(up, down)   # 区间 [0, 1]，z=1.96
```

- 当 `up + down < min_votes_for_tier`（建议 **3**）时，tier 仍按 net 分档，但 `quality` 向 0.5 收缩（贝叶斯先验），避免 1 票 up 把 record 当「铁证正确」。
- `min_votes_for_tier` 可配置；eval 可设为 1 以便测试。

### 3.2 相关度 `relevance`（浮点，越大越好，归一化到 [0, 1]）

**统一公式**：

```text
relevance = normalize(raw_relevance) × context_boost(payload, SearchContext)
```

`raw_relevance` 按 embedding 开关分支，**结果必须可比**（同一 query 下 max 归一化）：

| 模式 | `raw_relevance` |
|------|-----------------|
| **Hybrid**（Postgres FTS + vector） | 沿用现有：`max(vec, 0.4·fts_norm + 0.6·vec)`；无 vec 时 `0.5·fts_norm` |
| **Lexical-only**（`disable_embeddings=1`） | **新**：Postgres 用 `ts_rank_cd`（与 hybrid 同 FTS 路径）；SQLite/dev 用 **加权 token 命中分**（见 §3.4），**禁止** `created_at DESC` 作为主排序 |
| **Fallback** | 无 FTS 且无 vector：token overlap 分（§3.4） |

`context_boost` 上限建议 cap 在 **1.5**，避免 metadata 完全压过文本相关度。

### 3.3 时效 `recency`（仅作用于 tier 2 未知档）

避免「未知 + 很旧 + 偶然高相关」长期占位：

```text
recency = exp(−age_days / τ)     # τ 默认 180 天
```

- **tier 3 / 1 / 0**：不加 recency（正确/错误由票决定，不靠新旧）。
- **tier 2**：`relevance_adj = relevance × (0.85 + 0.15 × recency)`，给新 record 小幅 grace。

### 3.4 Lexical-only 打分（替换 `_like_search_records` 的 created_at 排序）

对 query token 集合 `T`（与现 `_search_tokens` 相同，长度 ≥2，最多 8 个）：

```text
score_lex(record) = Σ_t∈T [
    w_problem · 1[problem 含 t]  +  w_summary · 1[summary 含 t]
] / (|T| · (w_problem + w_summary))

w_problem = 2.0 ,  w_summary = 1.0
```

可选：完整 phrase 命中 problem 额外 +0.2 bonus。

候选集：与现逻辑相同 `library_id IN (...) AND status='active' AND (token OR …)`，**ORDER BY score_lex DESC**，LIMIT pool。

### 3.5 最终排序键（字典序）

```text
sort_key(record) = (
    correctness_tier,           # 主键：3 > 2 > 1 > 0
    relevance_adj,              # tier=2 时含 recency；其他 tier 用 relevance
    quality,                    # Wilson 下界，同 relevance 时 tie-break
    created_at                  # 最后 tie-break：新的略优先（仅同分）
)
```

**保证产品约束**（在 tier 分档正确时）：

| A | B | 比较 |
|---|---|------|
| 相关 + 正确 (tier 3, rel 高) | 不相关 + 正确 (tier 3, rel 低) | 同 tier → rel 高者前 ✓ |
| 不相关 + 正确 (tier 3, rel 低) | 相关 + 错误 (tier 1, rel 高) | tier 3 > tier 1 ✓ |
| 相关 + 错误 (tier 1) | 明显错误 (tier 0) | tier 1 > tier 0 ✓ |

**与 agent policy 1.5.0 对齐**：「正确答案的排名」= **`ma3_context` 返回列表中 tier=3（或 agent 认定采用的那条）且 relevance 最高** 的 record 的位置；只点踩排在该位置**之前**的 tier≤1 record。

---

## 4. 统一搜索管线（实现 sketch）

```text
search_records(library_ids, problem, limit, context, explain)
│
├─ 1. candidate_pool(limit × 4)     # hybrid | lexical | fallback
├─ 2. relevance + context_boost     # → relevance [0,1]
├─ 3. load feedback + superseded
├─ 4. correctness_tier + quality    # Wilson
├─ 5. recency (tier 2 only)
├─ 6. sort by sort_key DESC
├─ 7. truncate to limit
└─ 8. attach explain._rank { relevance, tier, quality, recency, ... }
```

**删除/废弃**：在 `disable_embeddings=1` 路径上单独走 `_like_search_records(..., ORDER BY created_at)`；改为调用同一 `rank_records()`。

**配置**（`config.py` / env）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `MA3_DISABLE_EMBEDDINGS` | `0` | 关则走 hybrid；开则 lexical-only（仍打分，非 created_at） |
| `MA3_SEARCH_MIN_VOTES_FOR_QUALITY` | `3` | Wilson 强置信阈值 |
| `MA3_SEARCH_RECENCY_TAU_DAYS` | `180` | 未知档时效 |
| `MA3_SEARCH_HIDE_TIER0` | `1` | tier 0 默认不出现在 agent 结果（explain 可选展示） |

---

## 5. 与旧 `_feedback_multiplier` 的关系

| 旧 | 新 |
|----|-----|
| `final = relevance × multiplier(net)` | `sort_key = (tier(net), relevance, quality)` |
| 1 票 down → ×0.7，仍可能高于无票高相关 | 1 票 down → tier 1，**整档**低于所有 tier 2/3 |
| 无法表达「不相关但正确 > 相关但不正确」 | 字典序显式保证 |

迁移：删除 `_feedback_multiplier` 在最终排序中的使用；保留字段在 explain 里作「legacy_multiplier」一段过渡可选。

---

## 6. 测试计划

### 6.1 单元测试（`tests/unit/test_search_ranking.py`）

| 用例 | 输入 | 期望顺序 |
|------|------|----------|
| R1 跨档 | A: rel=0.9 tier=1；B: rel=0.2 tier=3 | B ≻ A |
| R2 同档相关度 | A: rel=0.8 tier=3；B: rel=0.3 tier=3 | A ≻ B |
| R3 冷启动 | A: rel=0.9 tier=2 新；B: rel=0.5 tier=2 旧 400d | A ≻ B（recency） |
| R4 Wilson | A: up=1 down=0 tier=3；B: up=100 down=5 tier=3, rel 略低 | 仍 B ≻ A（同 tier 内 quality tie-break） |
| R5 tier0 过滤 | net≤−3 | 默认不出现在 top-k |
| R6 lexical-only | disable_embeddings=1，mihomo query | mihomo fix record ≻ 无关 policy record（**非** created_at） |

### 6.2 集成 / eval

- 重跑 `release-agent-behavior-tests.md` T2/T3：排名须由 **tier+relevance** 决定，**不再**依赖手动改 `created_at` 做实验。
- `ma3_search_explain` 快照：每条 hit 含 `correctness_tier`、`relevance`、`quality`。

### 6.3 202 部署

1. 实现 lexical 打分 + 统一 `rank_records()`  
2. 保持 `MA3_DISABLE_EMBEDDINGS=1` 直至 pgvector 模型就绪  
3. 可选第二阶段：202 开 embedding，验证 hybrid 与 lexical 排名一致性趋势  

---

## 7. 开放问题（实现前确认）

| # | 问题 | 建议默认 |
|---|------|----------|
| Q1 | tier 3 是否要求 `net≥1`，还是 `net≥0` 且 up>0 即可？ | **`net ≥ 1`**（至少净一票 up） |
| Q2 | verify/refute 边是否自动 bump tier？ | refute target → tier 0；verify target → 至少 tier 3 |
| Q3 | tier 0 对 agent 完全隐藏还是沉底可见？ | **默认隐藏**（`MA3_SEARCH_HIDE_TIER0=1`） |
| Q4 | 是否在 v1 就开 202 embedding？ | **第二阶段**；先修 lexical 路径 |

---

## 8. 实现切片（建议 PR 顺序）

1. **`rank_records()` + lexical 打分** — 替换 `_like_search_records` 的 created_at 排序；加单元测试 R1/R6  
2. **hybrid 路径接入同一 ranker** — 删除 `_feedback_multiplier` 最终排序；加 R2/R4  
3. **recency + explain 字段** — `ma3_search_explain` 结构化 `_rank`  
4. **refute/supersede → tier** — 与 `get_superseded_record_ids` 统一  
5. **202 开 embedding（可选）** — profile 配置，对比 eval 结果  

---

## 9. 变更记录

| 日期 | 变更 |
|------|------|
| 2026-07-03 | 初稿：字典序 tier×relevance、Wilson、lexical-only 修复、与 policy 1.5.0 rank-downvote 对齐 |
