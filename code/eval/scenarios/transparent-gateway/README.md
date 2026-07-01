# transparent-gateway

Fix transparent HTTP proxy routing inside a privileged client container (iptables REDIRECT to sidecar proxy).

## Task

1. Call `ma3_context` with `target_product=ma3-eval`, `target_component=transparent-gateway`.
2. Sidecar `proxy` listens on `:3128`. Client uses iptables to redirect outbound HTTP to the proxy.
3. Fix `workspace/redirect.sh` (copied from `broken/`) — wrong port or chain.
4. From inside `client`, `curl http://httpbin.org/get` must succeed via transparent proxy.
5. Report reusable knowledge to ma3 if applicable.

Do **not** modify host iptables.
