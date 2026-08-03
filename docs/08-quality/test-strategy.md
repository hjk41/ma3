# Test Strategy

> Chinese version: [test-strategy.zh.md](test-strategy.zh.md)

## Layers

| Layer | Location | Responsibility |
|----|------|------|
| **Unit** | `code/server/tests/unit/` | Ranking, entitlement, billing formulas, onboarding idempotency |
| **Integration** | `code/server/tests/integration/` | MCP, portal, keys, auth, search ranking |
| **E2E (Tier A)** | `tests/e2e/` Playwright local-auth | Every PR (`e2e-portal`); see [portal-playwright-regression.md](testing/portal-playwright-regression.md) |
| **E2E (Tier B)** | `scripts/e2e_authing_ui.py` | Nightly / pre-release; requires Authing secrets |
| **Agent eval** | `code/eval/` | Weekly subset + pre-release T0–T5; see [agent-eval-cadence.md](testing/agent-eval-cadence.md) |

## Module gates

| Module | Key tests |
|------|----------|
| MCP errors | `test_mcp_integration.py` — assert `error.message` |
| Search GTN | `test_ranking.py`, `test_search_ranking.py`; MCP explain does not leak |
| API keys | Delete blocks MCP, legacy revoked hidden, 422 label |
| Portal | Navigation, 403 observatory, stat links, list sort/filter |
| Write buffer | Author-vs-others visibility, publish job |
| Display name | Setup gate, unique constraint |

## CI policy

- **Every PR**: unit + integration (mainly SQLite) + **Playwright portal Tier A** (`e2e-portal`)
- **Nightly**: Tier A again; Authing Tier B if secrets configured (`nightly.yml`)
- **Weekly (LAN host checklist)**: agent behavior subset **claude × T2/T4/T5** via `run_behavior_subset.sh`
- **Pre-release**: full T0–T5 × 3 agents (blocks release); search golden (hybrid deferred)
- **Merge blocking**: ranking invariant guards, MCP explain key sets disjoint; **not** Authing E2E or agent matrix

## To be added

- [x] Playwright portal regression scope — [portal-playwright-regression.md](testing/portal-playwright-regression.md)
- [x] Agent eval fixed cadence — [agent-eval-cadence.md](testing/agent-eval-cadence.md)
- [ ] Coverage targets
- [ ] Performance/load tests (read quota, search pool)
