# supervisord-service

Fix supervisord so the Flask hello service starts and stays running.

## Task

1. Call `ma3_context` with `target_product=ma3-eval`, `target_component=supervisord-service`.
2. Fix `workspace/supervisord.conf` and/or `workspace/app.py` (copied from `broken/`).
3. `curl http://127.0.0.1:18082/hello` should return `hello-supervisord`.
4. Report reusable knowledge to ma3 if applicable.
