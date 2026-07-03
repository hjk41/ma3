from __future__ import annotations

from fastapi import HTTPException

from app.models.mcp_payloads import Ma3ReportPayload
from app.services.record_read_service import format_record_for_read
from app.services.redaction_service import redact_text
from app.services.report_store_service import validate_report_write
from app.services.search_context_service import SearchContext, context_boost


def test_redact_sk_proj_key():
    text = "token sk-proj-abc123XYZ_abcdefghij"
    assert "[REDACTED:api_key]" in redact_text(text)


def test_read_time_redaction_in_format_record():
    record = {
        "id": "vk_x",
        "library_id": "lib_default",
        "case_id": None,
        "status": "active",
        "problem": "legacy sk-proj-abcdefghijklmnopqrstuvwxyz1234567890 leak",
        "outcome": "resolved",
        "result_summary": "summary",
        "created_at": "2026-01-01T00:00:00+00:00",
        "payload": {"evidence": [{"kind": "log", "summary": "api_key=oldsecret"}]},
    }
    out = format_record_for_read(record, include_full_json=True)
    assert "sk-proj" not in out["problem"]
    assert "oldsecret" not in str(out["evidence"])


def test_context_boost_tag_overlap():
    payload = {"tags": ["deploy", "nginx"], "task_type": "deploy"}
    ctx = SearchContext(task_type="deploy", tags=["nginx"])
    assert context_boost(payload, ctx) > 1.0


def test_validate_report_requires_evidence_for_active():
    payload = Ma3ReportPayload(problem="p", outcome="resolved", result_summary="s", visibility="active")
    try:
        validate_report_write(payload, is_maintainer=False)
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 400
