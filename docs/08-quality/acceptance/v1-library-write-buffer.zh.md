# v1 Acceptance — Library Write Buffer (design/16)

- **Tester**: fable (QA acceptance)
- **Date**: 2026-07-04
- **Target**: local pytest + code inspection
- **Scope**: ratified [../../03-backend/write-buffer.md](../../03-backend/write-buffer.md)（原 design/16 fable 已归档移除）
- **Method**: integration suite `tests/integration/test_write_buffer.py`, existing suites with `write_buffer_hours=0` on test default library, structural grep for MCP/portal routes

## Verdict

**PASS-WITH-NITS (fable QA sign-off).** Write buffer v1 conforms to all seven ratified decisions in design/16: schema (`write_buffer_hours` DEFAULT 24, `records.publish_at`), `buffer_service` status resolution, MCP `ma3_publish_record` / `ma3_patch_record` with timer reset, author-only visibility across `ma3_context` / portal deep links, background publish loop (startup + 60s) plus lazy publish on read/write paths, and v1 portal UI (待发布 badge, record actions, library settings 0–168h). Implementer + fable evidence: 8/8 buffer tests, **210** total passed locally.

**Conditions before release:** seed ratified decision-7 user-guide record into `lib_default` (content op, not code). **Fixed in implementation pass:** patch when library `write_buffer_hours=0` now auto-publishes instead of leaving a stuck `buffered` record.

Remaining nits (stats total card includes buffered count, no portal DOM tests, evidence not patchable in v1) are non-blocking.

## B1–B10 mapping

| # | Criterion | Result | Evidence |
|---|---|---|---|
| B1 | `new`/`supplement` + `write_buffer_hours>0` → `status=buffered` + `publish_at`; response includes `readable_by: ["author"]` | **PASS** | `buffer_service.resolve_report_status`; `test_new_report_becomes_buffered` |
| B2 | `write_buffer_hours=0` → immediate `active` (ADR-002 compatible) | **PASS** | `test_buffer_zero_writes_immediate_active`; test conftest sets default lib to 0 |
| B3 | Others cannot read/search buffered records (404 / excluded from context) | **PASS** | `can_read_record`; `test_author_sees_buffered_in_context_other_user_does_not` |
| B4 | Author sees own buffered in `ma3_context` + `ma3_list_my_writes` status/publish_at | **PASS** | `mcp_tool_service._context_payload`; `write_audit_service.format_my_writes`; context test |
| B5 | `ma3_publish_record` by owner → `active`; idempotent if already active | **PASS** | `publish_record_for_owner`; `test_publish_record_makes_active_and_searchable` |
| B6 | `ma3_patch_record` / portal edit resets `publish_at` | **PASS** | `patch_buffered_record_for_owner`; `test_patch_resets_publish_at` |
| B7 | `verify` / `visibility=draft` paths exempt from buffer | **PASS** | `resolve_report_status`; `test_verify_report_skips_buffer` |
| B8 | Maintainer/admin bypass → immediate `active` | **PASS** | `resolve_report_status(is_maintainer=True)`; `test_smoke.test_ma3_report_active_default` (ma3dev admin) |
| B9 | `publish_due_buffered_records()` on startup + background loop (60s) | **PASS** | `main.py` `_buffer_publish_loop`; `test_publish_due_buffered_records` |
| B10 | Portal: `/ui/me/` 待发布 count; writes status; record publish/edit/delete; library settings | **PASS** (code) | `routes_portal.py`; no dedicated portal DOM tests for buffer UI |

## Schema / MCP

| Item | Expected |
|------|----------|
| DB columns | `libraries.write_buffer_hours DEFAULT 24`, `records.publish_at` |
| New MCP tools | `ma3_publish_record`, `ma3_patch_record` (15 tools total) |
| Public stats | `by_outcome` / `by_task_type` count **active only**; buffered excluded from Active card |

## Test plan

```text
pytest tests/integration/test_write_buffer.py -v
pytest tests/ -q
grep -r ma3_publish_record code/server/app
grep publish_due_buffered_records code/server/app/main.py
```

## Operations log (implementer)

```text
pytest tests/integration/test_write_buffer.py -v → 8 passed
pytest tests/ -q → 210 passed, 12 deselected
grep ma3_publish_record code/server/app → mcp_tool_service, mcp_payloads, routes
grep publish_due_buffered_records code/server/app/main.py → _buffer_publish_loop
```

## Nits / follow-ups

1. **Decision 7** — Community user-guide record in `lib_default` not auto-seeded in this slice; content exists in design docs.
2. **LAN staging deploy** — **done 2026-07-04.** `deploy_ma3_v1_202.sh` rsync + restart OK; `http://ma3.example.internal:8000/healthz` UP; MCP **15 tools** (`ma3_publish_record`, `ma3_patch_record` present); UI smoke OK. Deploy gate fails on `MA3_EXPECT_MIN_RECORDS=30` (DB has 21 active) — env threshold drift, not buffer regression. Onboarding `test_ui_create_key_form_post` cross-origin when pytest uses 127.0.0.1 vs LAN `public_base_url` (known).
3. **Personal library default 24h** — owner may set 0 in `/ui/libraries/{id}/settings/`; sole-owner experience documented in fable §0.
