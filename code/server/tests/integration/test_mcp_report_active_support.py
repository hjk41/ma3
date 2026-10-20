"""ma3_validate, dry_run, and writes share the active-support invariant."""
from __future__ import annotations

from app.models.mcp_payloads import ACTIVE_REPORT_SUPPORT_MESSAGE
from app.storage import db
from tests.helpers.mcp_client import McpClient

_EVIDENCE = [{"kind": "test", "summary": "active support evidence"}]
_ACTIONS = [{"action": "restarted the worker", "rationale": "cleared the stuck state"}]


def _base(**overrides) -> dict:
    payload = {
        "problem": "active support integration",
        "outcome": "resolved",
        "result_summary": "preflight matches the write",
    }
    payload.update(overrides)
    return payload


def _validate(mcp: McpClient, arguments: dict) -> dict:
    return mcp.structured(
        "ma3_validate",
        {"tool_name": "ma3_report", "arguments": arguments},
    )


def test_ma3_validate_matches_active_support_matrix(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")

    missing = _validate(mcp, _base())
    assert missing["ok"] is False
    assert ACTIVE_REPORT_SUPPORT_MESSAGE in str(missing["validation_errors"])

    explicit_empty = _validate(mcp, _base(visibility="active", evidence=[], actions=[]))
    assert explicit_empty["ok"] is False

    assert _validate(mcp, _base(visibility="draft"))["ok"] is True
    assert _validate(mcp, _base(evidence=_EVIDENCE))["ok"] is True
    assert _validate(mcp, _base(actions=_ACTIONS))["ok"] is True


def test_dry_run_and_write_reject_active_without_support_before_persist(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    before = db.count_records()

    dry = mcp.post_raw(
        "tools/call",
        {"name": "ma3_report", "arguments": _base(dry_run=True, problem="dry-run missing support")},
    )
    assert dry["status_code"] == 200, dry
    error = dry["body"]["error"]
    assert error["code"] == -32602
    assert ACTIVE_REPORT_SUPPORT_MESSAGE in error["message"]
    assert "<root>" not in error["message"]
    assert "Fix these fields and retry" in error["message"]
    assert error.get("data", {}).get("status_code") != 400
    assert "validation_errors" in error["data"]

    write = mcp.post_raw(
        "tools/call",
        {"name": "ma3_report", "arguments": _base(problem="write missing support")},
    )
    assert write["status_code"] == 200, write
    write_error = write["body"]["error"]
    assert write_error["code"] == -32602
    assert ACTIVE_REPORT_SUPPORT_MESSAGE in write_error["message"]
    assert db.count_records() == before


def test_draft_evidence_only_and_actions_only_reports(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")

    dry_evidence = mcp.structured(
        "ma3_report",
        _base(dry_run=True, problem="dry-run evidence only", evidence=_EVIDENCE),
    )
    assert dry_evidence["persisted"] is False
    assert dry_evidence["dry_run"] is True

    dry_actions = mcp.structured(
        "ma3_report",
        _base(dry_run=True, problem="dry-run actions only", actions=_ACTIONS),
    )
    assert dry_actions["persisted"] is False

    draft = mcp.structured(
        "ma3_report",
        _base(problem="explicit draft without support", visibility="draft", outcome="pending"),
    )
    assert draft["persisted"] is True
    assert draft["status"] == "draft"

    evidence_only = mcp.structured(
        "ma3_report",
        _base(problem="evidence only active", evidence=_EVIDENCE),
    )
    assert evidence_only["persisted"] is True
    assert evidence_only["status"] == "active"

    actions_only = mcp.structured(
        "ma3_report",
        _base(problem="actions only active", actions=_ACTIONS),
    )
    assert actions_only["persisted"] is True
    assert actions_only["status"] == "active"
