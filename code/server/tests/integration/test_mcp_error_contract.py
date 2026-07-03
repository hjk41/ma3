"""MCP error contract (ADR-014 / design/11): every error must be self-correctable.

MCP hosts only surface ``error.message`` to the model (``error.data`` is often
dropped), so each error path must carry actionable guidance in the message
itself. These tests lock that constraint per JSON-RPC error code.
"""
from __future__ import annotations

from tests.helpers.mcp_client import McpClient


def _post(client, body):
    return client.post(
        "/mcp",
        content=body,
        headers={"Content-Type": "application/json", "X-API-Key": "ma3dev"},
    )


def test_parse_error_message_is_actionable(isolated_client):
    resp = _post(isolated_client, "{not valid json")
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert err["code"] == -32700
    assert "json" in err["message"].lower()


def test_invalid_request_message_names_bad_field(isolated_client):
    # Missing required `method` on the JSON-RPC envelope.
    resp = _post(isolated_client, '{"jsonrpc": "2.0", "id": 1}')
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert err["code"] == -32600
    # message must name the offending field, not just "Invalid Request".
    assert "method" in err["message"].lower()


def test_missing_tool_name_message(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    err = mcp.rpc("tools/call", {"arguments": {}}, expect_error=True)
    assert err["code"] == -32602
    assert "name" in err["message"].lower()


def test_non_object_arguments_message(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    err = mcp.rpc("tools/call", {"name": "ma3_context", "arguments": "oops"}, expect_error=True)
    assert err["code"] == -32602
    assert "object" in err["message"].lower()


def test_missing_required_fields_message_lists_fields(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    err = mcp.rpc(
        "tools/call",
        {"name": "ma3_report", "arguments": {"problem": "only one field"}},
        expect_error=True,
    )
    assert err["code"] == -32602
    msg = err["message"]
    assert "ma3_report" in msg
    assert "missing required field" in msg
    assert "outcome" in msg and "result_summary" in msg
    # structured copy still present for programmatic clients
    assert err["data"]["validation_errors"]
    assert "schema_hint" in err["data"]


def test_envelope_confusion_message_hints_flat_payload(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    err = mcp.rpc(
        "tools/call",
        {
            "name": "ma3_report",
            "arguments": {
                "arguments": {
                    "problem": "wrapped",
                    "outcome": "resolved",
                    "result_summary": "nested by mistake",
                }
            },
        },
        expect_error=True,
    )
    assert err["code"] == -32602
    msg = err["message"]
    assert "unexpected field" in msg and "arguments" in msg
    assert "FLAT payload" in msg and "ma3_validate" in msg


def test_unknown_enum_value_message_names_field(isolated_client):
    """A bad enum (case_assignment_mode) should surface the field in the message."""
    mcp = McpClient(isolated_client, api_key="ma3dev")
    err = mcp.rpc(
        "tools/call",
        {
            "name": "ma3_report",
            "arguments": {
                "problem": "bad enum",
                "outcome": "resolved",
                "result_summary": "x",
                "case_assignment_mode": "not_a_mode",
            },
        },
        expect_error=True,
    )
    assert err["code"] == -32602
    assert "case_assignment_mode" in err["message"]


def test_method_not_found_lists_supported_methods(isolated_client):
    mcp = McpClient(isolated_client)
    err = mcp.rpc("tools/frobnicate", expect_error=True)
    assert err["code"] == -32601
    assert "tools/call" in err["message"]


def test_unknown_tool_message_names_tool(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    err = mcp.rpc("tools/call", {"name": "ma3_nope", "arguments": {}}, expect_error=True)
    assert err["code"] == -32601
    assert "ma3_nope" in err["message"]


def test_invalid_credentials_message_mentions_api_key(isolated_client):
    mcp = McpClient(isolated_client)
    err = mcp.rpc(
        "tools/call",
        {"name": "ma3_context", "arguments": {"problem": "x"}},
        api_key="totally-bogus-key",
        expect_error=True,
    )
    assert err["code"] == -32001
    assert "api-key" in err["message"].lower() or "api key" in err["message"].lower()


def test_writer_access_denied_message_is_actionable(isolated_client):
    """A reader-only DB key writing must get an actionable 403-mapped message."""
    import secrets

    from app.services.api_key_service import hash_key
    from app.storage import db

    db.create_library("lib_ro_contract", name="RO Contract", visibility="private")
    key = f"ma3v4_{secrets.token_hex(12)}"
    db.upsert_user_principal(sso_user="ro-contract", display_name="ro")
    db.insert_api_key(
        key_id=f"key_{secrets.token_hex(5)}",
        key_hash=hash_key(key),
        principal_id="user:ro-contract",
        label="ro",
        grants=[{"library_id": "lib_ro_contract", "role": "reader"}],
    )
    mcp = McpClient(isolated_client)
    err = mcp.rpc(
        "tools/call",
        {
            "name": "ma3_report",
            "arguments": {
                "problem": "reader tries to write",
                "outcome": "resolved",
                "result_summary": "should be denied",
                "library_id": "lib_ro_contract",
            },
        },
        api_key=key,
        expect_error=True,
    )
    assert err["code"] == -32001
    assert "writer" in err["message"].lower() or "access" in err["message"].lower()
