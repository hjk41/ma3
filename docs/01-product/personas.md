# Roles & Personas

> Chinese version: [personas.zh.md](personas.zh.md)

> **Status**: Draft — product needs to add scenario stories and priorities

## Role Overview

| Role | Identity criteria | Core goals | Primary surface |
|------|----------|----------|----------|
| **Individual developer (contributor)** | Authing user + personal library + API key | Self-serve agent onboarding; write back experience; manage own keys and contributions | User portal `/ui/me/*`, API Keys |
| **Agent (contributor)** | MCP client holding `X-API-Key` | `ma3_context` before tasks; `ma3_report` after tasks; can explain failures and retry | MCP + policy |
| **Agent (maintainer)** | Key with maintainer grant | Flag invalid, review drafts, curate cases | MCP `ma3_review_record` etc. |
| **Human — knowledge base maintainer** | Library admin / org admin / product admin | Supervise agent maintainers; remove privacy/values-violating content | Portal (limited) + Observatory |
| **Org admin** | `org_members.role=admin` | Members, org libraries, visibility (v1.1 UI) | `/ui/orgs/*` (v1.1) |
| **Product admin** | `MA3_AUTH_ADMIN_USERS` | Global health, enumeration, operations | Observatory |
| **Anonymous visitor** | No session | Browse Community Library **Stats only** | `/ui/libraries/lib_default/` |

## Role Overlap

- A product admin **is also** a regular user; Observatory is an extra capability, not a replacement for the portal.
- `is_admin` does **not automatically grant** org/library business admin rights (global observability is separate from business administration).

## To Be Added

- [ ] Typical day / typical tasks per role (user stories)
- [ ] Free vs paid persona differences (Pro/Team)
- [ ] B2B team onboarding persona (v1.1)
