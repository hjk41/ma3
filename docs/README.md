# ma3 文档地图

> **体系版本**：2026-07-06  
> **说明**：本目录为 ma3 的**唯一系统化文档入口**。按「产品 → 架构 → 实现 → 交付」组织；标注 ✅ 已有实质内容，📝 占位/待补充。

---

## 阅读路径（新人）

1. [01-product/pitch.md](01-product/pitch.md) + [vision.md](01-product/vision.md) — 为什么做 ma3  
2. [02-architecture/system-overview.md](02-architecture/system-overview.md) — 系统形态  
3. [01-product/user-journeys.md](01-product/user-journeys.md) — 怎么用起来  
4. [05-agent/getting-started.md](05-agent/getting-started.md) — Agent 接入  
5. [04-frontend/information-architecture.md](04-frontend/information-architecture.md) — 登录后 UI  

---

## 1. 产品（01-product）

| 文档 | 状态 | 说明 |
|------|------|------|
| [pitch.md](01-product/pitch.md) | ✅ | 对外产品叙事 |
| [vision.md](01-product/vision.md) | ✅ | 愿景、原则、成功标准 |
| [problem-domain.md](01-product/problem-domain.md) | ✅ | 领域模型、质量状态 |
| [personas.md](01-product/personas.md) | 📝 | 角色画像（缺用户故事） |
| [user-journeys.md](01-product/user-journeys.md) | ✅ | 端到端旅程 |
| [roadmap.md](01-product/roadmap.md) | ✅ | v1 / v1.1 / 不做 |
| [feature-index.md](01-product/feature-index.md) | ✅ | 功能 → 规格 → 验收索引 |

---

## 2. 架构（02-architecture）

| 文档 | 状态 | 说明 |
|------|------|------|
| [system-overview.md](02-architecture/system-overview.md) | ✅ | 模块、MCP 契约、部署 profile |
| [external-integrations.md](02-architecture/external-integrations.md) | 📝 | Authing/Postgres/HF 集成（缺生产拓扑） |
| [data-model.md](02-architecture/data-model.md) | ✅ | ER、状态机总览 |
| [architecture-decisions.md](02-architecture/architecture-decisions.md) | ✅ | ADR 索引 + [decisions/](02-architecture/decisions/) 正文 |

---

## 3. 后端（03-backend）

| 文档 | 状态 | 说明 |
|------|------|------|
| [authentication.md](03-backend/authentication.md) | 📝 | Authing session、setup 门控 |
| [authorization-and-libraries.md](03-backend/authorization-and-libraries.md) | ✅ | ACL、grants、visibility |
| [billing-and-quotas.md](03-backend/billing-and-quotas.md) | ✅ | 套餐 schema、enforcement 设计 |
| [writes-audit-and-deletion.md](03-backend/writes-audit-and-deletion.md) | ✅ | report_kind、删除、tombstone |
| [write-buffer.md](03-backend/write-buffer.md) | ✅ | buffered 状态、publish |
| [search-and-ranking.md](03-backend/search-and-ranking.md) | ✅ | GTN 算法与配置 |
| [background-jobs.md](03-backend/background-jobs.md) | 📝 | 定时任务（缺运维细节） |
| [api-overview.md](03-backend/api-overview.md) | 📝 | 路由总览（缺 OpenAPI） |

---

## 4. 前端（04-frontend）

| 文档 | 状态 | 说明 |
|------|------|------|
| [information-architecture.md](04-frontend/information-architecture.md) | ✅ | 路由、顶栏、列表壳、页面规格 |
| [page-specifications.md](04-frontend/page-specifications.md) | ✅ | 页面规格索引 |
| [portal-permissions.md](04-frontend/portal-permissions.md) | ✅ | 权限、Stats/Enumerate、403 |
| [visual-design-system.md](04-frontend/visual-design-system.md) | ✅ | GitHub 浅色 token、组件 |
| [ui-copy-and-interactions.md](04-frontend/ui-copy-and-interactions.md) | 📝 | 文案与交互（缺错误页） |
| [api-keys-ui-and-api.md](04-frontend/api-keys-ui-and-api.md) | ✅ | Keys 列表/详情/API |
| [display-name-registration.md](04-frontend/display-name-registration.md) | ✅ | setup 一次性显示名 |

---

## 5. Agent 集成（05-agent）

| 文档 | 状态 | 说明 |
|------|------|------|
| [getting-started.md](05-agent/getting-started.md) | ✅ | 自助 key、首登建库 |
| [mcp-tools-reference.md](05-agent/mcp-tools-reference.md) | 📝 | 工具参考（缺完整示例） |
| [error-handling.md](05-agent/error-handling.md) | ✅ | MCP 错误自纠契约 |
| [policy-and-client-sync.md](05-agent/policy-and-client-sync.md) | 📝 | policy/sync（IDE 示例待补） |

> 操作步骤 HTTP 真源仍在 `code/client/agent-onboarding.md`（**待迁入** 本目录或链接替换）。

---

## 6. 运维（06-operations）

