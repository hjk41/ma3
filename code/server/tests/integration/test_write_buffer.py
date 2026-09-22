"""Integration tests for design/16 library write buffer."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.services.api_key_service import hash_key
from app.storage import db
from tests.helpers.mcp_client import McpClient

_EVIDENCE = [{"kind": "test", "summary": "write buffer integration evidence"}]


def _writer_key(principal_id: str, *, label: str = "buffer-test") -> str:
    plaintext = f"ma3k_{secrets.token_hex(16)}"
    key_id = f"key_{secrets.token_hex(6)}"
    db.upsert_user_principal(sso_user=principal_id.removeprefix("user:"), display_name=principal_id)
    db.insert_api_key(
        key_id=key_id,
        key_hash=hash_key(plaintext),
        principal_id=principal_id,
        label=label,
        grants=[{"library_id": settings.default_library_id, "role": "writer"}],
    )
    return plaintext


def _reader_key(principal_id: str) -> str:
    plaintext = f"ma3k_{secrets.token_hex(16)}"
    key_id = f"key_{secrets.token_hex(6)}"
    db.upsert_user_principal(sso_user=principal_id.removeprefix("user:"), display_name=principal_id)
    db.insert_api_key(
        key_id=key_id,
        key_hash=hash_key(plaintext),
        principal_id=principal_id,
        label="buffer-reader",
        grants=[{"library_id": settings.default_library_id, "role": "reader"}],
    )
    return plaintext


def _report_args(**overrides) -> dict:
    base = {
        "problem": "write buffer test problem",
        "outcome": "resolved",
        "result_summary": "buffer integration summary",
        "library_id": settings.default_library_id,
        "based_on_record_ids": [],
        "evidence": _EVIDENCE,
        "report_kind": "new",
        "confirmation": "agent_judged",
    }
    base.update(overrides)
    return base


def _context_ids(ctx: dict) -> set[str]:
    ids = {r["id"] for group in ctx.get("cases", []) for r in group.get("records", [])}
    ids.update(r["id"] for r in ctx.get("ungrouped_records", []))
    return ids


@pytest.fixture()
def buffered_library(isolated_client):
    db.set_library_write_buffer_hours(settings.default_library_id, 24)
    yield isolated_client
    db.set_library_write_buffer_hours(settings.default_library_id, 0)


def test_buffer_zero_writes_immediate_active(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    report = mcp.structured("ma3_report", _report_args(problem="buffer off immediate active"))
    assert report["status"] == "active"
    assert report.get("publish_at") is None
    ctx = mcp.structured("ma3_context", {"problem": "buffer off immediate active"})
    assert report["record_id"] in _context_ids(ctx)


def test_new_report_becomes_buffered(buffered_library):
    mcp = McpClient(buffered_library)
    author_key = _writer_key("user:buffer-author-a")
    report = mcp.structured("ma3_report", _report_args(problem="buffered new report"), api_key=author_key)
    assert report["status"] == "buffered"
    assert report["publish_at"]
    assert report.get("readable_by") == ["author"]
    record = db.get_record(report["record_id"])
    assert record["status"] == "buffered"
    assert record["created_by"] == "user:buffer-author-a"


def test_author_sees_buffered_in_context_other_user_does_not(buffered_library):
    mcp = McpClient(buffered_library)
    author_key = _writer_key("user:buffer-author-b")
    reader_key = _reader_key("user:buffer-reader-b")
    report = mcp.structured(
        "ma3_report",
        _report_args(problem="author-only buffered visibility token"),
        api_key=author_key,
    )
    author_ctx = mcp.structured(
        "ma3_context",
        {"problem": "author-only buffered visibility token"},
        api_key=author_key,
    )
    reader_ctx = mcp.structured(
        "ma3_context",
        {"problem": "author-only buffered visibility token"},
        api_key=reader_key,
    )
    assert report["record_id"] in _context_ids(author_ctx)
    assert report["record_id"] not in _context_ids(reader_ctx)


def test_author_buffered_uses_relevance_before_case_truncation(buffered_library, monkeypatch):
    monkeypatch.setattr(settings, "disable_embeddings", True)
    monkeypatch.setattr(settings, "search_rel_min", 0.35)
    mcp = McpClient(buffered_library)
    author_principal = "user:buffer-author-ranked"
    author_key = _writer_key(author_principal)
    reader_key = _reader_key("user:buffer-reader-ranked")

    target_case = db.get_or_create_case(settings.default_library_id, "buffered target case")
    target = db.insert_record(
        library_id=settings.default_library_id,
        case_id=target_case,
        status="buffered",
        problem="远程 SSH 到阿里云 ECS 时出现 connection refused 或连接在密钥交换阶段被关闭",
        outcome="resolved",
        result_summary="阿里云 SSH connection refused 排障与代理路径修复",
        payload={"task_type": "debug_network"},
        principal_id=author_principal,
    )
    for index in range(3):
        competitor_case = db.get_or_create_case(
            settings.default_library_id,
            f"active competitor case {index}",
        )
        db.insert_record(
            library_id=settings.default_library_id,
            case_id=competitor_case,
            status="active",
            problem=f"ssh connection refused candidate {index}",
            outcome="resolved",
            result_summary="miscellaneous note",
            payload={"task_type": "debug_network"},
        )

    query = {
        "problem": "我想远程ssh到一台阿里云的机器，但是ssh connection refused",
        "task_type": "debug_network",
        "max_cases": 3,
        "max_records_per_case": 1,
    }
    author_ctx = mcp.structured("ma3_context", query, api_key=author_key)
    reader_ctx = mcp.structured("ma3_context", query, api_key=reader_key)

    assert target["record_id"] in _context_ids(author_ctx)
    assert target["record_id"] not in _context_ids(reader_ctx)


def test_buffered_private_indexes_follow_patch_and_publish(buffered_library, monkeypatch):
    import numpy as np

    from app.services import embedding_service

    monkeypatch.setattr(settings, "disable_embeddings", False)
    monkeypatch.setattr(
        embedding_service,
        "embed_record_text",
        lambda **_kwargs: np.ones(settings.embedding_dim, dtype=np.float32),
    )
    mcp = McpClient(buffered_library)
    principal_id = "user:buffer-private-index"
    author_key = _writer_key(principal_id)
    report = mcp.structured(
        "ma3_report",
        _report_args(problem="private buffered index original"),
        api_key=author_key,
    )
    record_id = report["record_id"]

    with db.connect() as conn:
        search_row = db._fetchone(
            conn,
            "SELECT status, created_by, search_text FROM record_search_index WHERE record_id = ?",
            (record_id,),
        )
        embedding_row = db._fetchone(
            conn,
            "SELECT status, created_by FROM record_embeddings WHERE record_id = ?",
            (record_id,),
        )
    assert dict(search_row)["status"] == "buffered"
    assert dict(search_row)["created_by"] == principal_id
    assert dict(embedding_row) == {"status": "buffered", "created_by": principal_id}

    mcp.structured(
        "ma3_patch_record",
        {
            "record_id": record_id,
            "problem": "private buffered index updated",
            "outcome": "resolved",
            "result_summary": "updated private index summary",
        },
        api_key=author_key,
    )
    with db.connect() as conn:
        patched = db._fetchone(
            conn,
            "SELECT status, created_by, search_text FROM record_search_index WHERE record_id = ?",
            (record_id,),
        )
    assert dict(patched)["status"] == "buffered"
    assert "private buffered index updated" in dict(patched)["search_text"]

    mcp.structured("ma3_publish_record", {"record_id": record_id}, api_key=author_key)
    with db.connect() as conn:
        published_search = db._fetchone(
            conn,
            "SELECT status, created_by FROM record_search_index WHERE record_id = ?",
            (record_id,),
        )
        published_embedding = db._fetchone(
            conn,
            "SELECT status, created_by FROM record_embeddings WHERE record_id = ?",
            (record_id,),
        )
    assert dict(published_search) == {"status": "active", "created_by": principal_id}
    assert dict(published_embedding) == {"status": "active", "created_by": principal_id}


def test_publish_record_makes_active_and_searchable(buffered_library):
    mcp = McpClient(buffered_library)
    author_key = _writer_key("user:buffer-author-c")
    report = mcp.structured("ma3_report", _report_args(problem="publish early token"), api_key=author_key)
    published = mcp.structured("ma3_publish_record", {"record_id": report["record_id"]}, api_key=author_key)
    assert published["status"] == "active"
    assert published["published"] is True
    reader_key = _reader_key("user:buffer-reader-c")
    reader_ctx = mcp.structured("ma3_context", {"problem": "publish early token"}, api_key=reader_key)
    assert report["record_id"] in _context_ids(reader_ctx)


def test_patch_resets_publish_at(buffered_library):
    mcp = McpClient(buffered_library)
    author_key = _writer_key("user:buffer-author-d")
    report = mcp.structured("ma3_report", _report_args(problem="patch reset timer"), api_key=author_key)
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).replace(microsecond=0).isoformat()
    record = db.get_record(report["record_id"])
    db.update_buffered_record(
        report["record_id"],
        problem=str(record["problem"]),
        outcome=str(record["outcome"]),
        result_summary=str(record["result_summary"]),
        payload=dict(record.get("payload") or {}),
        publish_at=past,
    )
    patched = mcp.structured(
        "ma3_patch_record",
        {
            "record_id": report["record_id"],
            "problem": "patch reset timer updated",
            "outcome": "resolved",
            "result_summary": "patched summary",
        },
        api_key=author_key,
    )
    assert patched["status"] == "buffered"
    assert patched["patched"] is True
    after = db.get_record(report["record_id"])["publish_at"]
    assert after != past
    assert datetime.fromisoformat(after) > datetime.fromisoformat(past)


def test_verify_report_skips_buffer(buffered_library):
    mcp = McpClient(buffered_library)
    author_key = _writer_key("user:buffer-author-e")
    target = mcp.structured(
        "ma3_report",
        _report_args(problem="verify target active", report_kind="new"),
        api_key=author_key,
    )
    mcp.structured("ma3_publish_record", {"record_id": target["record_id"]}, api_key=author_key)
    verify = mcp.structured(
        "ma3_report",
        {
            "problem": "verify skips buffer",
            "outcome": "resolved",
            "result_summary": "verify path",
            "library_id": settings.default_library_id,
            "target_record_id": target["record_id"],
            "report_kind": "verify",
            "confirmation": "agent_judged",
            "based_on_record_ids": [],
            "evidence": _EVIDENCE,
        },
        api_key=author_key,
    )
    assert verify["status"] == "active"


def test_publish_due_buffered_records(buffered_library):
    mcp = McpClient(buffered_library)
    author_key = _writer_key("user:buffer-author-f")
    report = mcp.structured("ma3_report", _report_args(problem="auto publish due"), api_key=author_key)
    record = db.get_record(report["record_id"])
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0).isoformat()
    db.update_buffered_record(
        report["record_id"],
        problem=str(record["problem"]),
        outcome=str(record["outcome"]),
        result_summary=str(record["result_summary"]),
        payload=dict(record.get("payload") or {}),
        publish_at=past,
    )
    count = db.publish_due_buffered_records()
    assert count >= 1
    assert db.get_record(report["record_id"])["status"] == "active"


def test_non_owner_cannot_publish(buffered_library):
    mcp = McpClient(buffered_library)
    author_key = _writer_key("user:buffer-author-g")
    other_key = _writer_key("user:buffer-author-other-g")
    report = mcp.structured("ma3_report", _report_args(problem="owner only publish"), api_key=author_key)
    err = mcp.call(
        "ma3_publish_record",
        {"record_id": report["record_id"]},
        api_key=other_key,
        expect_error=True,
    )
    assert err["code"] in {-32603, 403} or "403" in str(err)
