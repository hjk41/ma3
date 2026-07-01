# compose-network-fix

Fix docker-compose service networking so the frontend can reach the backend by the correct hostname.

## Task

1. Call `ma3_context` with `target_product=ma3-eval`, `target_component=compose-network-fix`.
2. Fix `workspace/default.conf` (copied from `broken/`) — nginx upstream must use the compose service name.
3. `curl http://127.0.0.1:18081/` should return the backend response body.
4. Report reusable knowledge to ma3 if applicable.
