# 功能索引（Feature Index）

按模块列出能力、规格文档与验收。

| 功能 | 规格 | 验收 |
|------|------|------|
| 愿景与领域模型 | [vision.md](vision.md)、[problem-domain.md](problem-domain.md) | — |
| 系统架构 | [../02-architecture/system-overview.md](../02-architecture/system-overview.md) | — |
| KB 访问与 org 隔离 | [../03-backend/authorization-and-libraries.md](../03-backend/authorization-and-libraries.md) | — |
| 自助注册 + 首登建库 | [../05-agent/getting-started.md](../05-agent/getting-started.md) | v1-self-service-onboarding |
| API Key 生命周期 | [../04-frontend/api-keys-ui-and-api.md](../04-frontend/api-keys-ui-and-api.md) | v1-api-key-lifecycle |
| 显示名注册 | [../04-frontend/display-name-registration.md](../04-frontend/display-name-registration.md) | v1-display-name-registration |
| 用户门户 | [../04-frontend/portal-permissions.md](../04-frontend/portal-permissions.md)、[IA](../04-frontend/information-architecture.md) | v1-user-portal |
| Write buffer | [../03-backend/write-buffer.md](../03-backend/write-buffer.md) | v1-library-write-buffer |
| 写入审计与删除 | [../03-backend/writes-audit-and-deletion.md](../03-backend/writes-audit-and-deletion.md) | — |
| MCP 错误自纠 | [../05-agent/error-handling.md](../05-agent/error-handling.md) | 集成测试 |
| 搜索排序 GTN | [../03-backend/search-and-ranking.md](../03-backend/search-and-ranking.md) | test_ranking / test_search_ranking |
| 计费与配额 | [../03-backend/billing-and-quotas.md](../03-backend/billing-and-quotas.md) | 待 Phase B3 |
| 个人开发者端到端 | [user-journeys.md](user-journeys.md) J1 | v1-personal-developer-journey |

验收文档目录：`code` 仓库内 `docs/acceptance/v1-*.md`（待迁入 all_docs，见 [../08-quality/acceptance-criteria.md](../08-quality/acceptance-criteria.md)）。
