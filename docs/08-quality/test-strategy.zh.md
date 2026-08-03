# 测试策略

## 分层

| 层 | 位置 | 职责 |
|----|------|------|
| **Unit** | `code/server/tests/unit/` | ranking、entitlement、billing 公式、onboarding 幂等 |
| **Integration** | `code/server/tests/integration/` | MCP、portal、keys、auth、search ranking |
| **E2E（Tier A）** | `tests/e2e/` Playwright local-auth | 每个 PR（`e2e-portal`）；见 [portal-playwright-regression.zh.md](testing/portal-playwright-regression.zh.md) |
| **E2E（Tier B）** | `scripts/e2e_authing_ui.py` | Nightly / 发版前；需 Authing 密钥 |
| **Agent eval** | `code/eval/` | 周更子集 + 发版前 T0–T5；见 [agent-eval-cadence.zh.md](testing/agent-eval-cadence.zh.md) |

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

- **每 PR**：unit + integration + **Playwright 门户 Tier A**
- **Nightly**：Tier A；有密钥时跑 Authing Tier B
- **每周（LAN checklist）**：claude × T2/T4/T5（`run_behavior_subset.sh`）
- **发版前**：完整 T0–T5 × 三 Agent；search golden（hybrid 延后）
- **阻塞合并**：**不**包含 Authing E2E / Agent 全矩阵

## 待补充

- [x] Playwright 门户回归范围
- [x] Agent eval 固定节奏
- [ ] 覆盖率目标
- [ ] 性能/负载测试（read quota、search pool）
