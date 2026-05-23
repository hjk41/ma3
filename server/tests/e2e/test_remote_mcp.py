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


def _draft_record_payload(title: str) -> dict:
    return {
        "title": title,
        "problem_family": "review_queue",
        "summary": f"{title} summary",
        "claim": f"{title} claim",
        "target": {"product": "ma3", "component": "mcp-review"},
        "steps": [{"order": 1, "action": "capture draft", "note": None}],
        "result": {"outcome": "success", "summary": f"{title} result", "details": []},
        "evidence": [{"kind": "manual_observation", "summary": f"{title} evidence", "ref": None}],
        "applicable_if": [],
        "not_applicable_if": [],
        "status": "draft",
        "visibility_scope": "tenant",
        "risk_level": "high",
        "execution_mode": "manual_only",
        "source_type": "manual",
        "tags": ["review", "mcp"],
    }


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
    assert {
        "ma3_context",
        "ma3_report",
        "ma3_case",
        "ma3_search_explain",
        "ma3_list_drafts",
        "ma3_review_record",
        "ma3_validate",
        "ma3_doctor",
        "ma3_whoami",
    } <= set(tools)
    assert tools["ma3_context"]["inputSchema"]["type"] == "object"
    # The schema must surface the AgentAction/EvidenceItem $defs so clients
    # can construct payloads from inputSchema alone.
    report_schema = tools["ma3_report"]["inputSchema"]
    assert "$defs" in report_schema
    assert "AgentAction" in report_schema["$defs"]
    assert "EvidenceItem" in report_schema["$defs"]


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


def test_remote_mcp_all_initial_tools_and_full_json_modes(authed_client):
    report = _call(
        authed_client,
        "ma3_report",
        {
            "problem": "Remote MCP full coverage needs explain and full JSON",
            "task_type": "remote mcp coverage",
            "goal": "exercise all MCP tools",
            "target_product": "ma3",
            "target_component": "remote-mcp-tests",
            "outcome": "success",
            "result_summary": "Full MCP coverage seed record",
            "actions": [{"action": "seeded through ma3_report"}],
            "tags": ["mcp", "coverage", "explain"],
            "include_full_json": True,
        },
    )
    assert report.status_code == 200, report.text
    report_structured = report.json()["result"]["structuredContent"]
    assert report_structured["persisted"] is True
    assert report_structured["record"]["record_id"].startswith("vk_")
    case_id = report_structured["case_assignment"]["case"]["case_id"]

    explain = _call(
        authed_client,
        "ma3_search_explain",
        {
            "problem": "Remote MCP full coverage needs explain and full JSON",
            "task_type": "remote mcp coverage",
            "goal": "inspect explain ranking output",
            "target_product": "ma3",
            "target_component": "remote-mcp-tests",
            "max_cases": 5,
            "include_full_json": True,
        },
    )
    assert explain.status_code == 200, explain.text
    explain_structured = explain.json()["result"]["structuredContent"]
    assert "explain" in explain_structured
    assert explain_structured["explain"]["query_hash"]
    assert any(group["case"]["case_id"] == case_id for group in explain_structured["cases"])

    case = _call(authed_client, "ma3_case", {"case_id": case_id, "include_full_json": True})
    assert case.status_code == 200, case.text
    case_structured = case.json()["result"]["structuredContent"]
    assert case_structured["case"]["case_id"] == case_id
    assert any(record["record_id"] == report_structured["record"]["record_id"] for record in case_structured["records"])

    doctor = _call(authed_client, "ma3_doctor", {"include_full_json": True})
    assert doctor.status_code == 200, doctor.text
    doctor_structured = doctor.json()["result"]["structuredContent"]
    assert doctor_structured["status"] == "ok"
    assert doctor_structured["mcp"]["endpoint"] == "/mcp"
    assert "ma3_search_explain" in doctor_structured["mcp"]["tools"]

    whoami = _call(authed_client, "ma3_whoami", {"include_full_json": True})
    assert whoami.status_code == 200, whoami.text
    whoami_structured = whoami.json()["result"]["structuredContent"]
    assert whoami_structured["identity"]["type"] == "admin"
    assert isinstance(whoami_structured["visible_libraries"], list)


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
    err = bad.json()["error"]
    assert err["code"] == -32602
    # The structured shape must carry the offending field, not just a string.
    assert err["data"]["tool_name"] == "ma3_context"
    validation_errors = err["data"]["validation_errors"]
    assert isinstance(validation_errors, list) and validation_errors
    locs = {tuple(item["loc"]) for item in validation_errors}
    assert ("problem",) in locs, f"problem field should be flagged missing; got {locs}"
    assert "schema_hint" in err["data"]

    notification = client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert notification.status_code == 202


