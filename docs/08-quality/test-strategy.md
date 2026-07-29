# Test Strategy

> Chinese version: [test-strategy.zh.md](test-strategy.zh.md)

## Layers

| Layer | Location | Responsibility |
|----|------|------|
| **Unit** | `code/server/tests/unit/` | Ranking, entitlement, billing formulas, onboarding idempotency |
| **Integration** | `code/server/tests/integration/` | MCP, portal, keys, auth, search ranking |
| **E2E** | `scripts/e2e_authing_ui.py` | Optional; requires `AUTHING_TEST_USER` |
| **Agent eval** | `code/eval/` | Not a release artifact; real agent behavior (T1–T5) |

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

- **Every PR**: unit + integration (mainly SQLite)
- **Nightly / pre-release**: search golden (hybrid deferred), agent eval subset
- **Merge blocking**: ranking invariant guards, MCP explain key sets disjoint

## To be added

- [ ] Coverage targets
- [ ] Playwright portal regression scope
- [ ] Performance/load tests (read quota, search pool)
