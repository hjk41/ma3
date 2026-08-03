# ma3 Documentation Map

> Chinese version: [README.zh.md](README.zh.md)

> **Structure version**: 2026-07-06
> **Note**: This directory is the **single systematic documentation entry point** for ma3. It is organized as "Product → Architecture → Implementation → Delivery"; ✅ marks documents with substantial content, 📝 marks placeholders / documents pending completion.

## Language policy

- **English is the default language** for all documents in this tree: every `foo.md` is the English (canonical) version.
- **Chinese versions are preserved as siblings** named `foo.zh.md` (e.g. this page's Chinese version is [README.zh.md](README.zh.md)).
- Links between documents always target the default English file (`foo.md`).

---

## Reading path (newcomers)

1. [01-product/pitch.md](01-product/pitch.md) + [vision.md](01-product/vision.md) — why ma3 exists
2. [02-architecture/system-overview.md](02-architecture/system-overview.md) — system shape
3. [01-product/user-journeys.md](01-product/user-journeys.md) — how it is used
4. [05-agent/getting-started.md](05-agent/getting-started.md) — agent integration
5. [04-frontend/information-architecture.md](04-frontend/information-architecture.md) — post-login UI

---

## 1. Product (01-product)

| Document | Status | Description |
|------|------|------|
| [pitch.md](01-product/pitch.md) | ✅ | External product narrative |
| [vision.md](01-product/vision.md) | ✅ | Vision, principles, success criteria |
| [problem-domain.md](01-product/problem-domain.md) | ✅ | Domain model, quality states |
| [personas.md](01-product/personas.md) | 📝 | Persona profiles (user stories missing) |
| [user-journeys.md](01-product/user-journeys.md) | ✅ | End-to-end journeys |
| [roadmap.md](01-product/roadmap.md) | ✅ | v1 / v1.1 / not doing |
| [feature-index.md](01-product/feature-index.md) | ✅ | Feature → spec → acceptance index |

---

## 2. Architecture (02-architecture)

| Document | Status | Description |
|------|------|------|
| [system-overview.md](02-architecture/system-overview.md) | ✅ | Modules, MCP contract, deployment profiles |
| [external-integrations.md](02-architecture/external-integrations.md) | 📝 | Authing/Postgres/HF integrations (production topology missing) |
| [data-model.md](02-architecture/data-model.md) | ✅ | ER, state machine overview |
| [architecture-decisions.md](02-architecture/architecture-decisions.md) | ✅ | ADR index + full texts in [decisions/](02-architecture/decisions/) |

---

## 3. Backend (03-backend)

| Document | Status | Description |
|------|------|------|
| [authentication.md](03-backend/authentication.md) | 📝 | Authing session, setup gating |
| [authorization-and-libraries.md](03-backend/authorization-and-libraries.md) | ✅ | ACL, grants, visibility |
| [billing-and-quotas.md](03-backend/billing-and-quotas.md) | ✅ | Plan schema, enforcement design |
| [writes-audit-and-deletion.md](03-backend/writes-audit-and-deletion.md) | ✅ | report_kind, deletion, tombstones |
| [write-buffer.md](03-backend/write-buffer.md) | ✅ | Buffered state, publish |
| [search-and-ranking.md](03-backend/search-and-ranking.md) | ✅ | GTN algorithm and configuration |
| [background-jobs.md](03-backend/background-jobs.md) | 📝 | Scheduled jobs (operational details missing) |
| [api-overview.md](03-backend/api-overview.md) | 📝 | Route overview (OpenAPI missing) |

---

## 4. Frontend (04-frontend)

| Document | Status | Description |
|------|------|------|
| [information-architecture.md](04-frontend/information-architecture.md) | ✅ | Routes, top bar, list shell, page specs |
| [page-specifications.md](04-frontend/page-specifications.md) | ✅ | Page specification index |
| [portal-permissions.md](04-frontend/portal-permissions.md) | ✅ | Permissions, Stats/Enumerate, 403 |
| [visual-design-system.md](04-frontend/visual-design-system.md) | ✅ | GitHub light tokens, components |
| [ui-copy-and-interactions.md](04-frontend/ui-copy-and-interactions.md) | 📝 | Copy and interactions (error pages missing) |
| [api-keys-ui-and-api.md](04-frontend/api-keys-ui-and-api.md) | ✅ | Keys list/detail/API |
| [display-name-registration.md](04-frontend/display-name-registration.md) | ✅ | One-time display name at setup |

---

## 5. Agent integration (05-agent)

| Document | Status | Description |
|------|------|------|
| [getting-started.md](05-agent/getting-started.md) | ✅ | Self-service keys, first-login library creation |
| [mcp-tools-reference.md](05-agent/mcp-tools-reference.md) | 📝 | Tool reference (full examples missing) |
| [error-handling.md](05-agent/error-handling.md) | ✅ | MCP error self-correction contract |
| [policy-and-client-sync.md](05-agent/policy-and-client-sync.md) | 📝 | policy/sync (IDE examples pending) |

> The HTTP source of truth for operational steps still lives in `code/client/agent-onboarding.md` (**to be migrated** into this directory or replaced with a link).

---

## 6. Operations (06-operations)

| Document | Status | Description |
|------|------|------|
| [deployment.md](06-operations/deployment.md) | 📝 | Profile overview |
| [self-hosting.md](06-operations/self-hosting.md) | ✅ | Compose self-hosting (bootstrap / local accounts / OIDC) |
| [self-host-first-run-guide.md](06-operations/self-host-first-run-guide.md) | In design | First-run guide: create admin → checklist → daily use |
| [deployment-authing.md](06-operations/deployment-authing.md) | ✅ | Authing console + env |
| [runbook.md](06-operations/runbook.md) | ✅ | Release/rollback/migration notes/logs/on-call |
| [monitoring-and-health.md](06-operations/monitoring-and-health.md) | ✅ | Probe, metrics, Alertmanager, SLO-1–3 |
| [security.md](06-operations/security.md) | 📝 | Security summary (threat model missing) |

---

## 7. Commercial and operations (07-commercial)

| Document | Status | Description |
|------|------|------|
| [pricing-and-plans.md](07-commercial/pricing-and-plans.md) | ✅ | User-facing plan summary |
| [administrator-guide.md](07-commercial/administrator-guide.md) | 📝 | Observatory/operations guide |
| [end-user-faq.md](07-commercial/end-user-faq.md) | 📝 | End-user FAQ draft |
| [legal/](07-commercial/legal/README.md) | 📝 | Terms of service / privacy / data retention (drafts, not lawyer-reviewed) |

---

## 8. Quality and delivery (08-quality)

| Document | Status | Description |
|------|------|------|
| [acceptance-criteria.md](08-quality/acceptance-criteria.md) | 📝 | Acceptance index (full texts to be migrated) |
| [test-strategy.md](08-quality/test-strategy.md) | ✅ | Test layering and gates |
| [release-checklist.md](08-quality/release-checklist.md) | 📝 | Release checklist draft |

---

## 9. Engineering collaboration (09-engineering)

| Document | Status | Description |
|------|------|------|
| [glossary.md](09-engineering/glossary.md) | ✅ | Terminology and deprecated terms |
| [repository-layout.md](09-engineering/repository-layout.md) | 📝 | Code layout summary |
| [changelog.md](09-engineering/changelog.md) | 📝 | Changelog (versioning cadence to be established) |
| [design-backlog.md](09-engineering/design-backlog.md) | ✅ | Topics awaiting design (migrated from root todo.md; not commitments) |

> [design-archive/README.md](09-engineering/design-archive/README.md) contains **historical design decision summaries** only; it is not an implementation source of truth.

---

## Currently missing documents (to be created or migrated)

The following document types **should exist** in the structure but have no standalone version yet, or only placeholders:

### High priority

| Suggested path | Content |
|----------|------|
| `02-architecture/decisions/` | ✅ Migrated | 15 ADR texts (001–015) |
| `05-agent/agent-onboarding.md` | Migrate from `code/client/agent-onboarding.md` or replace with a link |
| `08-quality/acceptance/v1-*.md` | ✅ Migrated into `08-quality/acceptance/` |
| `09-engineering/design-archive/` | ✅ Recent design fables (23/24 etc.) |
| `06-operations/runbook.md` | ✅ Release, rollback, schema notes, logs (issue #6) |
| `05-agent/mcp-tools-reference.md` | Per-tool JSON examples + permission error table |

### Medium priority

| Suggested path | Content |
|----------|------|
| `06-operations/deployment-saas.md` / `deployment-lan.md` | Complete per-profile runbooks |
| `03-backend/authentication.md` | Session cookie, logout, attribute mapping |
| `04-frontend/ui-copy-and-interactions.md` | Site-wide error pages, form validation copy |
| `07-commercial/administrator-guide.md` | Observatory walkthrough |
| `07-commercial/end-user-faq.md` | Quotas, voting, support channels |
| `06-operations/monitoring-and-health.md` | ✅ Phase 0–3 shipped (issue #5) |

### Low priority / optional

| Suggested path | Content |
|----------|------|
| `04-frontend/accessibility-and-i18n.md` | Accessibility and internationalization (not done in v1) |
| `09-engineering/contributing.md` | Contribution guide, PR conventions |
| `06-operations/security.md` | Threat model, penetration testing cadence |
| `03-backend/api-openapi.md` | Auto-generated OpenAPI notes |
| `01-product/competitive-analysis.md` | Competitive analysis (if needed) |

---

## v1 cross-document "not doing" list

| Item | Note |
|----|------|
| SPA / client-side routing | SSR + query string |
| Non-admin in-library record enumeration UI | Stats + deep links |
| Org / Grants management UI | v1.1 |
| Bulk export | v1.1+ |
| MCP `ma3_create_key` | v1.1 |
| Stripe payments | v1.1 |
| "Revoke API key" copy/routes | → hard delete |
| MCP search explain | Internal/Observatory only |
| `ma3_ui_session` signing keys | Forbidden |

---

## Maintenance conventions

1. **New feature** → update [feature-index.md](01-product/feature-index.md) + the corresponding layer document + acceptance (if any).
2. **Architecture decision** → add `02-architecture/decisions/ADR-NNN.md` + update [architecture-decisions.md](02-architecture/architecture-decisions.md).
3. **IA/page changes** → edit only [information-architecture.md](04-frontend/information-architecture.md).
4. **Release** → [changelog.md](09-engineering/changelog.md) + [release-checklist.md](08-quality/release-checklist.md).
5. Document status: ✅ can guide implementation; 📝 needs completion before serving as an acceptance source of truth.
