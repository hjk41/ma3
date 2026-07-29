# Acceptance Documents

> Chinese version: [README.zh.md](README.zh.md)

> **Source of truth**: this directory + [../acceptance-criteria.md](../acceptance-criteria.md)
> **Design reference**: [../../04-frontend/information-architecture.md](../../04-frontend/information-architecture.md)

## Document list

| Document | Scope | Gate |
|------|------|------|
| [v1-user-portal-ui.md](v1-user-portal-ui.md) | Post-login portal SSR UI (navigation, lists, batch actions, HTML invariants) | **Must run for every release** |
| [v1-self-service-onboarding.md](v1-self-service-onboarding.md) | Self-service registration + key issuance | Must run for every release |
| [v1-api-key-lifecycle.md](v1-api-key-lifecycle.md) | Keys UI/API | Must run for every release |
| [v1-display-name-registration.md](v1-display-name-registration.md) | Display name setup | Must run for every release |
| [v1-library-write-buffer.md](v1-library-write-buffer.md) | Buffered state machine | Must run for every release |
| [v1-user-portal.md](v1-user-portal.md) | Historical P1–P19 mapping (read-only archive) | — |
| [v1-ui-i18n-acceptance-gpt55.md](v1-ui-i18n-acceptance-gpt55.md) | UI i18n acceptance | — |
| [v1-personal-developer-journey.md](v1-personal-developer-journey.md) | Personal developer journey eval | — |

## Must run before release (portal UI)

```bash
cd code/server
.venv/bin/pytest tests/integration/test_user_portal*.py \
  tests/integration/test_portal_html_regression.py \
  tests/integration/test_display_name_registration.py \
  tests/integration/test_ui_i18n.py \
  -q --tb=short
```

**Pass criteria**: 0 failed; if any **R\*** (HTML regression) or **W\*** (record list) test fails, you must **not** report to the user that "the portal passed acceptance".

## Acceptance layers

| Layer | Tool | Coverage |
|------|------|------|
| L1 Automated HTML | pytest + TestClient | Routes, table header links, batch forms, copy, 403/302 |
| L2 Deployment smoke | `deploy/common/verify_ma3.sh` | healthz, anonymous pages, MCP tool count |
| L3 Browser E2E | `scripts/e2e_authing_ui.py` (Playwright) | Real Authing login, Keys forms |
| L4 Manual visual | Owner checklist (see the end of each document) | Layout spacing, mobile wrapping |

Interactions not covered by L1 **must** be re-tested at L3/L4; do not assume "integration tests passed, so there will be no UI bugs".
