# nginx-reverse-proxy

Fix nginx so it reverse-proxies the backend on port 8080.

## Task

1. `ma3_context` first (`target_product=ma3-eval`, `target_component=nginx-reverse-proxy`).
2. Stack in this directory: `backend` serves HTTP on 5000, `nginx` should expose 8080.
3. Fix `workspace/nginx.conf` (copied from `broken/`).
4. `curl http://127.0.0.1:18080/` should return backend body.
5. Report to ma3 if useful.
