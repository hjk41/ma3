"""Integration tests for DB-backed API key auth (design/08 §5.4, ADR-011 Phase 2).

Covers the regression that broke eval agents: keys living in the `api_keys`
table were rejected because `resolve_from_credential` never consulted the DB.
"""
from __future__ import annotations

import secrets

from app.services.api_key_service import hash_key
from app.storage import db
from tests.helpers.mcp_client import McpClient

_EVIDENCE = [{"kind": "test", "summary": "api-key auth integration"}]


def _seed_key(principal_id: str, grants: list[dict[str, str]], *, label: str = "test-key") -> tuple[str, str]:
    """Create a principal + api key with grants; return the plaintext key."""
    plaintext = f"ma3v4_{secrets.token_hex(16)}"
    key_id = f"key_{secrets.token_hex(6)}"
    db.upsert_user_principal(sso_user=principal_id.removeprefix("user:"), display_name=label)
    db.insert_api_key(
        key_id=key_id,
        key_hash=hash_key(plaintext),
        principal_id=principal_id,
        label=label,
        grants=grants,
    )
    return plaintext, key_id


def test_writer_key_can_read_and_write_granted_library(isolated_client):
    mcp = McpClient(isolated_client)
    db.create_library("lib_team_w", name="Team W", visibility="private")
    key, key_id = _seed_key("user:writer-a", [{"library_id": "lib_team_w", "role": "writer"}])

    who = mcp.structured("ma3_whoami", api_key=key)
    assert who["caller"]["type"] == "api_key"
    assert who["caller"]["principal_id"] == "user:writer-a"
    assert who["readable_library_ids"] == ["lib_team_w"]
    assert who["writable_library_ids"] == ["lib_team_w"]
    assert who["maintainer_library_ids"] == []

    report = mcp.structured(
        "ma3_report",
        {
            "problem": "writer key writes to its granted library",
            "outcome": "resolved",
            "result_summary": "written via db api key",
            "library_id": "lib_team_w",
            "based_on_record_ids": [],
            "evidence": _EVIDENCE,
        },
        api_key=key,
    )
    assert report["persisted"] is True
    assert report["library_id"] == "lib_team_w"

    ctx = mcp.structured("ma3_context", {"problem": "writer key writes"}, api_key=key)
    ids = {rec["id"] for g in ctx["cases"] for rec in g.get("records", [])}
    assert report["record_id"] in ids


def test_reader_key_cannot_write(isolated_client):
    mcp = McpClient(isolated_client)
    db.create_library("lib_ro", name="Read Only", visibility="private")
    key, _ = _seed_key("user:reader-a", [{"library_id": "lib_ro", "role": "reader"}])

    who = mcp.structured("ma3_whoami", api_key=key)
    assert who["readable_library_ids"] == ["lib_ro"]
    assert who["writable_library_ids"] == []

    err = mcp.call(
        "ma3_report",
        {
            "problem": "reader key must not write",
            "outcome": "resolved",
            "result_summary": "should be rejected",
            "library_id": "lib_ro",
            "based_on_record_ids": [],
            "evidence": _EVIDENCE,
        },
        api_key=key,
        expect_error=True,
    )
    assert err["code"] == -32001


def test_unknown_key_is_401(isolated_client):
    mcp = McpClient(isolated_client)
    err = mcp.call("ma3_context", {"problem": "x"}, api_key="ma3v4_not_a_real_key", expect_error=True)
    assert err["code"] == -32001
    assert err["data"]["status_code"] == 401


def test_revoked_key_is_401(isolated_client):
    mcp = McpClient(isolated_client)
    db.create_library("lib_rev", name="Revoked", visibility="private")
    key, key_id = _seed_key("user:revoked-a", [{"library_id": "lib_rev", "role": "writer"}])

    # sanity: works before revocation
    assert mcp.structured("ma3_whoami", api_key=key)["caller"]["type"] == "api_key"

    with db.connect() as conn:
        db._execute(conn, "UPDATE api_keys SET revoked_at = ? WHERE key_id = ?", ("2020-01-01T00:00:00+00:00", key_id))

    err = mcp.call("ma3_context", {"problem": "x"}, api_key=key, expect_error=True)
    assert err["code"] == -32001


def test_key_cannot_read_other_library(isolated_client):
    mcp = McpClient(isolated_client)
    # dev writes a record into the community library
    admin_report = mcp.structured(
        "ma3_report",
        {
            "problem": "secret in community lib",
            "outcome": "resolved",
            "result_summary": "only visible to community-lib grantees",
            "based_on_record_ids": [],
            "evidence": _EVIDENCE,
        },
        api_key="ma3dev",
    )
    assert admin_report["persisted"] is True

    db.create_library("lib_other", name="Other", visibility="private")
    key, _ = _seed_key("user:isolated-a", [{"library_id": "lib_other", "role": "writer"}])

    ctx = mcp.structured("ma3_context", {"problem": "secret in community lib"}, api_key=key)
    ids = {rec["id"] for g in ctx["cases"] for rec in g.get("records", [])}
    assert admin_report["record_id"] not in ids
