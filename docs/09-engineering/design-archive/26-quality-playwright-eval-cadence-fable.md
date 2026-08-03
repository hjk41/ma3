# Design: Issue #7 (Playwright portal) + Issue #8 (Agent eval cadence)

> Author: Fable design session (2026-08-03). Composer implements.
> Source agent: design lead for GitHub #7 / #8.

See the full acceptance checklists and file lists in the conversation transcript;
this archive captures the ratified decisions for traceability.

## Decisions

| Topic | Choice |
|-------|--------|
| Portal E2E Tier A | pytest + Playwright, local-auth, every PR (`e2e-portal` job) |
| Portal E2E Tier B | existing `e2e_authing_ui.py`, nightly + secrets-gated SKIP |
| Agent eval cadence | Checklist-driven weekly on LAN host (not GitHub cron) |
| Weekly subset | claude × T2 / T4 / T5, carrier `mihomo-proxy` |
| Pre-release | Unchanged T0–T5 × 3 agents |
| Entry script | `code/eval/scripts/run_behavior_subset.sh` |

Full case tables P1–P12 and acceptance checklists: implement from Fable design message in session.
