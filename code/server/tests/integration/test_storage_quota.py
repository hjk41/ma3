"""Integration tests for personal-library storage quotas."""
from __future__ import annotations

import secrets

import pytest

from app.core.config import settings
from app.services.api_key_service import hash_key
from app.storage import db
from tests.helpers.mcp_client import McpClient

_EVIDENCE = [{"kind": "test", "summary": "storage quota integration"}]


def _seed_personal_library(principal_id: str) -> str:
    lib_id = db.new_id("lib")
    db.ensure_library(
        lib_id,
        name="Quota Personal",
        visibility="private",
        kind="personal",
        owner_principal_id=principal_id,
    )
    return lib_id


def _seed_key(principal_id: str, personal_lib: str) -> str:
    plaintext = f"ma3k_{secrets.token_hex(16)}"
    db.upsert_user_principal(sso_user=principal_id.removeprefix("user:"), display_name=principal_id)
    db.insert_api_key(
        key_id=f"key_{secrets.token_hex(6)}",
        key_hash=hash_key(plaintext),
        principal_id=principal_id,
        label="quota-test",
        grants=[
            {"library_id": personal_lib, "role": "writer"},
            {"library_id": settings.default_library_id, "role": "writer"},
        ],
    )
    return plaintext


def test_personal_library_quota_blocks_write(isolated_client, monkeypatch):
    monkeypatch.setattr(settings, "personal_library_quota_bytes_free", 700)
    monkeypatch.setattr(settings, "max_record_bytes", 102400)
    mcp = McpClient(isolated_client)
    principal = "user:quota-free"
    personal = _seed_personal_library(principal)
    key = _seed_key(principal, personal)

    ok = mcp.structured(
        "ma3_report",
        {
            "problem": "first quota record",
            "outcome": "resolved",
            "result_summary": "fits",
            "library_id": personal,
            "based_on_record_ids": [],
            "evidence": _EVIDENCE,
        },
        api_key=key,
    )
    assert ok["record_id"]

    err = mcp.call(
        "ma3_report",
        {
            "problem": "second quota record",
            "outcome": "resolved",
            "result_summary": "overflow",
            "library_id": personal,
            "based_on_record_ids": [],
            "evidence": [{"kind": "test", "summary": "x" * 200}],
        },
        api_key=key,
        expect_error=True,
    )
    assert "quota exceeded" in err["message"].lower()


def test_community_library_not_subject_to_personal_quota(isolated_client, monkeypatch):
    monkeypatch.setattr(settings, "personal_library_quota_bytes_free", 1)
    monkeypatch.setattr(settings, "max_record_bytes", 102400)
    mcp = McpClient(isolated_client, api_key="ma3dev")
    report = mcp.structured(
        "ma3_report",
        {
            "problem": "community quota exempt",
            "outcome": "resolved",
            "result_summary": "public write",
            "library_id": settings.default_library_id,
            "based_on_record_ids": [],
            "evidence": _EVIDENCE,
        },
    )
    assert report["library_id"] == settings.default_library_id


def test_record_size_limit(isolated_client, monkeypatch):
    monkeypatch.setattr(settings, "max_record_bytes", 120)
    mcp = McpClient(isolated_client)
    principal = "user:record-size"
    personal = _seed_personal_library(principal)
    key = _seed_key(principal, personal)

    err = mcp.call(
        "ma3_report",
        {
            "problem": "x" * 200,
            "outcome": "resolved",
            "result_summary": "too big",
            "library_id": personal,
            "based_on_record_ids": [],
            "evidence": _EVIDENCE,
        },
        api_key=key,
        expect_error=True,
    )
    assert "limited to" in err["message"].lower()


def test_whoami_includes_storage_quota(isolated_client, monkeypatch):
    monkeypatch.setattr(settings, "personal_library_quota_bytes_free", 10 * 1024 * 1024)
    mcp = McpClient(isolated_client)
    principal = "user:whoami-quota"
    personal = _seed_personal_library(principal)
    key = _seed_key(principal, personal)

    whoami = mcp.structured("ma3_whoami", {}, api_key=key)
    quota = whoami["storage_quota"]
    assert quota["library_id"] == personal
    assert quota["tier"] == "free"
    assert quota["limit_bytes"] == 10 * 1024 * 1024


@pytest.mark.parametrize(
    ("tier", "limit"),
    [
        ("100mb", 100 * 1024 * 1024),
        ("10gb", 10 * 1024 * 1024 * 1024),
        ("1tb", 1024**4),
    ],
)
def test_principal_storage_tier_env(isolated_client, monkeypatch, tier, limit):
    principal = f"user:tier-{tier}"
    monkeypatch.setattr(settings, "principal_storage_tiers", {principal: tier})
    monkeypatch.setattr(settings, "max_record_bytes", 102400)
    mcp = McpClient(isolated_client)
    personal = _seed_personal_library(principal)
    key = _seed_key(principal, personal)

    whoami = mcp.structured("ma3_whoami", {}, api_key=key)
    assert whoami["storage_quota"]["tier"] == tier
    assert whoami["storage_quota"]["limit_bytes"] == limit
