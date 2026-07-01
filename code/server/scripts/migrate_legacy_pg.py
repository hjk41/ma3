#!/usr/bin/env python3
"""Migrate legacy ma3 tables (legacy_* prefix) into ma3_v1 schema in the same PostgreSQL DB."""
from __future__ import annotations

import json
import os
import sys
from typing import Any

import psycopg
from psycopg.rows import dict_row

LEGACY_RENAMES = (
    ("records", "legacy_records"),
    ("cases", "legacy_cases"),
    ("libraries", "legacy_libraries"),
    ("organizations", "legacy_organizations"),
)


def rename_legacy_tables(conn: psycopg.Connection) -> None:
    for old, new in LEGACY_RENAMES:
        old_exists = conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
            (old,),
        ).fetchone()
        new_exists = conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
            (new,),
        ).fetchone()
        if old_exists and not new_exists:
            conn.execute(f'ALTER TABLE public."{old}" RENAME TO "{new}"')


def _extract_record_fields(payload: dict[str, Any]) -> tuple[str, str, str]:
    problem = (
        payload.get("problem")
        or payload.get("claim")
        or payload.get("goal")
        or payload.get("task_type")
        or "imported record"
    )
    outcome = payload.get("outcome") or payload.get("result", {}).get("outcome") or "unknown"
    summary = (
        payload.get("result_summary")
        or payload.get("summary")
        or (problem[:500] if isinstance(problem, str) else "imported")
    )
    return str(problem)[:4000], str(outcome)[:500], str(summary)[:4000]


def _case_title(payload: dict[str, Any], case_id: str) -> str:
    for key in ("title", "problem", "name", "target_product"):
        val = payload.get(key)
        if val:
            return str(val)[:500]
    return case_id


def migrate(database_url: str, *, rename: bool = True) -> None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ["MA3_DATABASE_URL"] = database_url

    from app.storage.db import initialize_database

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        if rename:
            rename_legacy_tables(conn)
            conn.commit()

    initialize_database()

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        orgs = conn.execute(
            "SELECT org_id, name FROM legacy_organizations WHERE deleted_at IS NULL"
        ).fetchall()
        for org in orgs:
            conn.execute(
                """
                INSERT INTO organizations (id, name) VALUES (%s, %s)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
                """,
                (org["org_id"], org["name"]),
            )

        libs = conn.execute(
            "SELECT library_id, organization_id, name, is_public FROM legacy_libraries"
        ).fetchall()
        for lib in libs:
            org_id = lib["organization_id"] or "org_default"
            visibility = "public" if lib["is_public"] else "private"
            conn.execute(
                """
                INSERT INTO libraries (id, org_id, name, visibility)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, visibility = EXCLUDED.visibility
                """,
                (lib["library_id"], org_id, lib["name"], visibility),
            )

        cases = conn.execute(
            "SELECT case_id, library_id, updated_at, payload_json FROM legacy_cases"
        ).fetchall()
        case_count = 0
        default_lib = libs[0]["library_id"] if libs else "lib_default"
        for row in cases:
            payload = row["payload_json"] if isinstance(row["payload_json"], dict) else json.loads(row["payload_json"])
            library_id = row["library_id"] or default_lib
            title = _case_title(payload, row["case_id"])
            conn.execute(
                """
                INSERT INTO cases (id, library_id, title, created_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title, library_id = EXCLUDED.library_id
                """,
                (row["case_id"], library_id, title, row["updated_at"]),
            )
            case_count += 1

        records = conn.execute(
            "SELECT record_id, library_id, status, payload_json FROM legacy_records"
        ).fetchall()
        rec_count = 0
        skip = 0
        for row in records:
            if row["record_id"].startswith("vk_seed_"):
                skip += 1
                continue
            payload = row["payload_json"] if isinstance(row["payload_json"], dict) else json.loads(row["payload_json"])
            library_id = row["library_id"] or default_lib
            case_id = payload.get("case_id")
            status = row["status"] or payload.get("status") or "active"
            if status not in ("active", "draft", "invalid"):
                status = "active"
            problem, outcome, summary = _extract_record_fields(payload)
            created_at = payload.get("created_at") or payload.get("updated_at") or row["record_id"]
            conn.execute(
                """
                INSERT INTO records (id, library_id, case_id, status, problem, outcome, result_summary, payload_json, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (id) DO UPDATE SET
                  library_id = EXCLUDED.library_id,
                  case_id = EXCLUDED.case_id,
                  status = EXCLUDED.status,
                  problem = EXCLUDED.problem,
                  outcome = EXCLUDED.outcome,
                  result_summary = EXCLUDED.result_summary,
                  payload_json = EXCLUDED.payload_json
                """,
                (
                    row["record_id"],
                    library_id,
                    case_id,
                    status,
                    problem,
                    outcome,
                    summary,
                    json.dumps(payload),
                    created_at,
                ),
            )
            rec_count += 1

        conn.commit()
        print(
            json.dumps(
                {
                    "organizations": len(orgs),
                    "libraries": len(libs),
                    "cases": case_count,
                    "records": rec_count,
                    "skipped_seed_records": skip,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    target = os.environ.get("MA3_DATABASE_URL")
    if not target:
        print("Set MA3_DATABASE_URL", file=sys.stderr)
        sys.exit(1)
    rename = os.environ.get("MA3_MIGRATE_RENAME", "1") == "1"
    migrate(target, rename=rename)
