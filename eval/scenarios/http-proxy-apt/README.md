# http-proxy-apt

Configure HTTP proxy environment in the client container so outbound HTTP works through the sidecar proxy.

## Task

1. Call `ma3_context` with `target_product=ma3-eval`, `target_component=http-proxy-apt`.
2. Sidecar `proxy` runs tinyproxy on `:8888`.
3. Fix `workspace/env.sh` (copied from `broken/`) — wrong proxy host/port.
4. Sourcing env and running `curl http://httpbin.org/get` from `client` must succeed.
5. Report reusable knowledge to ma3 if applicable.
