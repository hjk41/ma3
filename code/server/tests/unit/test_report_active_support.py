"""Active-vs-draft support is part of the ma3_report contract, not only the write."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.mcp_payloads import (
    ACTIVE_REPORT_SUPPORT_MESSAGE,
    REPORT_ACTIVE_SUPPORT_SCHEMA_IF,
    REPORT_ACTIVE_SUPPORT_SCHEMA_THEN,
    Ma3ReportPayload,
    tool_input_schema,
)
from app.services.mcp_tool_service import list_mcp_tools, ma3_report_tool_description


def _minimal(**overrides) -> dict:
    payload = {
        "problem": "active support contract",
        "outcome": "resolved",
        "result_summary": "schema and validator agree",
    }
    payload.update(overrides)
    return payload


def test_tool_description_states_active_support_rule():
    phrase = "active records require at least one evidence item or action"
    for enhanced in (False, True):
        text = ma3_report_tool_description(enhanced=enhanced)
        assert "problem, outcome, result_summary" in text
        assert phrase in text
        assert "visibility=draft" in text
        assert "Omitted visibility means active" in text
    published = next(tool.description for tool in list_mcp_tools() if tool.name == "ma3_report")
    assert published == ma3_report_tool_description(enhanced=False)


def test_input_schema_conditional_requires_support_unless_draft():
    schema = tool_input_schema("ma3_report")
    assert schema["if"] == REPORT_ACTIVE_SUPPORT_SCHEMA_IF
    assert schema["then"] == REPORT_ACTIVE_SUPPORT_SCHEMA_THEN
    # Draft payloads stay valid at the top-level required array.
    assert "evidence" not in schema["required"]
    assert "actions" not in schema["required"]
    assert schema["properties"]["visibility"]["default"] == "active"
    description = schema["description"]
    assert "Omitted" in description and "draft" in description
    for name in ("evidence", "actions", "visibility"):
        assert "draft" in schema["properties"][name]["description"]
    published = next(tool.inputSchema for tool in list_mcp_tools() if tool.name == "ma3_report")
    assert published["if"] == schema["if"]
    assert published["then"] == schema["then"]


def test_model_rejects_active_without_support_and_accepts_the_valid_matrix():
    with pytest.raises(ValidationError) as omitted:
        Ma3ReportPayload.model_validate(_minimal())
    assert ACTIVE_REPORT_SUPPORT_MESSAGE in str(omitted.value)

    with pytest.raises(ValidationError) as explicit_active:
        Ma3ReportPayload.model_validate(_minimal(visibility="active", evidence=[], actions=[]))
    assert ACTIVE_REPORT_SUPPORT_MESSAGE in str(explicit_active.value)

    draft = Ma3ReportPayload.model_validate(_minimal(visibility="draft"))
    assert draft.visibility == "draft"
    assert draft.evidence == []
    assert draft.actions == []

    evidence_only = Ma3ReportPayload.model_validate(
        _minimal(evidence=[{"kind": "log", "summary": "reproduced"}])
    )
    assert evidence_only.visibility == "active"
    assert len(evidence_only.evidence) == 1
    assert evidence_only.actions == []

    actions_only = Ma3ReportPayload.model_validate(
        _minimal(actions=[{"action": "restarted the worker"}])
    )
    assert actions_only.visibility == "active"
    assert actions_only.evidence == []
    assert len(actions_only.actions) == 1
