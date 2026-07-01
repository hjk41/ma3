from __future__ import annotations

from tests.helpers.mcp_client import McpClient

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


def test_healthz_and_client_bundle(isolated_client):
    health = isolated_client.get("/healthz")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["api_version"] == "v1"
    assert "sqlite" in body["features"]

    manifest = isolated_client.get("/client/manifest.json")
    assert manifest.status_code == 200
    assert manifest.json()["skill_bundle_version"]

    policy = isolated_client.get("/client/templates/ma3-agent-policy.mdc")
    assert policy.status_code == 200
    assert "ma3_context" in policy.text


def test_mcp_transport_and_schema(isolated_client):
    mcp = McpClient(isolated_client)

    assert isolated_client.get("/mcp").status_code == 405
    info = isolated_client.get("/mcp/info")
    assert info.status_code == 200
    assert info.json()["endpoint"] == "/mcp"
    assert "ma3_context" in info.json()["tools"]

    init = mcp.rpc("initialize")
    assert init["serverInfo"]["name"] == "ma3-remote-mcp"
    assert init["capabilities"]["tools"]

    tools = {t["name"]: t for t in mcp.rpc("tools/list")["tools"]}
    assert EXPECTED_TOOLS <= set(tools)
    report_schema = tools["ma3_report"]["inputSchema"]
    assert "$defs" in report_schema
    assert "AgentAction" in report_schema["$defs"]
    assert "EvidenceItem" in report_schema["$defs"]
    validate_tool = tools["ma3_validate"]
    assert "arguments" in validate_tool["inputSchema"]["properties"]
    assert "tool_name" in validate_tool["inputSchema"]["properties"]
    assert "tool_name" in validate_tool["description"]


def test_ma3_validate_success_and_failure(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    good = mcp.structured(
        "ma3_validate",
        {
            "tool_name": "ma3_report",
            "arguments": {
                "problem": "validate me",
                "outcome": "resolved",
                "result_summary": "ok",
            },
        },
    )
    assert good["ok"] is True

    bad = mcp.structured(
        "ma3_validate",
        {"tool_name": "ma3_report", "arguments": {"problem": "missing fields"}},
    )
    assert bad["ok"] is False
    assert bad["validation_errors"]


def test_ma3_report_context_case_roundtrip(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    problem = "mihomo proxy docker subscription URL unset"
    report = mcp.structured(
        "ma3_report",
        {
            "problem": problem,
            "outcome": "resolved",
            "result_summary": "Removed empty proxy-provider reference",
            "target_product": "ma3-eval",
            "tags": ["mihomo", "integration-test"],
        },
    )
    assert report["persisted"] is True
    assert report["status"] == "active"
    record_id = report["record_id"]
    case_id = report["case_assignment"]["case_id"]
    assert case_id

    context = mcp.structured("ma3_context", {"problem": "mihomo proxy docker"})
    assert context["cases"], context
    returned_ids = {
        rec["id"]
        for group in context["cases"]
        for rec in group.get("records", [])
    }
    assert record_id in returned_ids

    case = mcp.structured("ma3_case", {"case_id": case_id})
    assert case["case"]["id"] == case_id
    assert any(rec["id"] == record_id for rec in case["case"]["records"])

    explain = mcp.structured("ma3_search_explain", {"problem": "mihomo proxy"})
    assert explain["explain"]["hits"] >= 1


def test_ma3_whoami_and_doctor(isolated_client):
    mcp = McpClient(isolated_client)

    anon = mcp.structured("ma3_whoami")
    assert anon["caller"]["type"] == "anonymous"
    assert anon["readable_library_ids"]

    admin = mcp.structured("ma3_whoami", api_key="ma3dev")
    assert admin["caller"]["type"] == "admin"
    assert admin["writable_library_ids"]

    doctor = mcp.structured("ma3_doctor")
    assert doctor["status"] == "ok"
    assert doctor["database"] == "sqlite"
    assert doctor["records"] >= 0
    assert "server" in doctor
    assert doctor["server"]["client_update_urls"]


def test_draft_review_flow(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    lib_id = mcp.structured("ma3_whoami")["writable_library_ids"][0]

    draft = mcp.structured(
        "ma3_report",
        {
            "problem": "draft review integration",
            "outcome": "pending",
            "result_summary": "needs maintainer review",
            "visibility": "draft",
        },
    )
    assert draft["status"] == "draft"
    record_id = draft["record_id"]

    drafts = mcp.structured("ma3_list_drafts", {"library_id": lib_id})
    assert any(item["id"] == record_id for item in drafts["drafts"])

    reviewed = mcp.structured(
        "ma3_review_record",
        {
            "record_id": record_id,
            "decision": "approve",
            "review_note": "integration test approval",
        },
    )
    assert reviewed["old_status"] == "draft"
    assert reviewed["new_status"] == "active"


def test_validation_error_surfaces_field_loc(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    error = mcp.rpc(
        "tools/call",
        {"name": "ma3_report", "arguments": {"problem": "only one field"}},
        expect_error=True,
    )
    assert error["code"] == -32602
    data = error["data"]
    assert data["tool_name"] == "ma3_report"
    assert data["validation_errors"]
    assert "schema_hint" in data
