# 12 — Search Ranking: Content Relevance × Correctness (Votes)

> Chinese version: [search-and-ranking.zh.md](search-and-ranking.zh.md)

> **Status**: Finalized and implemented (2026-07-03, Plan B GTN)
> **Implementation**: `code/server/app/storage/ranking.py`, `code/server/app/storage/search.py`

---

## 1. Goals

`ma3_context` is **query retrieval**, not "the best facts in the library":

```text
relevant AND correct/unknown       >   relevant BUT possibly incorrect (contested/cold-start)
                                    >   irrelevant BUT correct (even verified is still noise)
clearly-wrong                      →   sinks / does not appear in agent top-k by default
```

**`explain` is an internal-only interface**: the ranking breakdown is exposed **only internally / via Observatory**, and is **not** returned to the agent as an MCP tool or `ma3_context` field (to prevent gaming/SEO).

---

## 2. Design principles

1. **Relevance first (primary sort axis)**: a record irrelevant to the current query should not occupy a top slot even if the crowd has verified it as correct.
2. **The only hard boundary = clearly-wrong**: Wilson upper bound `U ≤ t_floor` or superseded/refute → **sinks or gets filtered**.
3. **Soft weighting for middle tiers**: unknown / contested / leaning-wrong are nudged with Wilson `L` **only when relevance is close**.
4. **Feedback loop**: a record that is relevant but possibly incorrect must remain **visible** to the agent, so it can trigger a rank-based downvote.
5. **Unified pipeline**: toggling embeddings only changes the relevance sub-score; correctness signals and `explain` are **shared**.
6. **Prohibited**: using `created_at DESC` as the primary sort on the lexical path.

---

## 3. Signal definitions

### 3.1 Votes → Wilson interval

```text
L = wilson_lower(up, down)   # positive lower bound
U = wilson_upper(up, down)   # negative upper bound
n = up + down
```

| label | condition | meaning |
|-------|------|------|
| `clearly_wrong` | `U ≤ t_floor` or superseded/refute | Clearly wrong, hard floor |
| `leaning_wrong` | `U < t_mid` and not clearly_wrong | Leaning wrong, soft penalty |
| `verified` | `L ≥ t_high` | High-confidence correct |
| `unknown` | Everything else (including n=0, contested, few votes) | Unknown / contested / cold-start |

verify/refute edges: a refute target → `clearly_wrong`; a verify target → at least `verified` (bumped even if the Wilson score doesn't otherwise qualify). **Follow-up**: explicit refute/verify bumps need to persist the `target_record_id` relationship (currently partially driven by superseded + Wilson).

### 3.2 Relevance `relevance` ∈ [0, 1]

```text
relevance = normalize(raw_relevance) × min(context_boost, cap)
```

| Mode | `raw_relevance` |
|------|-----------------|
| **Hybrid** | `max(vec, 0.4·fts_norm + 0.6·vec)`; `0.5·fts_norm` when no vec |
| **Lexical-only** | Postgres `ts_rank_cd`; SQLite/dev uses weighted token hits |
| **Fallback** | Token overlap |

Lexical-only scoring (SQLite/dev):

```text
score_lex = Σ_t [ 2·1[problem∋t] + 1·1[summary∋t] ] / (|T|·3)
```

### 3.3 Recency tie-break

```text
recency = exp(−age_days / τ)    # τ defaults to 180, only for unknown with close relevance
```

---

## 4. Ranking model (Plan B — Gate-Then-Nudge, finalized)

```text
# hyperparameters (config)
rel_min    = 0.35
epsilon    = 0.05
delta      = 0.10
cap        = rel_min − delta = 0.25
q_verified = 0.02
q_lean     = 0.02
L_verified = 0.65          # = t_high
# invariant: 2·max(q_verified, q_lean) = 0.04 < epsilon = 0.05 < delta = 0.10

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

When `MA3_SEARCH_HIDE_CLEARLY_WRONG=1`, records where `is_wrong` is true are filtered out of the agent top-k (still visible in `explain`).

---

## 5. Unified search pipeline

```text
search_records(..., explain=<internal only>)
├─ 1. candidate_pool(limit × 4)       # hybrid | lexical | fallback
├─ 2. relevance (+ context_boost)
├─ 3. feedback → Wilson L/U + label
├─ 4. final_score = GTN(...)
├─ 5. sort by (wrong_tier ASC, final_score DESC, recency DESC, record_id ASC)
├─ 6. hide is_wrong if MA3_SEARCH_HIDE_CLEARLY_WRONG, truncate
└─ 7. explain._rank { relevance, rel_eff, capped, label, L, U, Q, final_score }
       # explain is internal / Observatory only; not returned to the agent via MCP
```

---

## 6. Configuration

| Variable | Default | Description |
|------|------|------|
| `MA3_DISABLE_EMBEDDINGS` | `0` | Off → hybrid; on → lexical (still scored) |
| `MA3_SEARCH_WILSON_Z` | `1.96` | Wilson z |
| `MA3_SEARCH_T_HIGH` | `0.65` | `L ≥` → verified |
| `MA3_SEARCH_T_MID` | `0.5` | `U <` → leaning_wrong |
| `MA3_SEARCH_T_FLOOR` | `0.25` | `U ≤` → clearly_wrong |
| `MA3_SEARCH_REL_MIN` | `0.35` | "Effective" relevance threshold |
| `MA3_SEARCH_EPSILON` | `0.05` | Relevance "closeness" bandwidth |
| `MA3_SEARCH_Q_VERIFIED` | `0.02` | verified nudge |
| `MA3_SEARCH_Q_LEAN` | `0.02` | leaning_wrong nudge |
| `MA3_SEARCH_HIDE_CLEARLY_WRONG` | `1` | Does not appear in agent results by default |
| `MA3_SEARCH_RECENCY_TAU_DAYS` | `180` | Recency tie-break |

`validate_ranking_config()` asserts invariants at startup (e.g. `2·max(q) < ε < δ`).

---

## 7. Implementation status

| Slice | Status |
|------|------|
| Unified relevance + lexical fix + GTN pipeline | ✅ |
| Wilson label + explain (internal only) | ✅ |
| Plan B + wrong_tier + HIDE respects limit | ✅ |
| Hybrid golden / Postgres parity | ⏳ v1.1 |
| Explicit refute/verify bump (needs persisted target relationship) | ⏳ follow-up |

Tests: `tests/unit/test_ranking.py`, `tests/integration/test_search_ranking.py`; MCP boundary asserts that `explain` keys and MCP keys are disjoint.

---

## 8. Related documents

- [04-target-architecture.md](../02-architecture/system-overview.md) (Q9 vector on by default)
- [11-mcp-error-contract.md](../05-agent/error-handling.md)
- ADR-005 (Observatory explain scope)
