# mihomo-proxy

Fix the mihomo proxy inside the Docker scenario so HTTP proxy works.

## Task

1. Call `ma3_context` with `target_product=ma3-eval`, `target_component=mihomo-proxy`.
2. The stack is running in this directory. Enter the `client` container or use `docker compose exec`.
3. Fix `broken/config.yaml` — mixed-port, proxy-groups, or rules are wrong.
4. Subscription URL is injected at runtime via env `MIHOMO_SUBSCRIPTION_URL` (do not hardcode).
5. After fix, `curl -x http://mihomo:7890 http://httpbin.org/get` should succeed from inside `client`.
6. If you learn something reusable, `ma3_validate` then `ma3_report`.

Do **not** change host `/etc` or global proxy settings.
