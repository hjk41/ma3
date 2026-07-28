from __future__ import annotations

import json
import os
import uuid

import pytest

pytestmark = pytest.mark.postgres


def _require_pg_url() -> str:
    url = os.environ.get("MA3_DATABASE_URL")
    if not url or not url.startswith("postgresql"):
        pytest.skip("MA3_DATABASE_URL postgres URL required")
    return url


def test_migration_script_idempotent_on_legacy_tables(monkeypatch):
    """Run migrate_legacy_pg against a scratch legacy schema; safe to repeat."""
    import psycopg

    database_url = _require_pg_url()
    suffix = uuid.uuid4().hex[:8]
    org_id = f"org_test_{suffix}"
    lib_id = f"lib_test_{suffix}"
    case_id = f"cs_test_{suffix}"
    record_id = f"vk_test_{suffix}"

    with psycopg.connect(database_url) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS legacy_organizations (
              org_id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              deleted_at TIMESTAMPTZ
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS legacy_libraries (
              library_id TEXT PRIMARY KEY,
              organization_id TEXT,
              name TEXT NOT NULL,
              description TEXT NOT NULL DEFAULT '',
              is_public BOOLEAN NOT NULL DEFAULT FALSE,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS legacy_cases (
              case_id TEXT PRIMARY KEY,
              library_id TEXT,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              payload_json JSONB NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS legacy_records (
              record_id TEXT PRIMARY KEY,
              library_id TEXT,
              status TEXT,
              payload_json JSONB NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO legacy_organizations (org_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (org_id, "Test Org"),
        )
        conn.execute(
            """
            INSERT INTO legacy_libraries (library_id, organization_id, name, is_public)
            VALUES (%s, %s, %s, TRUE) ON CONFLICT DO NOTHING
            """,
            (lib_id, org_id, "Test Library"),
        )
        payload = {"title": "mihomo proxy docker", "problem": "mihomo proxy docker"}
        conn.execute(
            """
            INSERT INTO legacy_cases (case_id, library_id, payload_json)
            VALUES (%s, %s, %s::jsonb) ON CONFLICT DO NOTHING
            """,
            (case_id, lib_id, json.dumps(payload)),
        )
        record_payload = {
            "problem": "mihomo proxy docker subscription",
            "outcome": "resolved",
            "result_summary": "fixed proxy provider",
            "case_id": case_id,
        }
        conn.execute(
            """
            INSERT INTO legacy_records (record_id, library_id, status, payload_json)
            VALUES (%s, %s, 'active', %s::jsonb) ON CONFLICT DO NOTHING
            """,
            (record_id, lib_id, json.dumps(record_payload)),
        )
        conn.commit()

    monkeypatch.setenv("MA3_DATABASE_URL", database_url)
    monkeypatch.setenv("MA3_MIGRATE_RENAME", "0")

    import sys
    from pathlib import Path

    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    sys.path.insert(0, str(scripts_dir))
    import migrate_legacy_pg

    migrate_legacy_pg.migrate(database_url, rename=False)

    with psycopg.connect(database_url) as conn:
        row = conn.execute("SELECT problem FROM records WHERE id = %s", (record_id,)).fetchone()
        assert row is not None
        assert "mihomo" in row[0]
