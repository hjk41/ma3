# 测试策略

## 分层

| 层 | 位置 | 职责 |
|----|------|------|
| **Unit** | `code/server/tests/unit/` | ranking、entitlement、billing 公式、onboarding 幂等 |
| **Integration** | `code/server/tests/integration/` | MCP、portal、keys、auth、search ranking |
| **E2E** | `scripts/e2e_authing_ui.py` | 可选；需 `AUTHING_TEST_USER` |
| **Agent eval** | `code/eval/` | 非发布物；真实 Agent 行为（T1–T5） |

## 模块门禁

| 模块 | 关键测试 |
|------|----------|
| MCP 错误 | `test_mcp_integration.py` — assert `error.message` |
| 搜索 GTN | `test_ranking.py`、`test_search_ranking.py`；MCP explain 不泄露 |
| API Keys | delete blocks MCP、legacy revoked hidden、422 label |
| Portal | navigation、403 observatory、stat links、list sort/filter |
| Write buffer | author vs others visibility、publish job |
| Display name | setup gate、unique constraint |

## CI 策略

- **每 PR**：unit + integration（SQLite 为主）
- **Nightly / 发版前**：search golden（hybrid 延后）、Agent eval 子集
- **阻塞合并**：ranking 不变量守卫、MCP explain 键集不相交

## 待补充

- [ ] 覆盖率目标
- [ ] Playwright 门户回归范围
- [ ] 性能/负载测试（read quota、search pool）
