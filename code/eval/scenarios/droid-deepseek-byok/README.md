# droid-deepseek-byok

Configure Factory Droid with DeepSeek BYOK inside an isolated workspace.

## Task

1. Call `ma3_context` with `target_product=ma3-eval`, `target_component=droid-deepseek-byok`.
2. Fix `workspace/.factory/settings.json` (copied from `broken/`).
3. Settings must use DeepSeek OpenAI-compatible API with thinking disabled.
4. Report reusable knowledge to ma3 if applicable.

Use `DEEPSEEK_API_KEY` from the environment — never hardcode secrets.