def test_remote_mcp_report_extra_field_surfaces_offending_field(authed_client):
    """A typo like `outome` instead of `outcome` must fail loudly and name the field."""

    bad = _call(
        authed_client,
        "ma3_report",
        {
            "problem": "validate that typos are caught",
            "outome": "success",  # typo on purpose
            "result_summary": "this should never persist",
            "target": {"product": "ma3", "component": "remote-mcp"},
        },
    )
    assert bad.status_code == 200
    err = bad.json()["error"]
    assert err["code"] == -32602
    assert err["data"]["tool_name"] == "ma3_report"
    locs = {tuple(item["loc"]) for item in err["data"]["validation_errors"]}
    # extra=forbid surfaces the unknown key's loc; outcome must also be flagged missing.
    assert ("outome",) in locs or any("outome" in str(item) for item in err["data"]["validation_errors"])
    assert ("outcome",) in locs


def test_remote_mcp_ma3_validate_dry_run_does_not_persist(authed_client):
    listed_before = _call(authed_client, "ma3_doctor").json()["result"]["structuredContent"]
    assert listed_before["mcp"]["status"] == "ok"

    ok = _call(
        authed_client,
        "ma3_validate",
        {
            "tool_name": "ma3_report",
            "arguments": {
                "problem": "dry-run validation should succeed",
                "outcome": "resolved",
                "result_summary": "this is a dry run",
                "target": {"product": "ma3", "component": "remote-mcp"},
                "actions": [{"action": "ran ma3_validate"}],
            },
        },
    )
    assert ok.status_code == 200, ok.text
    ok_body = ok.json()["result"]["structuredContent"]
    assert ok_body == {"ok": True, "tool_name": "ma3_report"}

    bad = _call(
        authed_client,
        "ma3_validate",
        {
            "tool_name": "ma3_report",
            "arguments": {"problem": "missing outcome and result_summary"},
        },
    )
    assert bad.status_code == 200, bad.text
    bad_body = bad.json()["result"]["structuredContent"]
    assert bad_body["ok"] is False
    assert bad_body["tool_name"] == "ma3_report"
    locs = {tuple(item["loc"]) for item in bad_body["validation_errors"]}
    assert ("outcome",) in locs
    assert ("result_summary",) in locs


def test_remote_mcp_list_drafts_and_review_flow(authed_client):
    lib = authed_client.post("/libraries", json={"name": "mcp-review-lib", "is_public": False}).json()
    writer = authed_client.post(
        f"/libraries/{lib['library_id']}/tokens",
        json={"label": "writer", "role": "writer"},
    ).json()["token"]
    admin = authed_client.post(
        f"/libraries/{lib['library_id']}/tokens",
        json={"label": "admin", "role": "admin"},
    ).json()["token"]

    created = authed_client.post(
        "/records",
        json=_draft_record_payload("draft approval candidate"),
        headers={"X-API-Key": writer},
    )
    assert created.status_code == 200, created.text
    record_id = created.json()["record_id"]

    listed = _call(
        authed_client,
        "ma3_list_drafts",
        {"library_id": lib["library_id"], "include_full_json": True},
        key=writer,
    )
    assert listed.status_code == 200, listed.text
    listed_body = listed.json()["result"]["structuredContent"]
    assert listed_body["library_id"] == lib["library_id"]
    assert listed_body["total_drafts"] >= 1
    assert any(item["record_id"] == record_id for item in listed_body["records"])

    approved = _call(
        authed_client,
        "ma3_review_record",
        {
            "record_id": record_id,
            "decision": "approve",
            "review_note": "validated and approved",
            "include_full_json": True,
        },
        key=admin,
    )
    assert approved.status_code == 200, approved.text
    approved_body = approved.json()["result"]["structuredContent"]
    assert approved_body["record_id"] == record_id
    assert approved_body["old_status"] == "draft"
    assert approved_body["new_status"] == "active"
    assert approved_body["record"]["status"] == "active"


