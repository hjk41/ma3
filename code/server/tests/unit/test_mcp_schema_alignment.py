"""MCP inputSchema must match Pydantic payload models (P7)."""
from __future__ import annotations

from app.models.mcp_payloads import PAYLOAD_BY_TOOL, tool_input_schema
from app.services.mcp_tool_service import _TOOL_DESCRIPTIONS, list_mcp_tools


EXPECTED_TOOLS = {
    "ma3_context",
    "ma3_report",
    "ma3_case",
    "ma3_locate_by_id",
    "ma3_list_my_writes",
    "ma3_delete_record",
    "ma3_publish_record",
    "ma3_patch_record",
    "ma3_restore_record",
    "ma3_list_drafts",
    "ma3_review_record",
    "ma3_validate",
    "ma3_doctor",
    "ma3_whoami",
    "ma3_feedback",
}


def test_every_mcp_tool_has_a_pydantic_payload_model():
    tools = {t.name for t in list_mcp_tools()}
    assert tools == EXPECTED_TOOLS
    assert set(PAYLOAD_BY_TOOL) == EXPECTED_TOOLS


def test_published_input_schema_matches_payload_model_schema():
    for descriptor in list_mcp_tools():
        derived = tool_input_schema(descriptor.name)
        assert descriptor.inputSchema == derived


def test_ma3_report_schema_documents_actions_and_evidence_shape():
    schema = tool_input_schema("ma3_report")
    defs = schema.get("$defs", {})
    assert "AgentAction" in defs
    assert "EvidenceItem" in defs
    actions = schema["properties"]["actions"]
    assert actions["items"]["$ref"] == "#/$defs/AgentAction"


def test_every_payload_has_an_example():
    for name, model in PAYLOAD_BY_TOOL.items():
        schema = tool_input_schema(name)
        examples = schema.get("examples") or model.model_config.get("json_schema_extra", {}).get("examples")
        assert examples, f"{name} missing examples"
        model.model_validate(examples[0])
