"""Integration tests for multi-library read + agent write-target selection (ADR-011 slice)."""
from __future__ import annotations

import secrets

from app.core.config import settings
from app.services.api_key_service import hash_key
from app.storage import db
from tests.helpers.mcp_client import McpClient

_EVIDENCE = [{"kind": "test", "summary": "multi-library write selection"}]


def _seed_personal_library(principal_id: str, *, lib_id: str | None = None, name: str = "Personal") -> str:
    lib_id = lib_id or db.new_id("lib")
    db.ensure_library(
        lib_id,
        name=name,
        visibility="private",
        kind="personal",
        owner_principal_id=principal_id,
    )
    return lib_id


def _seed_dual_grant_key(
    principal_id: str,
    personal_lib: str,
    *,
    public_role: str = "writer",
) -> tuple[str, str]:
    plaintext = f"ma3k_{secrets.token_hex(16)}"
    key_id = f"key_{secrets.token_hex(6)}"
    db.upsert_user_principal(sso_user=principal_id.removeprefix("user:"), display_name=principal_id)
    db.insert_api_key(
        key_id=key_id,
        key_hash=hash_key(plaintext),
        principal_id=principal_id,
        label="dual-grant",
        grants=[
            {"library_id": personal_lib, "role": "writer"},
            {"library_id": settings.default_library_id, "role": public_role},
        ],
    )
    return plaintext, key_id


def test_one_key_reads_public_and_personal_libraries(isolated_client):
    mcp = McpClient(isolated_client)
    personal = _seed_personal_library("user:dual-read")
    key, _ = _seed_dual_grant_key("user:dual-read", personal)

    public_report = mcp.structured(
        "ma3_report",
        {
            "problem": "public dual-read token",
            "outcome": "resolved",
            "result_summary": "public side",
            "library_id": settings.default_library_id,
            "based_on_record_ids": [],
            "evidence": _EVIDENCE,
        },
        api_key=key,
    )
    personal_report = mcp.structured(
        "ma3_report",
        {
            "problem": "personal dual-read token",
            "outcome": "resolved",
            "result_summary": "personal side",
            "library_id": personal,
            "based_on_record_ids": [],
            "evidence": _EVIDENCE,
        },
        api_key=key,
    )

    ctx = mcp.structured("ma3_context", {"problem": "dual-read token"}, api_key=key)
    ids = {rec["id"] for g in ctx["cases"] for rec in g.get("records", [])}
    assert public_report["record_id"] in ids
    assert personal_report["record_id"] in ids
    lib_ids = {lib["library_id"] for lib in ctx["libraries"]}
    assert personal in lib_ids
    assert settings.default_library_id in lib_ids


def test_report_without_library_id_defaults_to_single_owned_personal_library(isolated_client):
    mcp = McpClient(isolated_client)
    personal = _seed_personal_library("user:default-personal")
    key, _ = _seed_dual_grant_key("user:default-personal", personal)

    report = mcp.structured(
        "ma3_report",
        {
            "problem": "implicit personal default",
            "outcome": "resolved",
            "result_summary": "should land in personal library",
            "based_on_record_ids": [],
            "evidence": _EVIDENCE,
        },
        api_key=key,
    )
    assert report["library_id"] == personal
    assert db.get_record(report["record_id"])["library_id"] == personal


def test_report_without_library_id_requires_explicit_when_no_personal_library(isolated_client):
    mcp = McpClient(isolated_client)
    plaintext = f"ma3k_{secrets.token_hex(16)}"
    key_id = f"key_{secrets.token_hex(6)}"
    db.upsert_user_principal(sso_user="public-only", display_name="public-only")
    db.insert_api_key(
        key_id=key_id,
        key_hash=hash_key(plaintext),
        principal_id="user:public-only",
        label="public-only",
        grants=[{"library_id": settings.default_library_id, "role": "writer"}],
    )

    err = mcp.call(
        "ma3_report",
        {
            "problem": "needs explicit library",
            "outcome": "resolved",
            "result_summary": "x",
            "based_on_record_ids": [],
            "evidence": _EVIDENCE,
        },
        api_key=plaintext,
        expect_error=True,
    )
    assert err["code"] == -32000
    assert "library_id_required" in err["message"]
    assert settings.default_library_id in err["message"]
    assert err["data"]["detail"]["error"] == "library_id_required"


def test_only_one_owned_personal_library_per_principal(isolated_client):
    """Schema enforces one personal library per owner; ambiguity case is prevented."""
    from app.services.onboarding_service import ensure_personal_library

    principal = "user:multi-personal"
    db.upsert_user_principal(sso_user="multi-personal", display_name="multi-personal")
    first = ensure_personal_library(principal, "Multi")
    second = ensure_personal_library(principal, "Multi")
    assert first["library_id"] == second["library_id"]
    libs = [
        lib
        for lib in db.list_libraries()
        if lib.get("kind") == "personal" and lib.get("owner_principal_id") == principal
    ]
    assert len(libs) == 1


