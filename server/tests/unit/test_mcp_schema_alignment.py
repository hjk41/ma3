"""Lock the MCP advertised inputSchema to the actual Pydantic validator.

Before this lock existed, ``tools/list[].inputSchema`` was a hand-written dict
that drifted away from the Pydantic models the server validated against — most
visibly for ``actions`` and ``evidence`` on ``ma3_report``, where the schema
said ``"type": "array"`` but the server required full ``AgentAction`` /
``EvidenceItem`` shapes. Agents calling the tool had no way to discover the
required shape and saw ``-32602 Invalid params`` with no detail.

These tests guarantee that:

1. every MCP tool's published ``inputSchema`` is exactly the schema emitted by
   the corresponding Pydantic payload model (``tool_input_schema`` is the only
   source of truth);
2. the schema embeds ``$defs`` for nested types (``AgentAction``,
   ``EvidenceItem``, ``TargetRef``), so MCP clients can author payloads from
   the schema alone;
3. each payload carries a runnable example;
4. ``ma3_validate`` exists alongside the original six tools so agents can
   dry-run an arbitrary payload before consuming write quota.
"""
from __future__ import annotations

from app.models.mcp_payloads import PAYLOAD_BY_TOOL, tool_input_schema
from app.models.library import LibraryCreate
from app.services.library_service import create_library
from app.services.mcp_tool_service import call_mcp_tool, list_mcp_tools, resolve_mcp_auth


EXPECTED_TOOLS = {
    "ma3_context",
    "ma3_report",
    "ma3_case",
    "ma3_search_explain",
    "ma3_list_drafts",
    "ma3_review_record",
    "ma3_validate",
    "ma3_doctor",
    "ma3_whoami",
}


def test_every_mcp_tool_has_a_pydantic_payload_model():
    tools = {t.name for t in list_mcp_tools()}
    assert tools == EXPECTED_TOOLS, (
        "tools/list and PAYLOAD_BY_TOOL must stay in lockstep. "
        f"Listed: {sorted(tools)}; Modeled: {sorted(PAYLOAD_BY_TOOL)}"
    )
    assert set(PAYLOAD_BY_TOOL) == EXPECTED_TOOLS


def test_published_input_schema_matches_payload_model_schema():
    for descriptor in list_mcp_tools():
        derived = tool_input_schema(descriptor.name)
        assert descriptor.inputSchema == derived, (
            f"{descriptor.name} inputSchema drift detected. "
            "The Pydantic payload model is the source of truth — do not "
            "hand-edit the schema dict."
        )


def test_every_payload_model_forbids_extra_fields_so_typos_fail_loud():
    for name, model in PAYLOAD_BY_TOOL.items():
        config = getattr(model, "model_config", {}) or {}
        assert config.get("extra") == "forbid", (
            f"{name} payload allows extra=True; typos like `outome` instead of `outcome` "
            "would silently fall through to defaults."
        )


def test_every_payload_publishes_a_working_example():
    for name, model in PAYLOAD_BY_TOOL.items():
        schema = model.model_json_schema(ref_template="#/$defs/{model}")
        examples = schema.get("examples") or []
        assert examples, f"{name} payload has no example for clients to copy"
        # Each example must round-trip through the model unchanged.
        for example in examples:
            model.model_validate(example)


def test_ma3_report_schema_documents_actions_and_evidence_shape():
    """The original -32602 confusion came from ``actions`` showing as a bare
    array. The new schema must point clients at the nested AgentAction /
    EvidenceItem definitions so the *shape* of an item is discoverable.
    """
    schema = tool_input_schema("ma3_report")
    defs = schema.get("$defs") or {}
    assert "AgentAction" in defs, "AgentAction definition missing from ma3_report schema"
    assert "EvidenceItem" in defs, "EvidenceItem definition missing from ma3_report schema"

    actions = schema["properties"]["actions"]
    items_ref = actions["items"].get("$ref")
    assert items_ref and items_ref.endswith("AgentAction"), (
        f"ma3_report.actions.items must $ref AgentAction; got {actions['items']}"
    )
    evidence = schema["properties"]["evidence"]
    evidence_ref = evidence["items"].get("$ref")
    assert evidence_ref and evidence_ref.endswith("EvidenceItem"), (
        f"ma3_report.evidence.items must $ref EvidenceItem; got {evidence['items']}"
    )

    action_def = defs["AgentAction"]
    assert action_def["additionalProperties"] is False, (
        "AgentAction must forbid extras so payload typos (e.g. `step`) fail with the field name."
    )
    assert {"action", "rationale", "ref", "note"} <= set(action_def["properties"]), (
        "AgentAction is expected to expose rationale/ref/note as optional fields."
    )


def test_ma3_validate_inner_tool_enum_covers_every_callable_tool():
    schema = tool_input_schema("ma3_validate")
    enum = schema["properties"]["tool_name"]["enum"]
    callable_tools = EXPECTED_TOOLS - {"ma3_validate"}
    assert set(enum) == callable_tools, (
        "ma3_validate.tool_name enum must list every callable MCP tool except itself."
    )


def test_ma3_whoami_response_includes_additive_libraries_array():
    lib = create_library(LibraryCreate(name="public", is_public=True))
    result = call_mcp_tool("ma3_whoami", {}, resolve_mcp_auth(None))
    payload = result.structuredContent
    assert payload["principal"]["kind"] == "anonymous"
    assert {"library_id": lib.library_id, "role": "reader"} in payload["libraries"]
