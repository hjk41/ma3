# Monitoring and Health Checks

> Chinese version: [monitoring-and-health.zh.md](monitoring-and-health.zh.md)

> TODO(v1.1): add metrics/alerting/SLO (see checklist at the end); existing endpoints and doctor checks below.

## Existing Endpoints

| Endpoint / tool | Purpose |
|-------------|------|
| `GET /healthz` | liveness; exposes version, commit, instance |
| MCP `ma3_doctor` | auth, DB, embedding, legacy keys, billing schema (Phase B) |
| MCP `ma3_whoami` | runtime key/principal/quota snapshot |

## What doctor Should Report (target)

- `anonymous_mcp_enabled: false` (without an API key, `tools/call` returns authentication required except for `ma3_whoami`; anonymous callers have no read access to Community records)
- `api_keys_table: ok`
- `auth_admin_configured: ok` (when Authing is on)
- `billing_schema_ok` (Phase B)
- `usage_rollup_lag` (Phase B)
- `legacy_env_writer_keys: deprecated` (if still set)

## MCP quota Block

Successful read responses may include `structuredContent.quota` — the Agent policy may require relaying `warnings`.

> TODO(v1.1):
>
> - Prometheus metrics (if any)
> - Alert thresholds (read quota 80%, publish job lag)
> - Structured log field conventions
> - SLO / SLA definitions (formal SLA planned for v1.1+)
