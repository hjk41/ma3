from __future__ import annotations

from tests.helpers.mcp_client import McpClient

_EVIDENCE = [{"kind": "test", "summary": "integration test evidence"}]

EXPECTED_TOOLS = {
    "ma3_context",
    "ma3_report",
    "ma3_case",
    "ma3_locate_by_id",
    "ma3_list_my_writes",
    "ma3_delete_record",
    "ma3_restore_record",
    "ma3_list_drafts",
    "ma3_review_record",
    "ma3_validate",
    "ma3_doctor",
    "ma3_whoami",
    "ma3_feedback",
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


def test_search_explain_is_not_exposed(isolated_client):
    mcp = McpClient(isolated_client)

    # ma3_search_explain tool is removed (internal-only ranking explain)
    assert "ma3_search_explain" not in EXPECTED_TOOLS
    err = mcp.call("ma3_search_explain", {"problem": "x"}, expect_error=True)
    assert err["code"] in (-32601, -32602, -32000, 404) or "unknown tool" in str(err).lower()

    # ma3_context must reject include_explain (extra=forbid)
    ctx_err = mcp.call(
        "ma3_context",
        {"problem": "x", "include_explain": True},
        expect_error=True,
    )
    assert ctx_err

    # ma3_validate no longer accepts ma3_search_explain as a target schema
    # (tool_name Literal rejects it → the validate call itself errors)
    validate_err = mcp.call(
        "ma3_validate",
        {"tool_name": "ma3_search_explain", "arguments": {"problem": "x"}},
        expect_error=True,
    )
    assert validate_err


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
            "evidence": _EVIDENCE,
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

    # explain is internal-only now: ma3_context must not surface ranking internals
    assert "explain" not in context
    # per-record ranking explain must not leak either. Derive the forbidden key set
    # from RankResult.explain() so new explain fields are auto-covered (design/12 §7.2).
    from app.storage.ranking import RankInput, score_one

    _INTERNAL_RANK_KEYS = {"_rank", "rank", *score_one(RankInput("x", relevance=0.5)).explain().keys()}
    for group in context["cases"]:
        for rec in group.get("records", []):
            assert _INTERNAL_RANK_KEYS.isdisjoint(rec.keys()), rec.keys()


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
            "based_on_record_ids": [],
            "evidence": _EVIDENCE,
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


def test_draft_approve_persists_relations(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    prior = mcp.structured(
        "ma3_report",
        {
            "problem": "draft relation prior",
            "outcome": "resolved",
            "result_summary": "prior active",
            "evidence": _EVIDENCE,
        },
    )
    draft = mcp.structured(
        "ma3_report",
        {
            "problem": "draft with lineage",
            "outcome": "pending",
            "result_summary": "awaiting review",
            "visibility": "draft",
            "based_on_record_ids": [prior["record_id"]],
            "relation_type": "derived_from",
            "evidence": _EVIDENCE,
        },
    )
    reviewed = mcp.structured(
        "ma3_review_record",
        {
            "record_id": draft["record_id"],
            "decision": "approve",
            "review_note": "approve with relations",
        },
    )
    assert reviewed["new_status"] == "active"
    ctx = mcp.structured("ma3_context", {"problem": "draft with lineage", "include_full_json": True})
    records = [rec for group in ctx["cases"] for rec in group.get("records", [])]
    records += ctx.get("ungrouped_records", [])
    hit = next(r for r in records if r["id"] == draft["record_id"])
    assert hit["trust"]["based_on_record_ids"] == [prior["record_id"]]
    assert hit.get("relations")

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
    # Message-level self-correction is covered exhaustively by
    # tests/integration/test_mcp_error_contract.py (ADR-014 / design/11).


def test_ma3_locate_by_id_record_and_case(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    report = mcp.structured(
        "ma3_report",
        {
            "problem": "locate by id integration",
            "outcome": "resolved",
            "result_summary": "fetch a single record by id",
            "evidence": _EVIDENCE,
            "actions": [{"action": "did the thing"}],
        },
    )
    record_id = report["record_id"]
    case_id = report["case_assignment"]["case_id"]

    located = mcp.structured("ma3_locate_by_id", {"id": record_id, "include_full_json": True})
    assert located["kind"] == "record"
    assert located["record"]["id"] == record_id
    assert located["record"]["evidence"]

    located_case = mcp.structured("ma3_locate_by_id", {"id": case_id})
    assert located_case["kind"] == "case"
    assert located_case["case"]["id"] == case_id
    assert any(r["id"] == record_id for r in located_case["case"]["records"])

    missing = mcp.rpc(
        "tools/call",
        {"name": "ma3_locate_by_id", "arguments": {"id": "vk_does_not_exist"}},
        expect_error=True,
    )
    assert missing["code"] == 404 or missing["message"]


def test_ma3_locate_by_id_hides_others_drafts_but_author_sees_own(isolated_client):
    admin = McpClient(isolated_client, api_key="ma3dev")
    draft = admin.structured(
        "ma3_report",
        {
            "problem": "locate draft visibility",
            "outcome": "pending",
            "result_summary": "author-only draft",
            "visibility": "draft",
            "evidence": _EVIDENCE,
        },
    )
    record_id = draft["record_id"]
    assert draft["status"] == "draft"

    # Anonymous (non-author, non-maintainer) must not see the draft -> 404.
    anon = McpClient(isolated_client)
    hidden = anon.rpc(
        "tools/call",
        {"name": "ma3_locate_by_id", "arguments": {"id": record_id}},
        expect_error=True,
    )
    assert hidden["code"] == 404 or hidden["message"]

    # Admin (maintainer/author) can see it.
    seen = admin.structured("ma3_locate_by_id", {"id": record_id})
    assert seen["kind"] == "record"
    assert seen["record"]["id"] == record_id
    assert seen["record"]["status"] == "draft"


def test_ma3_feedback_up_down_clear(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    report = mcp.structured(
        "ma3_report",
        {
            "problem": "feedback integration test",
            "outcome": "resolved",
            "result_summary": "verify thumbs up/down",
            "evidence": _EVIDENCE,
        },
    )
    record_id = report["record_id"]

    up = mcp.structured("ma3_feedback", {"record_id": record_id, "vote": "up"})
    assert up["feedback"]["up"] == 1
    assert up["feedback"]["my_vote"] == "up"

    down = mcp.structured("ma3_feedback", {"record_id": record_id, "vote": "down"})
    assert down["feedback"]["up"] == 0
    assert down["feedback"]["down"] == 1
    assert down["feedback"]["my_vote"] == "down"

    cleared = mcp.structured("ma3_feedback", {"record_id": record_id, "vote": "clear"})
    assert cleared["feedback"] == {"up": 0, "down": 0}

    case = mcp.structured("ma3_case", {"case_id": report["case_assignment"]["case_id"]})
    rec = next(r for r in case["case"]["records"] if r["id"] == record_id)
    assert rec["feedback"] == {"up": 0, "down": 0}

    anon_error = McpClient(isolated_client).rpc(
        "tools/call",
        {"name": "ma3_feedback", "arguments": {"record_id": record_id, "vote": "up"}},
        expect_error=True,
    )
    assert anon_error["code"] == -32001


def test_kb_trust_fields_relations_and_full_json(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    prior = mcp.structured(
        "ma3_report",
        {
            "problem": "kb prior record for lineage test",
            "outcome": "resolved",
            "result_summary": "baseline",
            "tags": ["kb-lineage"],
            "evidence": _EVIDENCE,
        },
    )
    follow = mcp.structured(
        "ma3_report",
        {
            "problem": "kb follow-up building on prior",
            "outcome": "resolved",
            "result_summary": "extended with sk-abcdefghijklmnopqrstuvwxyz1234567890",
            "based_on_record_ids": [prior["record_id"]],
            "relation_type": "derived_from",
            "applicable_if": ["runtime=python"],
            "evidence": _EVIDENCE,
        },
    )
    assert follow["relations_written"] == 1

    stored = mcp.structured(
        "ma3_context",
        {"problem": "kb follow-up building", "include_full_json": True},
    )
    records = [rec for group in stored["cases"] for rec in group.get("records", [])]
    records += stored.get("ungrouped_records", [])
    hit = next(r for r in records if r["id"] == follow["record_id"])
    assert hit["trust"]["based_on_record_ids"] == [prior["record_id"]]
    assert hit["actions"] == [] or isinstance(hit["actions"], list)
    assert "sk-" not in hit["result_summary"]
    assert hit.get("relations")

    compact = mcp.structured("ma3_context", {"problem": "kb follow-up building"})
    compact_records = [rec for group in compact["cases"] for rec in group.get("records", [])]
    compact_records += compact.get("ungrouped_records", [])
    compact_hit = next(r for r in compact_records if r["id"] == follow["record_id"])
    assert "actions" not in compact_hit
    assert compact_hit["trust"]["applicable_if"] == ["runtime=python"]


def test_invalid_api_key_rejected(isolated_client):
    error = McpClient(isolated_client, api_key="not-a-real-key").rpc(
        "tools/call",
        {"name": "ma3_whoami", "arguments": {}},
        expect_error=True,
    )
    assert error["code"] == -32001


def test_supersedes_requires_maintainer(isolated_client, monkeypatch):
    monkeypatch.setattr(
        "app.core.config.settings.writer_api_keys",
        ("writer-test-key",),
    )
    writer = McpClient(isolated_client, api_key="writer-test-key")
    target = writer.structured(
        "ma3_report",
        {
            "problem": "supersedes target record",
            "outcome": "resolved",
            "result_summary": "to be superseded",
            "evidence": _EVIDENCE,
        },
    )
    err = writer.rpc(
        "tools/call",
        {
            "name": "ma3_report",
            "arguments": {
                "problem": "attempt supersede",
                "outcome": "resolved",
                "result_summary": "should fail",
                "based_on_record_ids": [target["record_id"]],
                "relation_type": "supersedes",
                "evidence": _EVIDENCE,
            },
        },
        expect_error=True,
    )
    assert err["code"] == -32001


def test_ma3_report_idempotency_replay(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    key = "integration-idem-key-001"
    args = {
        "problem": "idempotency integration test",
        "outcome": "resolved",
        "result_summary": "same payload twice",
        "evidence": _EVIDENCE,
        "idempotency_key": key,
    }
    first = mcp.structured("ma3_report", args)
    assert first["persisted"] is True
    assert first.get("idempotent_replay") in (False, None)
    second = mcp.structured("ma3_report", args)
    assert second["record_id"] == first["record_id"]
    assert second["idempotent_replay"] is True

    conflict = mcp.rpc(
        "tools/call",
        {
            "name": "ma3_report",
            "arguments": {
                **args,
                "result_summary": "different summary",
            },
        },
        expect_error=True,
    )
    assert conflict["code"] == -32000
