# claude-deepseek-byok

Configure Claude Code with DeepSeek BYOK inside an isolated workspace HOME.

## Task

1. Call `ma3_context` with `target_product=ma3-eval`, `target_component=claude-deepseek-byok`.
2. Fix `workspace/.claude/settings.json` (copied from `broken/`).
3. `verify.sh` checks that settings point at DeepSeek and a minimal API probe succeeds.
4. Report reusable knowledge to ma3 if applicable.

Use `DEEPSEEK_API_KEY` from the environment — never hardcode secrets.
