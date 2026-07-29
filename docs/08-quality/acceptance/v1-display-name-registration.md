# v1 Acceptance — Display Name Registration

> Chinese version: [v1-display-name-registration.zh.md](v1-display-name-registration.zh.md)

- **Date**: 2026-07-05
- **Design**: [../../04-frontend/display-name-registration.md](../../04-frontend/display-name-registration.md)
- **Suite**: `tests/integration/test_display_name_registration.py`

## Verdict

**PASS** — all three constraints are covered by automated integration tests.

## Criteria

| # | Constraint | Result | Test(s) |
|---|------|--------|---------|
| A1 | **Prompt to set display name at registration**: Authing callback → `/ui/me/setup/`; setup page contains welcome copy and "globally unique / cannot be changed"; before completion `/ui/me/` and `/ui/keys/` redirect, API returns 403 | **PASS** | `test_registration_callback_redirects_new_user_to_setup`, `test_registration_setup_page_prompts_display_name`, `test_portal_blocks_other_pages_until_display_name_set`, `test_api_keys_json_blocked_until_display_name_set` |
| A2 | **Can only be set once**: first POST to setup succeeds and locks; subsequent POSTs to setup/settings both return 400; locked users GET setup redirects to next; settings page has no form | **PASS** | `test_display_name_can_only_be_set_once` |
| A3 | **Display names cannot duplicate**: same name as an existing user is rejected; case-insensitive (Alice vs alice); failures do not lock | **PASS** | `test_display_name_rejects_duplicate`, `test_display_name_uniqueness_is_case_insensitive` |

## Related tests

- `tests/integration/test_set_display_name.py` — MCP / personal library / Authing resync details
- `tests/unit/test_user_display_name.py` — validation functions and DB layer

## Run

```bash
cd code/server && pytest tests/integration/test_display_name_registration.py -v
```
