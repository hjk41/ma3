from app.core import config
import pytest

from app.storage.db import _ensure_postgres_jsonb_payload, _upsert, is_postgres


def test_upsert_sqlite_shape():
    orig_backend = config.settings.db_backend
    object.__setattr__(config.settings, "db_backend", "sqlite")
    try:
        sql = _upsert("records", ["record_id"], ["record_id", "status", "payload_json"])
    finally:
        object.__setattr__(config.settings, "db_backend", orig_backend)

    assert sql == "INSERT OR REPLACE INTO records(record_id, status, payload_json) VALUES (?, ?, ?)"


def test_upsert_postgres_shape():
    orig_backend = config.settings.db_backend
    object.__setattr__(config.settings, "db_backend", "postgresql")
    try:
        sql = _upsert("records", ["record_id"], ["record_id", "status", "payload_json"])
        backend = is_postgres()
    finally:
        object.__setattr__(config.settings, "db_backend", orig_backend)

    assert backend is True
    assert "ON CONFLICT (record_id) DO UPDATE SET status = EXCLUDED.status, payload_json = EXCLUDED.payload_json" in sql


def test_postgres_jsonb_payload_normalization_sql():
    class FakeConn:
        def __init__(self):
            self.sql = []

        def execute(self, sql, params=None):
            self.sql.append(sql)

    conn = FakeConn()
    _ensure_postgres_jsonb_payload(conn, "records")

    assert conn.sql == [
        "ALTER TABLE records ALTER COLUMN payload_json TYPE JSONB USING payload_json::jsonb"
    ]


def test_postgres_jsonb_payload_normalization_rejects_unknown_table():
    class FakeConn:
        def execute(self, sql, params=None):
            raise AssertionError("should not execute")

    with pytest.raises(ValueError):
        _ensure_postgres_jsonb_payload(FakeConn(), "libraries")
