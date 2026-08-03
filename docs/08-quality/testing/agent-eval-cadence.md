# Agent eval cadence (weekly subset)

> Chinese version: [agent-eval-cadence.zh.md](agent-eval-cadence.zh.md)

Design lead: Fable ([archive](../../09-engineering/design-archive/26-quality-playwright-eval-cadence-fable.md)).  
Full release gate (T0–T5 × 3 agents): [release-agent-behavior-tests.md](release-agent-behavior-tests.md).

## Decision

| Topic | Choice |
|-------|--------|
| Cadence | **Weekly** (target: Monday), **maintainer checklist on LAN host** |
| GitHub cron | **No** — runners cannot reach LAN Docker/agent profiles |
| Weekly subset | **claude × T2, T4, T5** (carrier `mihomo-proxy`) |
| Pre-release | Unchanged full **T0–T5 × claude/codex/hermes** gate |
| Entry script | `code/eval/scripts/run_behavior_subset.sh` |

### Why this subset

- **T5**: deterministic curl key auth (fast signal).
- **T4**: MCP error self-correction (one agent run).
- **T2**: upvote-dedup (highest-value behavior + Docker scenario).
- **T0/T1/T3**: stay pre-release-only (onboarding / version bump / planted fakes).

## How to run

```bash
# Smoke (no agents/secrets required) — always safe on a laptop
bash code/eval/scripts/run_behavior_subset.sh --dry-run

# Real weekly run (LAN host with profiles + secrets + local ma3)
export MA3_BASE_URL=http://127.0.0.1:8000
bash code/eval/scripts/run_behavior_subset.sh --agent claude --tests T2,T4,T5
```

Reports (gitignored): `code/eval/results/behavior/<UTC>-<agent>/report.{json,md}`.

Optional LAN systemd timer is allowed but **not required** for acceptance.

## Flake vs product regression

1. On FAIL of T2/T4: clear agent memory, reset scenario, **retry once**.
2. Retry PASS → **FLAKY** (non-blocking). Same test FLAKY two consecutive weeks → open a GitHub issue.
3. Retry FAIL → **FAIL** = product regression → open issue labeled `agent-behavior-regression` same day; blocks next release until fixed/waived.
4. **T5** has no flake retry — any FAIL is a product regression.

## Run log

| Date (UTC) | Host | Agent | T2 | T4 | T5 | Notes |
|------------|------|-------|----|----|----|-------|
| 2026-07-03 | LAN (archived) | claude/codex/hermes | PASS* | PASS* | PASS* | Full T0–T5 × 3 agents **18/18** recorded in release-agent-behavior-tests §4 |
| 2026-08-03 | hct-ThinkPad-P1-Gen-2 | claude | SKIPPED | SKIPPED | SKIPPED | `--dry-run` smoke; `results/behavior/2026-08-03T010723Z-claude/`; not a matrix pass |

\*Full-matrix cells; weekly subset uses the same T2/T4/T5 definitions.
