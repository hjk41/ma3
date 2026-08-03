# Design backlog

> Chinese version: [design-backlog.zh.md](design-backlog.zh.md)

> Migrated from the former repo-root `todo.md` (2026-07-03 pitch vs PITCH.md gap review).
> These are **planned design issues, not commitments** —
> no schedule, no delivery promise; they become ADRs / design docs only after discussion is settled.
>
> **Source of truth**: the GitHub Issues below (this file is an index only).

## Open design topics

| ID | Issue | Summary |
|----|-------|------|
| B1 | https://github.com/hjk41/ma3/issues/1 | Maintainer / compliance deletion of others' content |
| B2 | https://github.com/hjk41/ma3/issues/2 | Automated maintainer agent |
| B3 | https://github.com/hjk41/ma3/issues/3 | Org members / SSO / SCIM / seats |
| B4 | https://github.com/hjk41/ma3/issues/4 | Integrator / delegated sub-identities (B2B2C) |

Recreate issues: `bash scripts/file_design_backlog_issues.sh` (creates new issues without dedup — use carefully).


## Ops / quality debt (continuous improvement)

| ID | Issue | Summary |
|----|-------|------|
| O1 | ~~https://github.com/hjk41/ma3/issues/5~~ | **Closed** — Phase 0–3 metrics/alerting/SLOs shipped |
| O2 | ~~https://github.com/hjk41/ma3/issues/6~~ | **Closed** — production runbook filled (EN + zh) |
| O3 | ~~https://github.com/hjk41/ma3/issues/7~~ | **Closed** — Playwright Tier A on PR + Authing nightly |
| O4 | ~~https://github.com/hjk41/ma3/issues/8~~ | **Closed** — weekly claude×T2/T4/T5 checklist cadence |

## Already decided (for traceability; documented elsewhere)

- **Anti-deletion as a paid feature**: only paid orgs may enable recycle/restore on libraries they **own**; default is hard delete with no restore. → ADR-013 / design-10
- **All reads and writes require a key**: remove anonymous-read wording; sync across docs. → ADR-011 + pitch/design sync
- **Do not force one key ↔ one library**: cross-library / cross-org isolation is an enterprise admin concern; the server does not hard-isolate. → ADR-011 notes
- **Library over capacity → read-only**: past the cap, that library forbids writes but stays readable. → ADR-012 / design-09
