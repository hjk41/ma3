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


def _table_exists(conn: psycopg.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
            (name,),
        ).fetchone()
        is not None
    )


def _legacy_columns(conn: psycopg.Connection, table: str) -> set[str]:
    rows = conn.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table,),
    ).fetchall()
    return {str(r["column_name"]) for r in rows}


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


def _v1_already_populated(conn: psycopg.Connection) -> bool:
    row = conn.execute("SELECT COUNT(*) AS c FROM records").fetchone()
    return bool(row and int(row["c"]) > 0)


def _sync_search_indexes(record_ids: list[str]) -> int:
    if not record_ids:
        return 0
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app.storage.db import sync_record_search_index

    indexed = 0
    for rid in record_ids:
        sync_record_search_index(rid)
        indexed += 1
    return indexed


def _backfill_orgs_and_libs(conn: psycopg.Connection) -> dict[str, int]:
    stats = {"organizations": 0, "libraries": 0, "cases": 0}
    if not _table_exists(conn, "legacy_organizations"):
        return stats

    lib_cols = _legacy_columns(conn, "legacy_libraries") if _table_exists(conn, "legacy_libraries") else set()
    org_rows = conn.execute("SELECT * FROM legacy_organizations").fetchall()
    for org in org_rows:
        org_id = org.get("id") or org.get("org_id")
        if not org_id:
            continue
        deleted = org.get("deleted_at")
        if deleted is not None:
            continue
        conn.execute(
            """
            INSERT INTO organizations (id, name) VALUES (%s, %s)
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
            """,
            (org_id, org.get("name") or org_id),
        )
        stats["organizations"] += 1

    if _table_exists(conn, "legacy_libraries"):
        libs = conn.execute("SELECT * FROM legacy_libraries").fetchall()
        for lib in libs:
            if "library_id" in lib_cols or "library_id" in lib:
                library_id = lib.get("library_id")
                org_id = lib.get("organization_id") or lib.get("org_id") or "org_default"
                visibility = "public" if lib.get("is_public") else lib.get("visibility") or "private"
                name = lib.get("name") or library_id
                kind = lib.get("kind")
                owner = lib.get("owner_principal_id")
            else:
                library_id = lib.get("id")
                org_id = lib.get("org_id") or "org_default"
                visibility = lib.get("visibility") or "private"
                name = lib.get("name") or library_id
                kind = lib.get("kind")
                owner = lib.get("owner_principal_id")
            if not library_id:
                continue
            if kind:
                conn.execute(
                    """
                    INSERT INTO libraries (id, org_id, name, visibility, kind, owner_principal_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                      name = EXCLUDED.name,
                      visibility = EXCLUDED.visibility,
                      kind = COALESCE(EXCLUDED.kind, libraries.kind),
                      owner_principal_id = COALESCE(EXCLUDED.owner_principal_id, libraries.owner_principal_id)
                    """,
                    (library_id, org_id, name, visibility, kind, owner),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO libraries (id, org_id, name, visibility)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, visibility = EXCLUDED.visibility
                    """,
                    (library_id, org_id, name, visibility),
                )
            stats["libraries"] += 1

    if _table_exists(conn, "legacy_cases"):
        case_cols = _legacy_columns(conn, "legacy_cases")
        if "title" in case_cols:
            cases = conn.execute("SELECT id, library_id, title, created_at FROM legacy_cases").fetchall()
            for row in cases:
                conn.execute(
                    """
                    INSERT INTO cases (id, library_id, title, created_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title, library_id = EXCLUDED.library_id
                    """,
                    (row["id"], row["library_id"], row["title"], row["created_at"]),
                )
                stats["cases"] += 1
        else:
            cases = conn.execute(
                "SELECT case_id, library_id, updated_at, payload_json FROM legacy_cases"
            ).fetchall()
            default_lib = "lib_default"
            for row in cases:
                payload = (
                    row["payload_json"]
                    if isinstance(row["payload_json"], dict)
                    else json.loads(row["payload_json"])
                )
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
                stats["cases"] += 1
    return stats


def _backfill_records_v1_shape(conn: psycopg.Connection) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT lr.*
        FROM legacy_records lr
        WHERE lr.id NOT LIKE 'vk_seed_%'
          AND NOT EXISTS (SELECT 1 FROM records r WHERE r.id = lr.id)
        """
    ).fetchall()
    imported = 0
    indexed_ids: list[str] = []
    for row in rows:
        status = row.get("status") or "active"
        if status not in ("active", "draft", "invalid", "buffered", "trashed"):
            status = "active"
        conn.execute(
            """
            INSERT INTO records (
                id, library_id, case_id, status, problem, outcome, result_summary,
                payload_json, created_by, created_at, trashed_at, publish_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, NULL)
            ON CONFLICT (id) DO UPDATE SET
              library_id = EXCLUDED.library_id,
              case_id = EXCLUDED.case_id,
              status = EXCLUDED.status,
              problem = EXCLUDED.problem,
              outcome = EXCLUDED.outcome,
              result_summary = EXCLUDED.result_summary,
              payload_json = EXCLUDED.payload_json,
              created_by = COALESCE(EXCLUDED.created_by, records.created_by),
              created_at = EXCLUDED.created_at,
              trashed_at = EXCLUDED.trashed_at
            """,
            (
                row["id"],
                row["library_id"],
                row.get("case_id"),
                status,
                row["problem"],
                row["outcome"],
                row["result_summary"],
                json.dumps(row["payload_json"])
                if not isinstance(row["payload_json"], str)
                else row["payload_json"],
                row.get("created_by"),
                row.get("created_at"),
                row.get("trashed_at"),
            ),
        )
        imported += 1
        if status == "active":
            indexed_ids.append(str(row["id"]))
    return {"records_imported": imported, "records_indexed": _sync_search_indexes(indexed_ids)}


def _backfill_records_old_shape(conn: psycopg.Connection, *, default_lib: str) -> dict[str, int]:
    rows = conn.execute(
        "SELECT record_id, library_id, status, payload_json FROM legacy_records"
    ).fetchall()
    imported = 0
    skipped_seed = 0
    indexed_ids: list[str] = []
    for row in rows:
        record_id = row["record_id"]
        if record_id.startswith("vk_seed_"):
            skipped_seed += 1
            continue
        exists = conn.execute("SELECT 1 FROM records WHERE id = %s", (record_id,)).fetchone()
        if exists:
            continue
        payload = (
            row["payload_json"]
            if isinstance(row["payload_json"], dict)
            else json.loads(row["payload_json"])
        )
        library_id = row["library_id"] or default_lib
        case_id = payload.get("case_id")
        status = row["status"] or payload.get("status") or "active"
        if status not in ("active", "draft", "invalid"):
            status = "active"
        problem, outcome, summary = _extract_record_fields(payload)
        created_at = payload.get("created_at") or payload.get("updated_at") or record_id
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
                record_id,
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
        imported += 1
        if status == "active":
            indexed_ids.append(record_id)
    return {
        "records_imported": imported,
        "skipped_seed_records": skipped_seed,
        "records_indexed": _sync_search_indexes(indexed_ids),
    }


def backfill_legacy(database_url: str) -> dict[str, Any]:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ["MA3_DATABASE_URL"] = database_url
    os.environ.setdefault("MA3_DISABLE_EMBEDDINGS", "1")

    from app.storage.db import initialize_database

    initialize_database()

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        if not _table_exists(conn, "legacy_records"):
            return {"skipped": True, "reason": "no legacy_records table"}

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        meta = _backfill_orgs_and_libs(conn)
        conn.commit()

        rec_cols = _legacy_columns(conn, "legacy_records")
        if "problem" in rec_cols and "id" in rec_cols:
            rec_stats = _backfill_records_v1_shape(conn)
        else:
            default_lib = "lib_default"
            if _table_exists(conn, "legacy_libraries"):
                lib_cols = _legacy_columns(conn, "legacy_libraries")
                if "id" in lib_cols:
                    lib = conn.execute("SELECT id FROM legacy_libraries LIMIT 1").fetchone()
                    if lib and lib.get("id"):
                        default_lib = lib["id"]
                else:
                    lib = conn.execute("SELECT library_id FROM legacy_libraries LIMIT 1").fetchone()
                    if lib and lib.get("library_id"):
                        default_lib = lib["library_id"]
            rec_stats = _backfill_records_old_shape(conn, default_lib=default_lib)
        conn.commit()

    return {**meta, **rec_stats, "backfill": True}


def migrate(database_url: str, *, rename: bool = True, backfill: bool = False) -> dict[str, Any]:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ["MA3_DATABASE_URL"] = database_url

    from app.storage.db import initialize_database

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        if rename:
            rename_legacy_tables(conn)
            conn.commit()

    initialize_database()

    if backfill:
        return backfill_legacy(database_url)

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        if _v1_already_populated(conn):
            return {"skipped": True, "reason": "v1 records already present"}

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        meta = _backfill_orgs_and_libs(conn)
        rec_cols = _legacy_columns(conn, "legacy_records")
        if "problem" in rec_cols and "id" in rec_cols:
            rec_stats = _backfill_records_v1_shape(conn)
        else:
            rec_stats = _backfill_records_old_shape(conn, default_lib="lib_default")
        conn.commit()
        return {**meta, **rec_stats, "initial_migration": True}


if __name__ == "__main__":
    target = os.environ.get("MA3_DATABASE_URL")
    if not target:
        print("Set MA3_DATABASE_URL", file=sys.stderr)
        sys.exit(1)
    rename = os.environ.get("MA3_MIGRATE_RENAME", "1") == "1"
    backfill = os.environ.get("MA3_MIGRATE_BACKFILL", "0") == "1"
    result = migrate(target, rename=rename, backfill=backfill)
    print(json.dumps(result, indent=2))
