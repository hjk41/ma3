from __future__ import annotations

import hashlib
import json

import pytest

from app.core.config import settings
from app.storage.db import count_records, get_idempotent_report, initialize_database, insert_record


def _hash_payload(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


@pytest.fixture
def idempotency_db(tmp_path, monkeypatch):
    db_path = tmp_path / "idem.sqlite3"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("MA3_DATABASE_URL", url)
    monkeypatch.setattr(settings, "database_url", url)
    initialize_database()
    yield


def test_idempotent_report_replay(idempotency_db):
    payload = {"problem": "idem test", "outcome": "resolved", "result_summary": "once"}
    payload_hash = _hash_payload(payload)
    first = insert_record(
        library_id="lib_default",
        case_id=None,
        status="active",
        problem="idem test",
        outcome="resolved",
        result_summary="once",
        payload=payload,
        idempotency_key="idem-key-001",
        principal_id="writer:key:0",
        payload_hash=payload_hash,
    )
    assert first["idempotent_replay"] is False
    before = count_records()
    second = insert_record(
        library_id="lib_default",
        case_id=None,
        status="active",
        problem="idem test",
        outcome="resolved",
        result_summary="once",
        payload=payload,
        idempotency_key="idem-key-001",
        principal_id="writer:key:0",
        payload_hash=payload_hash,
    )
    assert second["idempotent_replay"] is True
    assert second["record_id"] == first["record_id"]
    assert count_records() == before
    stored = get_idempotent_report("idem-key-001", "writer:key:0")
    assert stored is not None
    assert stored["record_id"] == first["record_id"]
