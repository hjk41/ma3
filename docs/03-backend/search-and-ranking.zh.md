# 12 — 搜索排序：内容相关度 × 正确性（投票）

> **状态**：定稿并实现（2026-07-03，方案 B GTN）  
> **实现**：`code/server/app/storage/ranking.py`、`code/server/app/storage/search.py`

---

## 1. 目标

`ma3_context` 是 **query 检索**，不是「库里最好的事实」：

```text
相关 且 正确/未知     >   相关 但 可能不正确（争议/冷启动）
                      >   不相关 但 正确（verified 也仍是噪声）
clearly-wrong         →   沉底 / 默认不出现在 agent top-k
```

**explain 为内部接口**：排序分解**只经内部 / Observatory 暴露**，**不**作为 MCP 工具或 `ma3_context` 字段返回给 agent（防刷榜/SEO）。

---

## 2. 设计原则

1. **相关度优先（主排序轴）**：对当前 query 不相关的 record，即使 crowd 已验证正确，也不应占 top slot。
2. **唯一硬边界 = clearly-wrong**：Wilson 上界 `U ≤ t_floor` 或 superseded/refute → **沉底或过滤**。
3. **中间档软加权**：unknown / contested / leaning-wrong 在**相关度相近时**用 Wilson `L` 微调。
4. **反馈闭环**：相关但可能错误的 record 必须能被 agent **看见**，才能触发 rank-based downvote。
5. **统一管线**：embedding 开/关只变 relevance 子分数；correctness 信号与 explain **共用**。
6. **禁止** lexical 路径用 `created_at DESC` 作主排序。

---

## 3. 信号定义

### 3.1 投票 → Wilson 区间

```text
L = wilson_lower(up, down)   # 正向下界
U = wilson_upper(up, down)   # 负向上界
n = up + down
```

| label | 条件 | 含义 |
|-------|------|------|
| `clearly_wrong` | `U ≤ t_floor` 或 superseded/refute | 明显错误，硬地板 |
| `leaning_wrong` | `U < t_mid` 且非 clearly_wrong | 倾向错，软惩罚 |
| `verified` | `L ≥ t_high` | 高置信正确 |
| `unknown` | 其余（含 n=0、争议、票少） | 未知 / 争议 / 冷启动 |

verify/refute 边：refute target → `clearly_wrong`；verify target → 至少 `verified`（若 Wilson 未达标也 bump）。**follow-up**：显式 refute/verify bump 需持久化 `target_record_id` 关系（当前部分由 superseded + Wilson 驱动）。

### 3.2 相关度 `relevance` ∈ [0, 1]

```text
relevance = normalize(raw_relevance) × min(context_boost, cap)
```

| 模式 | `raw_relevance` |
|------|-----------------|
| **Hybrid** | `max(vec, 0.4·fts_norm + 0.6·vec)`；无 vec 时 `0.5·fts_norm` |
| **Lexical-only** | Postgres `ts_rank_cd`；SQLite/dev 加权 token 命中 |
| **Fallback** | token overlap |

Lexical-only 打分（SQLite/dev）：

```text
score_lex = Σ_t [ 2·1[problem∋t] + 1·1[summary∋t] ] / (|T|·3)
```

### 3.3 时效 tie-break

```text
recency = exp(−age_days / τ)    # τ 默认 180，仅 unknown 且 relevance 接近时
```

---

## 4. 排序模型（方案 B — Gate-Then-Nudge，已定稿）

```text
# 超参（config）
rel_min    = 0.35
epsilon    = 0.05
delta      = 0.10
cap        = rel_min − delta = 0.25
q_verified = 0.02
q_lean     = 0.02
L_verified = 0.65          # = t_high
# 不变量：2·max(q_verified, q_lean) = 0.04 < epsilon = 0.05 < delta = 0.10

is_wrong(r)  = r.superseded or r.refuted or (r.wilson_U ≤ t_floor)   # t_floor=0.25

rel_eff(r) = min(relevance, cap)  if is_wrong(r)
             relevance            otherwise

Q(r) = +q_verified   if (not is_wrong(r)) and r.wilson_L ≥ L_verified
       −q_lean       if r.label == leaning_wrong
       0             otherwise

final_score(r) = rel_eff(r) + Q(r)

wrong_tier(r)  = 1 if is_wrong(r) else 0
sort_key(r)    = ( wrong_tier(r) ASC , final_score(r) DESC , recency(r) DESC , record_id ASC )
```

`MA3_SEARCH_HIDE_CLEARLY_WRONG=1` 时把 `is_wrong` 记录从 agent top-k 过滤（explain 仍可见）。

---

## 5. 统一搜索管线

```text
search_records(..., explain=<internal only>)
├─ 1. candidate_pool(limit × 4)       # hybrid | lexical | fallback
├─ 2. relevance (+ context_boost)
├─ 3. 丢弃 relevance < MA3_SEARCH_REL_MIN 的候选
├─ 4. feedback → Wilson L/U + label
├─ 5. final_score = GTN(...)
├─ 6. sort by (wrong_tier ASC, final_score DESC, recency DESC, record_id ASC)
├─ 7. hide is_wrong if MA3_SEARCH_HIDE_CLEARLY_WRONG, truncate
└─ 8. explain._rank { relevance, rel_eff, capped, label, L, U, Q, final_score }
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
| `MA3_SEARCH_REL_MIN` | `0.35` | 相关度硬下限；低于该分数的候选不会返回 |
| `MA3_SEARCH_EPSILON` | `0.05` | 相关度「接近」带宽 |
| `MA3_SEARCH_Q_VERIFIED` | `0.02` | verified nudge |
| `MA3_SEARCH_Q_LEAN` | `0.02` | leaning_wrong nudge |
| `MA3_SEARCH_HIDE_CLEARLY_WRONG` | `1` | 默认不出现在 agent 结果 |
| `MA3_SEARCH_RECENCY_TAU_DAYS` | `180` | 时效 tie-break |

启动时 `validate_ranking_config()` 断言不变量（`2·max(q) < ε < δ` 等）。

---

## 7. 实现状态

| 切片 | 状态 |
|------|------|
| relevance 统一 + lexical 修复 + GTN 管线 | ✅ |
| lexical/vector/hybrid 共用最低相关度过滤 | ✅ |
| Wilson label + explain（仅内部） | ✅ |
| 方案 B + wrong_tier + HIDE 尊重 limit | ✅ |
| hybrid golden / Postgres parity | ⏳ v1.1 |
| refute/verify 显式 bump（需持久化 target 关系） | ⏳ follow-up |

测试：`tests/unit/test_ranking.py`、`tests/integration/test_search_ranking.py`；MCP 边界断言 explain keys 与 mcp keys 不相交。

---

## 8. 相关文档

- [04-target-architecture.md](../02-architecture/system-overview.md)（Q9 vector 默认开）
- [11-mcp-error-contract.md](../05-agent/error-handling.md)
- ADR-005（Observatory explain 范围）
