from __future__ import annotations

import secrets

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.services.storage_quota_service import (
    assert_personal_library_write_allowed,
    parse_principal_storage_tier_env,
    personal_library_quota_bytes,
    record_content_bytes,
    resolve_personal_storage_tier,
    tier_bytes,
)
from app.storage import db


def test_parse_principal_storage_tier_env():
    parsed = parse_principal_storage_tier_env("user:a=10gb,user:b=1tb")
    assert parsed == {"user:a": "10gb", "user:b": "1tb"}


def test_parse_principal_storage_tier_env_rejects_unknown_tier():
    with pytest.raises(ValueError, match="unknown storage tier"):
        parse_principal_storage_tier_env("user:a=5mb")


def test_tier_bytes_mapping():
    assert tier_bytes("free") == settings.personal_library_quota_bytes_free
    assert tier_bytes("100mb") == 100 * 1024 * 1024
    assert tier_bytes("10gb") == 10 * 1024 * 1024 * 1024
    assert tier_bytes("1tb") == 1024**4


def test_resolve_personal_storage_tier(monkeypatch):
    monkeypatch.setattr(settings, "principal_storage_tiers", {"user:vip": "1tb"})
    monkeypatch.setattr(settings, "paid_principal_ids", ("user:paid",))
    assert resolve_personal_storage_tier("user:vip") == "1tb"
    assert resolve_personal_storage_tier("user:paid") == "100mb"
    assert resolve_personal_storage_tier("user:free") == "free"
    assert personal_library_quota_bytes("user:vip") == 1024**4


def test_record_content_bytes_counts_utf8_payload():
    payload = {"problem": "p", "tags": ["中文"]}
    size = record_content_bytes(
        problem="问题",
        outcome="resolved",
        result_summary="总结",
        payload=payload,
    )
    assert size > len("问题".encode()) + len("resolved") + len("总结".encode())


def test_assert_blocks_oversized_record(monkeypatch):
    monkeypatch.setattr(settings, "max_record_bytes", 50)
    principal = f"user:oversize-{secrets.token_hex(4)}"
    lib_id = db.new_id("lib")
    db.ensure_library(lib_id, name="Personal", visibility="private", kind="personal", owner_principal_id=principal)
    with pytest.raises(HTTPException) as exc:
        assert_personal_library_write_allowed(
            library_id=lib_id,
            principal_id=principal,
            problem="x" * 100,
            outcome="resolved",
            result_summary="ok",
            payload={"problem": "x" * 100},
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "record_too_large"


def test_assert_blocks_personal_library_quota(monkeypatch):
    monkeypatch.setattr(settings, "personal_library_quota_bytes_free", 200)
    monkeypatch.setattr(settings, "max_record_bytes", 102400)
    principal = f"user:full-{secrets.token_hex(4)}"
    lib_id = db.new_id("lib")
    db.ensure_library(lib_id, name="Personal", visibility="private", kind="personal", owner_principal_id=principal)
    db.insert_record(
        library_id=lib_id,
        case_id=None,
        status="active",
        problem="existing",
        outcome="resolved",
        result_summary="filled",
        payload={"problem": "existing", "evidence": [{"kind": "log", "summary": "x" * 120}]},
        principal_id=principal,
    )
    with pytest.raises(HTTPException) as exc:
        assert_personal_library_write_allowed(
            library_id=lib_id,
            principal_id=principal,
            problem="another",
            outcome="resolved",
            result_summary="too much",
            payload={"problem": "another", "evidence": [{"kind": "log", "summary": "y" * 120}]},
        )
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "personal_library_storage_quota_exceeded"


def test_assert_skips_community_library(monkeypatch):
    monkeypatch.setattr(settings, "personal_library_quota_bytes_free", 1)
    monkeypatch.setattr(settings, "max_record_bytes", 1)
    assert_personal_library_write_allowed(
        library_id=settings.default_library_id,
        principal_id="user:any",
        problem="big" * 1000,
        outcome="resolved",
        result_summary="community write",
        payload={"problem": "big" * 1000},
    ) is None


def test_assert_patch_excludes_existing_record(monkeypatch):
    monkeypatch.setattr(settings, "personal_library_quota_bytes_free", 300)
    monkeypatch.setattr(settings, "max_record_bytes", 102400)
    principal = f"user:patch-{secrets.token_hex(4)}"
    lib_id = db.new_id("lib")
    db.ensure_library(lib_id, name="Personal", visibility="private", kind="personal", owner_principal_id=principal)
    row = db.insert_record(
        library_id=lib_id,
        case_id=None,
        status="buffered",
        problem="old",
        outcome="resolved",
        result_summary="old summary",
        payload={"problem": "old"},
        principal_id=principal,
    )
    assert_personal_library_write_allowed(
        library_id=lib_id,
        principal_id=principal,
        problem="new problem text",
        outcome="resolved",
        result_summary="new summary text",
        payload={"problem": "new problem text"},
        exclude_record_id=row["record_id"],
    ) is None
