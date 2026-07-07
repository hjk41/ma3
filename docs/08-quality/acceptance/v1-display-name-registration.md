# v1 Acceptance — Display Name Registration

- **Date**: 2026-07-05
- **Design**: [../../04-frontend/display-name-registration.md](../../04-frontend/display-name-registration.md)
- **Suite**: `tests/integration/test_display_name_registration.py`

## Verdict

**PASS** — 三项约束均有自动化集成测试覆盖。

## Criteria

| # | 约束 | Result | Test(s) |
|---|------|--------|---------|
| A1 | **注册时提示设定显示名**：Authing 回调 → `/ui/me/setup/`；setup 页含欢迎文案与「全局唯一 / 不可修改」；未完成前 `/ui/me/`、`/ui/keys/` 重定向，API 403 | **PASS** | `test_registration_callback_redirects_new_user_to_setup`, `test_registration_setup_page_prompts_display_name`, `test_portal_blocks_other_pages_until_display_name_set`, `test_api_keys_json_blocked_until_display_name_set` |
| A2 | **只能设定一次**：首次 POST setup 成功并锁定；再次 POST setup/settings 均 400；已锁定用户 GET setup 跳转 next；settings 无表单 | **PASS** | `test_display_name_can_only_be_set_once` |
| A3 | **显示名不能重复**：与已有用户同名拒绝；大小写不敏感（Alice vs alice）；失败不锁定 | **PASS** | `test_display_name_rejects_duplicate`, `test_display_name_uniqueness_is_case_insensitive` |

## Related tests

- `tests/integration/test_set_display_name.py` — MCP / 个人库 / Authing resync 细节
- `tests/unit/test_user_display_name.py` — 校验函数与 DB 层

## Run

```bash
cd code/server && pytest tests/integration/test_display_name_registration.py -v
```
