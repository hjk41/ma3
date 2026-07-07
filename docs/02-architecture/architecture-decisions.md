# 架构决策记录（ADR 索引）

> ADR 正文位于 [decisions/](decisions/) 目录。

| ADR | 主题 | 正文 |
|-----|------|------|
| 001 | SaaS 首要部署 | [001-saas-primary-deploy.md](decisions/001-saas-primary-deploy.md) |
| 002 | 写回默认 active | [002-active-default-writes.md](decisions/002-active-default-writes.md) |
| 003 | MCP-only Agent 面 | [003-mcp-only-agent-surface.md](decisions/003-mcp-only-agent-surface.md) |
| 004 | Vector 默认开 | [004-vector-default-optional-off.md](decisions/004-vector-default-optional-off.md) |
| 005 | Observatory 范围 | [005-observatory-ui-scope.md](decisions/005-observatory-ui-scope.md) |
| 006 | Hook 本地优先 | [006-hook-candidates-local-first.md](decisions/006-hook-candidates-local-first.md) |
| 007 | 里程碑与 Observatory 治理 | [007-v1-milestones-and-observatory-governance.md](decisions/007-v1-milestones-and-observatory-governance.md) |
| 008 | 维护者：人与 Agent | [008-maintainer-human-or-agent.md](decisions/008-maintainer-human-or-agent.md) |
| 009 | Client sync Scheme B | [009-client-sync-scheme-b.md](decisions/009-client-sync-scheme-b.md) |
| 010 | Authing 社交登录 | [010-authing-social-login.md](decisions/010-authing-social-login.md) |
| 011 | KB 访问与 org 隔离 | [011-kb-access-and-org-isolation.md](decisions/011-kb-access-and-org-isolation.md) |
| 012 | Billing 与配额 | [012-billing-and-quotas.md](decisions/012-billing-and-quotas.md) |
| 013 | 写入确认、审计、删除 | [013-write-confirmation-audit-delete.md](decisions/013-write-confirmation-audit-delete.md) |
| 014 | MCP 错误可自纠 | [014-mcp-error-self-correction.md](decisions/014-mcp-error-self-correction.md) |

## 产品层决策（未单独 ADR）

| 决策 | 摘要 | 规格 |
|------|------|------|
| Observatory 非 admin → 403 | 非 302 | [portal-permissions.md](../04-frontend/portal-permissions.md) |
| Stats ≠ Enumerate | 普通用户仅 Stats + 深链 | 同上 |
| API Key 删除非撤销 | 硬删行 | [api-keys-ui-and-api.md](../04-frontend/api-keys-ui-and-api.md) |
| 显示名一次性 setup | 全局唯一 | [display-name-registration.md](../04-frontend/display-name-registration.md) |
| 搜索 GTN 方案 B | 相关度优先 + wrong_tier | [search-and-ranking.md](../03-backend/search-and-ranking.md) |

## 新 ADR 流程

1. 复制 [decisions/000-template.md](decisions/000-template.md)
2. 编号递增，状态 Accepted / Superseded
3. 更新本索引 + 相关 backend/frontend 规格文档
