from __future__ import annotations

from tests.conftest import ADMIN_KEY


def _rpc(client, method: str, params: dict | None = None, *, key: str | None = ADMIN_KEY, request_id: int = 1):
    headers = {"X-API-Key": key} if key else {}
    return client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}},
        headers=headers,
    )


def _call(client, name: str, arguments: dict | None = None, *, key: str | None = ADMIN_KEY, request_id: int = 1):
    return _rpc(client, "tools/call", {"name": name, "arguments": arguments or {}}, key=key, request_id=request_id)


def test_remote_mcp_initialize_and_tools_list(client):
    no_sse = client.get("/mcp")
    assert no_sse.status_code == 405

    info = client.get("/mcp/info")
    assert info.status_code == 200
    assert info.json()["endpoint"] == "/mcp"
    assert "ma3_context" in info.json()["tools"]

    ping = _rpc(client, "ping", key=None)
    assert ping.status_code == 200
    assert ping.json()["result"] == {}

    init = _rpc(client, "initialize", key=None)
    assert init.status_code == 200
    body = init.json()
    assert body["result"]["serverInfo"]["name"] == "ma3-remote-mcp"
    assert body["result"]["capabilities"]["tools"]

    listed = _rpc(client, "tools/list", key=None)
    assert listed.status_code == 200
    tools = {tool["name"]: tool for tool in listed.json()["result"]["tools"]}
    assert {"ma3_context", "ma3_report", "ma3_case", "ma3_search_explain", "ma3_doctor", "ma3_whoami"} <= set(tools)
    assert tools["ma3_context"]["inputSchema"]["type"] == "object"


def test_remote_mcp_context_report_case_and_metrics(authed_client):
    report = _call(
        authed_client,
        "ma3_report",
        {
            "problem": "Remote MCP query should avoid shell JSON files",
            "task_type": "remote mcp implementation",
            "goal": "make agent querying one MCP call",
            "target_product": "ma3",
            "target_component": "remote-mcp",
            "outcome": "success",
            "result_summary": "Remote MCP report created a case",
            "actions": [{"action": "called ma3_report through MCP"}],
            "tags": ["mcp", "remote"],
        },
    )
    assert report.status_code == 200, report.text
    report_body = report.json()
    assert "result" in report_body
    structured = report_body["result"]["structuredContent"]
    assert structured["persisted"] is True
    record_id = structured["record_id"]
    case_id = structured["case_assignment"]["case"]["case_id"]
    assert record_id.startswith("vk_")

    context = _call(
        authed_client,
        "ma3_context",
        {
            "problem": "Remote MCP query should avoid shell JSON files",
            "task_type": "remote mcp implementation",
            "goal": "find the MCP case",
            "target_product": "ma3",
            "target_component": "remote-mcp",
            "tags": ["mcp", "remote"],
            "include_explain": True,
        },
    )
    assert context.status_code == 200, context.text
    ctx_structured = context.json()["result"]["structuredContent"]
    assert any(case["case_id"] == case_id for case in ctx_structured["cases"])
    assert ctx_structured["explain"]["query_hash"]

    case = _call(authed_client, "ma3_case", {"case_id": case_id})
    assert case.status_code == 200, case.text
    assert case.json()["result"]["structuredContent"]["case"]["case_id"] == case_id

    doctor = _call(authed_client, "ma3_doctor")
    assert doctor.status_code == 200
    assert doctor.json()["result"]["structuredContent"]["mcp"]["status"] == "ok"

    metrics = authed_client.get("/metrics")
    assert metrics.status_code == 200
    assert "ma3_mcp_tool_calls_total" in metrics.text
    assert 'tool="ma3_context"' in metrics.text
    assert 'tool="ma3_report"' in metrics.text


def test_remote_mcp_auth_isolation_reader_cannot_write(authed_client):
    lib = authed_client.post("/libraries", json={"name": "mcp-reader-lib", "is_public": False}).json()
    reader = authed_client.post(
        f"/libraries/{lib['library_id']}/tokens",
        json={"label": "reader", "role": "reader"},
    ).json()["token"]

    whoami = _call(authed_client, "ma3_whoami", key=reader)
    assert whoami.status_code == 200
    assert whoami.json()["result"]["structuredContent"]["identity"]["role"] == "reader"

    denied = _call(
        authed_client,
        "ma3_report",
        {
            "problem": "reader should not write",
            "outcome": "success",
            "result_summary": "this must be denied",
            "target_product": "ma3",
        },
        key=reader,
    )
    assert denied.status_code == 200
    error = denied.json()["error"]
    assert error["code"] == -32001
    assert error["message"] == "permission_denied"


def test_remote_mcp_invalid_params_and_notifications(client):
    bad = _call(client, "ma3_context", {}, key=None)
    assert bad.status_code == 200
    assert bad.json()["error"]["code"] == -32602

    notification = client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert notification.status_code == 202
