# ADR-008 — Maintainer: humans and agents jointly maintain the knowledge community

> Chinese version: [008-maintainer-human-or-agent.zh.md](008-maintainer-human-or-agent.zh.md)

## Status

Accepted (2026-07-01)

## Context

An ma3 library is analogous to an **online knowledge community**: beyond agents contributing verified knowledge, **maintainers** are also needed for annotation, correction, curation, and summarization.

**A maintainer can be either a human or a privileged agent** — modeled on the responsibilities of open-source *maintainers* and forum *moderators*, without using an obscure term like "curator."

**Terminology distinctions**:

| Term | Meaning |
|------|------|
| **Maintainer** | A runtime role: a human **or** an agent that governs library content |
| **Product owner** | The person making design and documentation decisions (not a product role name) |
| **Manager / Admin** | Platform back-office for org, seats, SSO, etc. (v1.1+, separate from content maintainers) |

## Decision

### 1. Role: Maintainer

| Maintainer capability | Human (Observatory UI) | Agent (MCP) |
|------------|---------------------|--------------|
| Browse case / record / explain | ✓ v1 | ✓ read-class MCP tools |
| Mark record **invalid** | ✓ v1 (ADR-007) | ✓ v1 — review / invalid semantics |
| Approve / reject **draft** | v1.1 UI; MCP in v1 | ✓ `ma3_list_drafts` / `ma3_review_record` |
| Case **summarization / annotation** | v1.1+ | v1.1+ |
| Community-level **knowledge curation** (merging duplicate cases, etc.) | Future | Future — high-privilege maintainer agents |

### 2. Maintenance layers: agents execute, humans exercise judgment

```text
Agent contributor ── writes back ──► verified knowledge
Agent maintainer ── routine maintenance ──► flags stale entries, curates, suggests (at scale)
Human / team maintainer ── oversight and correction ──► corrects agent maintainer misjudgments
                              ──► clears content that should not exist (privacy, values/compliance)
```

- **Agent maintainers**: automated, high-frequency, auditable; their actions **can be overturned or corrected by humans**.
- **Human and team maintainers**: the library's **ultimate responsible party**; they **correct** agent maintainers, and handle judgment calls agents cannot make alone (privacy, organizational values, compliance red lines).
- **Managers (Admin)**: org members and subscriptions; do not substitute for content maintenance duties.

Writes default to **active** (ADR-002); routine maintenance scales via agents, while **trust and compliance are backstopped by humans**.

### 3. Scope of human/team maintainer corrections (must be supported)

| Category | Example | Typical action |
|------|------|----------|
| **Correcting an agent maintainer** | Mistakenly marked invalid, mistakenly merged case | Restore status, revoke relation |
| **Privacy and sensitive information** | Tokens, secrets, personally identifiable information | Invalidate or redact the record |
| **Values / compliance** | Content that violates team guidelines or policy | Invalidate + optional library-level policy note |

Every governance action taken by an agent maintainer should be **auditable** (op log) for human review and correction.

### 4. Permissions

- **Reader agent**: read
- **Writer agent**: + write-back
- **Agent maintainer** (`library_maintainer`): review, mark invalid, curation suggestions; actions can be revoked by a human
- **Human maintainer** (`library_admin` or higher): **overrides** agent maintainer decisions; **final deletion authority** for privacy/values matters

The Observatory UI and MCP share **the same domain logic**; human maintainers take precedence over agent maintainers.

### 5. v1 scope

- External pitch and documentation consistently use **Maintainer**
- v1: agents participate in routine maintenance via MCP; Observatory lets **human maintainers** browse, mark invalid, and **revoke/correct agent maintainer actions** (minimum: invalid + a visible op log)
- v1.1+: case summarization, agent maintainer action queue, human review workbench, library values/privacy policy templates

## Consequences

### Positive

- The term feels natural; technical users are familiar with "maintainer"
- A clear boundary against "manager (org Admin)"
- Agent maintainers improve efficiency **without humans losing control**
- Acceptable to enterprises: there is a **human party of final responsibility** for privacy and values

### Negative

- Agent maintainer mistakes require an op log, revocation API, and ACL
- Policy must distinguish keys for Writer / agent maintainer / human maintainer
- An overly deep human review queue could offset the gains from automation — product needs to tune the threshold

### Related

- ADR-002, ADR-005, ADR-007
- pitch.md §Core users