def test_explicit_public_report_writes_community_library(isolated_client):
    mcp = McpClient(isolated_client)
    personal = _seed_personal_library("user:explicit-public")
    key, _ = _seed_dual_grant_key("user:explicit-public", personal)

    report = mcp.structured(
        "ma3_report",
        {
            "problem": "explicit community write",
            "outcome": "resolved",
            "result_summary": "public",
            "library_id": settings.default_library_id,
            "based_on_record_ids": [],
            "evidence": _EVIDENCE,
        },
        api_key=key,
    )
    assert report["library_id"] == settings.default_library_id


def test_verify_refute_pin_target_library_even_with_personal_default(isolated_client):
    mcp = McpClient(isolated_client)
    personal = _seed_personal_library("user:verify-pin")
    key, _ = _seed_dual_grant_key("user:verify-pin", personal)

    target = mcp.structured(
        "ma3_report",
        {
            "problem": "verify target in public",
            "outcome": "resolved",
            "result_summary": "target",
            "library_id": settings.default_library_id,
            "based_on_record_ids": [],
            "evidence": _EVIDENCE,
        },
        api_key=key,
    )
    verify = mcp.structured(
        "ma3_report",
        {
            "problem": "verify target in public",
            "outcome": "resolved",
            "result_summary": "confirmed",
            "report_kind": "verify",
            "target_record_id": target["record_id"],
            "based_on_record_ids": [],
            "evidence": _EVIDENCE,
        },
        api_key=key,
    )
    assert verify["library_id"] == settings.default_library_id


def test_unwritable_library_error_lists_writable_libraries(isolated_client):
    mcp = McpClient(isolated_client)
    personal = _seed_personal_library("user:unwritable")
    key, _ = _seed_dual_grant_key("user:unwritable", personal)
    other = db.new_id("lib")
    db.create_library(other, name="Other Org", visibility="private")

    err = mcp.call(
        "ma3_report",
        {
            "problem": "wrong library",
            "outcome": "resolved",
            "result_summary": "x",
            "library_id": other,
            "based_on_record_ids": [],
            "evidence": _EVIDENCE,
        },
        api_key=key,
        expect_error=True,
    )
    assert err["code"] == -32001
    assert "library_not_writable" in err["message"]
    assert personal in err["message"]


def test_whoami_exposes_library_selection_metadata(isolated_client):
    mcp = McpClient(isolated_client)
    personal = _seed_personal_library("user:whoami-meta", name="Whoami Personal")
    key, _ = _seed_dual_grant_key("user:whoami-meta", personal)

    who = mcp.structured("ma3_whoami", api_key=key)
    assert "library_selection" in who
    by_id = {lib["library_id"]: lib for lib in who["writable_libraries"]}
    assert by_id[personal]["kind"] == "personal"
    assert by_id[personal]["is_personal"] is True
    assert by_id[settings.default_library_id]["kind"] == "community"
    assert by_id[settings.default_library_id]["is_public_default"] is True


def test_dev_bypass_still_defaults_to_public_without_library_id(isolated_client):
    mcp = McpClient(isolated_client)
    report = mcp.structured(
        "ma3_report",
        {
            "problem": "dev implicit public default",
            "outcome": "resolved",
            "result_summary": "legacy path",
            "based_on_record_ids": [],
            "evidence": _EVIDENCE,
        },
        api_key="ma3dev",
    )
    assert report["library_id"] == settings.default_library_id


def test_dry_run_surfaces_library_selection_error(isolated_client):
    mcp = McpClient(isolated_client)
    plaintext = f"ma3k_{secrets.token_hex(16)}"
    key_id = f"key_{secrets.token_hex(6)}"
    db.upsert_user_principal(sso_user="dry-run-only", display_name="dry-run-only")
    db.insert_api_key(
        key_id=key_id,
        key_hash=hash_key(plaintext),
        principal_id="user:dry-run-only",
        label="public-only",
        grants=[{"library_id": settings.default_library_id, "role": "writer"}],
    )

    err = mcp.call(
        "ma3_report",
        {
            "problem": "dry run library pick",
            "outcome": "resolved",
            "result_summary": "x",
            "dry_run": True,
            "based_on_record_ids": [],
            "evidence": _EVIDENCE,
        },
        api_key=plaintext,
        expect_error=True,
    )
    assert err["code"] == -32000
    assert "library_id_required" in err["message"]
