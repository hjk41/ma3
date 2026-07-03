from __future__ import annotations

from app.services.redaction_service import redact_payload, redact_text
from app.services.record_read_service import format_record_for_read
from app.storage.db import (
    get_record,
    get_record_relations,
    get_superseded_record_ids,
    initialize_database,
    insert_record,
    insert_record_relations,
    set_record_status,
)


def test_redact_payload_scrubs_secrets():
    payload = {
        "problem": "use sk-abcdefghijklmnopqrstuvwxyz1234567890",
        "result_summary": "api_key=supersecret",
        "evidence": [{"summary": "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9"}],
    }
    out = redact_payload(payload)
    assert "sk-" not in out["problem"]
    assert "supersecret" not in out["result_summary"]
    assert "[REDACTED" in out["evidence"][0]["summary"]


def test_redact_text_url_credentials():
    text = "proxy at https://user:pass@host:8080/path"
    assert "[REDACTED:credentials]" in redact_text(text)


def test_format_record_for_read_trust_and_full():
    record = {
        "id": "vk_test",
        "library_id": "lib_default",
        "case_id": None,
        "status": "active",
        "problem": "p",
        "outcome": "resolved",
        "result_summary": "s",
        "created_at": "2026-01-01T00:00:00+00:00",
        "payload": {
            "applicable_if": ["os=linux"],
            "actions": [{"action": "ran tests"}],
            "evidence": [{"kind": "log", "summary": "ok"}],
        },
    }
    compact = format_record_for_read(record, include_full_json=False)
    assert compact["trust"]["applicable_if"] == ["os=linux"]
    assert "actions" not in compact

    full = format_record_for_read(record, include_full_json=True)
    assert full["actions"][0]["action"] == "ran tests"
    assert full["evidence"][0]["summary"] == "ok"


def test_record_relations_and_supersedes():
    initialize_database()
    old = insert_record(
        library_id="lib_default",
        case_id=None,
        status="active",
        problem="old approach",
        outcome="resolved",
        result_summary="deprecated",
        payload={"problem": "old approach"},
    )
    new = insert_record(
        library_id="lib_default",
        case_id=None,
        status="active",
        problem="new approach",
        outcome="resolved",
        result_summary="current",
        payload={"problem": "new approach"},
    )
    insert_record_relations(
        source_id=new["record_id"],
        based_on_record_ids=[old["record_id"]],
        relation_type="supersedes",
    )
    rels = get_record_relations([new["record_id"], old["record_id"]])
    assert any(r["relation_type"] == "supersedes" for r in rels[new["record_id"]])
    superseded = get_superseded_record_ids([old["record_id"]], {"lib_default"})
    assert old["record_id"] in superseded


def test_set_record_status_syncs_search_index():
    initialize_database()
    row = insert_record(
        library_id="lib_default",
        case_id=None,
        status="draft",
        problem="draft sync test unique token xyz",
        outcome="resolved",
        result_summary="pending",
        payload={"problem": "draft sync test unique token xyz", "tags": ["sync-test"]},
    )
    record_id = row["record_id"]
    set_record_status(record_id, "active")
    record = get_record(record_id)
    assert record is not None
    assert record["status"] == "active"