def test_remote_mcp_review_reject_and_permission_guardrails(authed_client):
    lib = authed_client.post("/libraries", json={"name": "mcp-review-guards", "is_public": False}).json()
    writer = authed_client.post(
        f"/libraries/{lib['library_id']}/tokens",
        json={"label": "writer", "role": "writer"},
    ).json()["token"]
    admin = authed_client.post(
        f"/libraries/{lib['library_id']}/tokens",
        json={"label": "admin", "role": "admin"},
    ).json()["token"]

    created = authed_client.post(
        "/records",
        json=_draft_record_payload("draft reject candidate"),
        headers={"X-API-Key": writer},
    )
    assert created.status_code == 200, created.text
    record_id = created.json()["record_id"]

    denied = _call(
        authed_client,
        "ma3_review_record",
        {"record_id": record_id, "decision": "reject", "review_note": "writer must not review"},
        key=writer,
    )
    assert denied.status_code == 200
    assert denied.json()["error"]["code"] == -32001
    assert denied.json()["error"]["message"] == "permission_denied"

    rejected = _call(
        authed_client,
        "ma3_review_record",
        {"record_id": record_id, "decision": "reject", "review_note": "not suitable for promotion"},
        key=admin,
    )
    assert rejected.status_code == 200, rejected.text
    rejected_body = rejected.json()["result"]["structuredContent"]
    assert rejected_body["new_status"] == "invalid"

    non_draft = _call(
        authed_client,
        "ma3_review_record",
        {"record_id": record_id, "decision": "approve", "review_note": "cannot re-review invalid"},
        key=admin,
    )
    assert non_draft.status_code == 200
    assert non_draft.json()["error"]["code"] == -32602
    assert non_draft.json()["error"]["message"] == "Invalid params"
    assert non_draft.json()["error"]["data"]["detail"] == "only draft records can be reviewed via MCP"


def test_remote_mcp_batch_jsonrpc_and_error_mapping(authed_client):
    batch = authed_client.post(
        "/mcp",
        json=[
            {"jsonrpc": "2.0", "id": "init", "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": "ping", "method": "ping", "params": {}},
            {
                "jsonrpc": "2.0",
                "id": "missing-tool",
                "method": "tools/call",
                "params": {"name": "ma3_missing_tool", "arguments": {}},
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        ],
    )
    assert batch.status_code == 200, batch.text
    responses = {item["id"]: item for item in batch.json()}
    assert responses["init"]["result"]["serverInfo"]["name"] == "ma3-remote-mcp"
    assert responses["ping"]["result"] == {}
    assert responses["missing-tool"]["error"]["code"] == -32601
    assert "notifications/initialized" not in responses

    invalid_arguments = _rpc(
        authed_client,
        "tools/call",
        {"name": "ma3_context", "arguments": []},
        request_id=77,
    )
    assert invalid_arguments.status_code == 200
    assert invalid_arguments.json()["error"]["code"] == -32602


def test_remote_mcp_overview_ui_shows_deploy_identity(client, monkeypatch):
    """The UI banner is the single visible source of truth for which
    instance is serving traffic. It must show commit, job, and deploy date
    even when the JS data fetches fail.
    """
    from app.core import config as _config

    object.__setattr__(_config.settings, "git_commit", "abcdef0123456789")
    object.__setattr__(_config.settings, "instance_id", "ma3-test-instance")
    object.__setattr__(_config.settings, "job_name", "ma3-cpudev-1234")

    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.text
    assert 'class="deploy-banner"' in body
    assert 'id="ma3-shell-css"' in body
    assert "ma3-test-instance" in body
    # short commit form (12 chars)
    assert "abcdef012345" in body
    assert "ma3-cpudev-1234" in body
    # deployed_at is an ISO timestamp captured at boot; the label is enough
    assert "DEPLOYED" in body.upper()
    assert client.get("/ui/overview").status_code == 404


def test_root_ui_routes_do_not_shadow_api_routes(client):
    for path in ["/", "/me", "/libs", "/libs/lib_example", "/keys", "/admin", "/observatory"]:
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert "text/html" in resp.headers["content-type"]
        assert 'class="deploy-banner"' in resp.text

    assert client.get("/ui").status_code == 404
    assert client.get("/ui/").status_code == 404

    mcp_info = client.get("/mcp/info")
    assert mcp_info.status_code == 200
    assert mcp_info.json()["endpoint"] == "/mcp"

    whoami = client.get("/v3/auth/whoami")
    assert whoami.status_code == 200
    assert whoami.headers["content-type"].startswith("application/json")


def test_healthz_and_doctor_expose_deploy_identity(authed_client):
    h = authed_client.get("/healthz").json()
    assert "job_name" in h
    assert "deployed_at" in h
    d = authed_client.get("/v2/doctor").json()
    assert "job_name" in d
    assert "deployed_at" in d