| 文档 | 状态 | 说明 |
|------|------|------|
| [deployment.md](06-operations/deployment.md) | 📝 | Profile 总览 |
| [self-hosting.md](06-operations/self-hosting.md) | ✅ | Compose 自托管（bootstrap / OIDC） |
| [deployment-authing.md](06-operations/deployment-authing.md) | ✅ | Authing 控制台 + env |
| [runbook.md](06-operations/runbook.md) | 📝 | 发版/回滚/排障 |
| [monitoring-and-health.md](06-operations/monitoring-and-health.md) | 📝 | healthz/doctor/告警 |
| [security.md](06-operations/security.md) | 📝 | 安全摘要（缺威胁模型） |

---

## 7. 商业与运营（07-commercial）

| 文档 | 状态 | 说明 |
|------|------|------|
| [pricing-and-plans.md](07-commercial/pricing-and-plans.md) | ✅ | 用户向套餐摘要 |
| [administrator-guide.md](07-commercial/administrator-guide.md) | 📝 | Observatory/运维指南 |
| [end-user-faq.md](07-commercial/end-user-faq.md) | 📝 | 用户 FAQ 草稿 |

---

## 8. 质量与交付（08-quality）

| 文档 | 状态 | 说明 |
|------|------|------|
| [acceptance-criteria.md](08-quality/acceptance-criteria.md) | 📝 | 验收索引（正文待迁入） |
| [test-strategy.md](08-quality/test-strategy.md) | ✅ | 测试分层与门禁 |
| [release-checklist.md](08-quality/release-checklist.md) | 📝 | 发版 checklist 草案 |

---

## 9. 工程协作（09-engineering）

| 文档 | 状态 | 说明 |
|------|------|------|
| [glossary.md](09-engineering/glossary.md) | ✅ | 术语与废止用语 |
| [repository-layout.md](09-engineering/repository-layout.md) | 📝 | 代码布局摘要 |
| [changelog.md](09-engineering/changelog.md) | 📝 | 变更日志（待建立版本节奏） |

---

## 当前缺失文档（待新建或迁入）

以下类型在体系中**应有**，但尚无独立成稿或仅有占位：

### 高优先级

| 建议路径 | 内容 |
|----------|------|
| `02-architecture/decisions/` | ✅ 已迁入 | 14 篇 ADR 正文 |
| `05-agent/agent-onboarding.md` | 自 `code/client/agent-onboarding.md` 迁入或链接替换 |
| `08-quality/acceptance/v1-*.md` | ✅ 已迁入 `08-quality/acceptance/` |
| `09-engineering/design-archive/` | ✅ 近期 design fable（23/24 等） |
| `06-operations/runbook.md` | 发版、回滚、migration 完整步骤 |
| `05-agent/mcp-tools-reference.md` | 每 tool JSON 示例 + 权限错误表 |

### 中优先级

| 建议路径 | 内容 |
|----------|------|
| `06-operations/deployment-saas.md` / `deployment-lan.md` | 分 profile 完整 runbook |
| `03-backend/authentication.md` | session cookie、登出、属性映射 |
| `04-frontend/ui-copy-and-interactions.md` | 全站错误页、表单校验文案 |
| `07-commercial/administrator-guide.md` | Observatory walkthrough |
| `07-commercial/end-user-faq.md` | 配额、投票、支持渠道 |
| `06-operations/monitoring-and-health.md` | 告警阈值、SLO |

### 低优先级 / 可选

| 建议路径 | 内容 |
|----------|------|
| `04-frontend/accessibility-and-i18n.md` | 无障碍与国际化（v1 未做） |
| `09-engineering/contributing.md` | 贡献指南、PR 规范 |
| `06-operations/security.md` | 威胁模型、渗透测试节奏 |
| `03-backend/api-openapi.md` | 自动生成 OpenAPI 说明 |
| `01-product/competitive-analysis.md` | 竞品对比（若需要） |

---

## v1 跨文档「不做」清单

| 项 | 说明 |
|----|------|
| SPA / 客户端路由 | SSR + query string |
| 非 admin 库内 record 枚举 UI | Stats + 深链 |
| Org / Grants 管理 UI | v1.1 |
| Export 批量导出 | v1.1+ |
| MCP `ma3_create_key` | v1.1 |
| Stripe 支付 | v1.1 |
| 撤销 API Key 文案/路由 | → 硬删除 |
| MCP search explain | 仅内部/Observatory |
| `ma3_ui_session` 签 key | 禁止 |

---

## 维护约定

1. **新功能** → 更新 [feature-index.md](01-product/feature-index.md) + 对应层文档 + 验收（若有）。  
2. **架构决策** → 新增 `02-architecture/decisions/ADR-NNN.md` + 更新 [architecture-decisions.md](02-architecture/architecture-decisions.md)。  
3. **IA/页面变更** → 只改 [information-architecture.md](04-frontend/information-architecture.md)。  
4. **发版** → [changelog.md](09-engineering/changelog.md) + [release-checklist.md](08-quality/release-checklist.md)。  
5. 文档状态：✅ 可指导实现；📝 需补充后方可作为验收真源。
