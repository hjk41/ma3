# Acceptance Criteria

> Chinese version: [acceptance-criteria.zh.md](acceptance-criteria.zh.md)

> **Full portal UI acceptance (as of 2026-07-06)**: [acceptance/v1-user-portal-ui.md](acceptance/v1-user-portal-ui.md) — **must run for every release**
> **Index and commands**: [acceptance/README.md](acceptance/README.md)

## Index

| Version | Topic | File | Status |
|------|------|------|------|
| v1 | **Portal UI (SSR + HTML regression)** | [acceptance/v1-user-portal-ui.md](acceptance/v1-user-portal-ui.md) | ✅ Source of truth |
| v1 | Self-service onboarding | [acceptance/v1-self-service-onboarding.md](acceptance/v1-self-service-onboarding.md) | Exists |
| v1 | API key lifecycle | [acceptance/v1-api-key-lifecycle.md](acceptance/v1-api-key-lifecycle.md) | Exists |
| v1 | Display name registration | [acceptance/v1-display-name-registration.md](acceptance/v1-display-name-registration.md) | Exists |
| v1 | User portal P1–P19 (archived) | [acceptance/v1-user-portal.md](acceptance/v1-user-portal.md) | Mapped to v1-user-portal-ui |
| v1 | Write buffer | [acceptance/v1-library-write-buffer.md](acceptance/v1-library-write-buffer.md) | PASS-WITH-NITS |
| v1 | Personal developer journey | [acceptance/v1-personal-developer-journey.md](acceptance/v1-personal-developer-journey.md) | Exists |

## Hard release gate (portal)

```bash
cd code/server
.venv/bin/pytest tests/integration/test_user_portal*.py \
  tests/integration/test_portal_html_regression.py \
  tests/integration/test_display_name_registration.py -q
```

If any **R-series (HTML invariants)** test fails → sign-off is not allowed.

## Portal acceptance item summary

| Series | Scope |
|------|------|
| **R1–R5** | Table header links not escaped, form errors do not return JSON |
| **N1–N7** | Routing, top bar, subnav, Observatory 403 |
| **M1–M5** | Overview stats, no Principal ID leakage |
| **S1–S3** | Settings read-only |
| **W1–W20** | Record list sort/filter/batch/select-all/deleted copy |
| **V1–V4** | Votes list |
| **L/D/K** | Libraries, detail, Keys (see the dedicated docs) |

Full table in [acceptance/v1-user-portal-ui.md](acceptance/v1-user-portal-ui.md).

## To be added

- [ ] Release sign-off template (who signs, which ACs must pass)
- [ ] Agent behavior acceptance T1–T5 ([testing/release-agent-behavior-tests.md](../testing/release-agent-behavior-tests.md))
