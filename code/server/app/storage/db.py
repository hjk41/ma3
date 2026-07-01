from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.core.config import settings


def _database_url() -> str:
    return os.environ.get("MA3_DATABASE_URL", settings.database_url)


def is_postgres() -> bool:
    return _database_url().startswith("postgresql")


def _adapt_sql(sql: str) -> str:
    return sql.replace("?", "%s") if is_postgres() else sql


def _sqlite_path() -> Path:
    url = _database_url()
    if not url.startswith("sqlite:///"):
        raise RuntimeError(f"unsupported sqlite url: {url}")
    raw = url.removeprefix("sqlite:///")
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def connect() -> Iterator[Any]:
    if is_postgres():
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(_database_url(), row_factory=dict_row)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(_sqlite_path(), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def _execute(conn: Any, sql: str, params: tuple | list = ()) -> Any:
    cur = conn.execute(_adapt_sql(sql), params)
    return cur


def _fetchone(conn: Any, sql: str, params: tuple | list = ()) -> Any:
    return _execute(conn, sql, params).fetchone()


def _fetchall(conn: Any, sql: str, params: tuple | list = ()) -> list[Any]:
    return _execute(conn, sql, params).fetchall()


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def initialize_database() -> None:
    payload_type = "JSONB NOT NULL" if is_postgres() else "TEXT NOT NULL"
    with connect() as conn:
        _execute(
            conn,
            f"""
            CREATE TABLE IF NOT EXISTS organizations (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL
            )
            """,
        )
        _execute(
            conn,
            f"""
            CREATE TABLE IF NOT EXISTS libraries (
              id TEXT PRIMARY KEY,
              org_id TEXT NOT NULL,
              name TEXT NOT NULL,
              visibility TEXT NOT NULL DEFAULT 'private'
            )
            """,
        )
        _execute(
            conn,
            f"""
            CREATE TABLE IF NOT EXISTS cases (
              id TEXT PRIMARY KEY,
              library_id TEXT NOT NULL,
              title TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """,
        )
        _execute(
            conn,
            f"""
            CREATE TABLE IF NOT EXISTS records (
              id TEXT PRIMARY KEY,
              library_id TEXT NOT NULL,
              case_id TEXT,
              status TEXT NOT NULL,
              problem TEXT NOT NULL,
              outcome TEXT NOT NULL,
              result_summary TEXT NOT NULL,
              payload_json {payload_type},
              created_at TEXT NOT NULL
            )
            """,
        )
        _execute(conn, "CREATE INDEX IF NOT EXISTS idx_records_library_status ON records(library_id, status)")
        _execute(conn, "CREATE INDEX IF NOT EXISTS idx_records_case ON records(case_id)")
        _execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS principals (
              id TEXT PRIMARY KEY,
              kind TEXT NOT NULL,
              display_name TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """,
        )
        _execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS record_embeddings (
              record_id TEXT PRIMARY KEY,
              embedding BLOB NOT NULL,
              model TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """,
        )
        if is_postgres():
            _execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS record_search_index (
                  record_id TEXT PRIMARY KEY,
                  library_id TEXT,
                  status TEXT NOT NULL,
                  search_text TEXT NOT NULL DEFAULT '',
                  tags_text TEXT NOT NULL DEFAULT '',
                  search_tsv TSVECTOR NOT NULL,
                  tags_tsv TSVECTOR NOT NULL,
                  updated_at TEXT NOT NULL
                )
                """,
            )
        else:
            _execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS record_search_index (
                  record_id TEXT PRIMARY KEY,
                  library_id TEXT,
                  status TEXT NOT NULL,
                  search_text TEXT NOT NULL DEFAULT '',
                  tags_text TEXT NOT NULL DEFAULT '',
                  updated_at TEXT NOT NULL
                )
                """,
            )

        if not _fetchone(conn, "SELECT 1 FROM organizations WHERE id = ?", (settings.default_org_id,)):
            _execute(
                conn,
                "INSERT INTO organizations (id, name) VALUES (?, ?)",
                (settings.default_org_id, "Default Organization"),
            )
        if not _fetchone(conn, "SELECT 1 FROM libraries WHERE id = ?", (settings.default_library_id,)):
            _execute(
                conn,
                "INSERT INTO libraries (id, org_id, name, visibility) VALUES (?, ?, ?, ?)",
                (settings.default_library_id, settings.default_org_id, "Default Library", "private"),
            )


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _search_tokens(problem: str) -> list[str]:
    import re

    tokens = [t for t in re.split(r"\s+", problem.strip()) if len(t) >= 2]
    return tokens[:10] or [problem[:200]]


def _like_search_records(library_ids: set[str], problem: str, limit: int = 20) -> list[dict[str, Any]]:
    if not library_ids:
        return []
    placeholders = ",".join("?" for _ in library_ids)
    op = "ILIKE" if is_postgres() else "LIKE"
    tokens = _search_tokens(problem)
    token_clauses = " OR ".join(f"(problem {op} ? OR result_summary {op} ?)" for _ in tokens)
    query = f"""
        SELECT id, library_id, case_id, status, problem, outcome, result_summary, created_at
        FROM records
        WHERE library_id IN ({placeholders}) AND status = 'active'
          AND ({token_clauses})
        ORDER BY created_at DESC
        LIMIT ?
    """
    params: list[Any] = list(library_ids)
    for token in tokens:
        pattern = f"%{token[:200]}%"
        params.extend([pattern, pattern])
    params.append(limit)
    with connect() as conn:
        rows = _fetchall(conn, query, params)
    return [_row_dict(r) for r in rows]


def _fetch_records_by_ids(record_ids: list[str], library_ids: set[str]) -> list[dict[str, Any]]:
    if not record_ids or not library_ids:
        return []
    id_placeholders = ",".join("?" for _ in record_ids)
    lib_placeholders = ",".join("?" for _ in library_ids)
    query = f"""
        SELECT id, library_id, case_id, status, problem, outcome, result_summary, created_at
        FROM records
        WHERE id IN ({id_placeholders})
          AND library_id IN ({lib_placeholders})
          AND status = 'active'
    """
    with connect() as conn:
        rows = _fetchall(conn, query, [*record_ids, *library_ids])
    return [_row_dict(r) for r in rows]


def _list_active_record_ids(library_ids: set[str], limit: int = 500) -> set[str]:
    if not library_ids:
        return set()
    placeholders = ",".join("?" for _ in library_ids)
    query = f"""
        SELECT id
        FROM records
        WHERE library_id IN ({placeholders}) AND status = 'active'
        ORDER BY created_at DESC
        LIMIT ?
    """
    with connect() as conn:
        rows = _fetchall(conn, query, [*library_ids, limit])
    return {str(row["id"]) for row in rows}


def get_embeddings_batch(record_ids: set[str]) -> dict[str, Any]:
    if not record_ids:
        return {}
    from app.services.embedding_service import deserialize_embedding

    placeholders = ",".join("?" for _ in record_ids)
    with connect() as conn:
        rows = _fetchall(
            conn,
            f"SELECT record_id, embedding FROM record_embeddings WHERE record_id IN ({placeholders})",
            list(record_ids),
        )
    return {str(row["record_id"]): deserialize_embedding(row["embedding"]) for row in rows}


def count_embeddings() -> int:
    with connect() as conn:
        if not _table_exists(conn, "record_embeddings"):
            return 0
        row = _fetchone(conn, "SELECT COUNT(*) AS c FROM record_embeddings")
    return int(row["c"])


def _record_index_text(
    *,
    problem: str,
    outcome: str,
    result_summary: str,
    payload: dict[str, Any],
) -> tuple[str, str]:
    search_text = " ".join(part for part in [problem, outcome, result_summary] if part)
    tags = payload.get("tags") or []
    tags_text = " ".join(str(tag) for tag in tags)
    return search_text, tags_text


def upsert_record_search_index(
    *,
    record_id: str,
    library_id: str,
    status: str,
    search_text: str,
    tags_text: str,
    updated_at: str,
) -> None:
    with connect() as conn:
        if is_postgres():
            _execute(
                conn,
                """
                INSERT INTO record_search_index (
                    record_id, library_id, status, search_text, tags_text,
                    search_tsv, tags_tsv, updated_at
                )
                VALUES (?, ?, ?, ?, ?, to_tsvector('simple', ?), to_tsvector('simple', ?), ?)
                ON CONFLICT (record_id) DO UPDATE SET
                    library_id = EXCLUDED.library_id,
                    status = EXCLUDED.status,
                    search_text = EXCLUDED.search_text,
                    tags_text = EXCLUDED.tags_text,
                    search_tsv = EXCLUDED.search_tsv,
                    tags_tsv = EXCLUDED.tags_tsv,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    record_id,
                    library_id,
                    status,
                    search_text,
                    tags_text,
                    search_text,
                    tags_text,
                    updated_at,
                ),
            )
            return
        _execute(
            conn,
            """
            INSERT INTO record_search_index (
                record_id, library_id, status, search_text, tags_text, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (record_id) DO UPDATE SET
                library_id = excluded.library_id,
                status = excluded.status,
                search_text = excluded.search_text,
                tags_text = excluded.tags_text,
                updated_at = excluded.updated_at
            """,
            (record_id, library_id, status, search_text, tags_text, updated_at),
        )


def upsert_record_embedding(*, record_id: str, embedding: bytes, model: str, created_at: str) -> None:
    with connect() as conn:
        if is_postgres():
            _execute(
                conn,
                """
                INSERT INTO record_embeddings (record_id, embedding, model, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (record_id) DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    model = EXCLUDED.model,
                    created_at = EXCLUDED.created_at
                """,
                (record_id, embedding, model, created_at),
            )
            return
        _execute(
            conn,
            """
            INSERT INTO record_embeddings (record_id, embedding, model, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (record_id) DO UPDATE SET
                embedding = excluded.embedding,
                model = excluded.model,
                created_at = excluded.created_at
            """,
            (record_id, embedding, model, created_at),
        )


def index_record(
    *,
    record_id: str,
    library_id: str,
    status: str,
    problem: str,
    outcome: str,
    result_summary: str,
    payload: dict[str, Any],
    created_at: str,
) -> None:
    from app.core.config import settings as app_settings
    from app.services.embedding_service import embed_record_text, serialize_embedding

    search_text, tags_text = _record_index_text(
        problem=problem,
        outcome=outcome,
        result_summary=result_summary,
        payload=payload,
    )
    upsert_record_search_index(
        record_id=record_id,
        library_id=library_id,
        status=status,
        search_text=search_text,
        tags_text=tags_text,
        updated_at=created_at,
    )
    if app_settings.disable_embeddings:
        return
    vector = embed_record_text(
        problem=problem,
        outcome=outcome,
        result_summary=result_summary,
        payload=payload,
    )
    if vector is None:
        return
    model_name = app_settings.embedding_model.rsplit("/", 1)[-1]
    upsert_record_embedding(
        record_id=record_id,
        embedding=serialize_embedding(vector),
        model=model_name,
        created_at=created_at,
    )


def insert_record(
    *,
    library_id: str,
    case_id: str | None,
    status: str,
    problem: str,
    outcome: str,
    result_summary: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    from datetime import datetime, timezone

    rid = new_id("vk")
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    raw = json.dumps(payload)
    with connect() as conn:
        if is_postgres():
            _execute(
                conn,
                """
                INSERT INTO records (id, library_id, case_id, status, problem, outcome, result_summary, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?::jsonb, ?)
                """,
                (rid, library_id, case_id, status, problem, outcome, result_summary, raw, now),
            )
        else:
            _execute(
                conn,
                """
                INSERT INTO records (id, library_id, case_id, status, problem, outcome, result_summary, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (rid, library_id, case_id, status, problem, outcome, result_summary, raw, now),
            )
    index_record(
        record_id=rid,
        library_id=library_id,
        status=status,
        problem=problem,
        outcome=outcome,
        result_summary=result_summary,
        payload=payload,
        created_at=now,
    )
    return {"record_id": rid, "library_id": library_id, "case_id": case_id, "status": status, "created_at": now}


def get_record(record_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = _fetchone(conn, "SELECT * FROM records WHERE id = ?", (record_id,))
    if not row:
        return None
    out = _row_dict(row)
    payload = out.pop("payload_json")
    if isinstance(payload, str):
        out["payload"] = json.loads(payload)
    else:
        out["payload"] = payload
    return out


def list_drafts(library_id: str, limit: int, offset: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = _fetchall(
            conn,
            """
            SELECT id, library_id, case_id, status, problem, outcome, result_summary, created_at
            FROM records WHERE library_id = ? AND status = 'draft'
            ORDER BY created_at DESC LIMIT ? OFFSET ?
            """,
            (library_id, limit, offset),
        )
    return [_row_dict(r) for r in rows]


def set_record_status(record_id: str, status: str) -> dict[str, Any] | None:
    with connect() as conn:
        _execute(conn, "UPDATE records SET status = ? WHERE id = ?", (status, record_id))
    return get_record(record_id)


def get_or_create_case(library_id: str, title: str) -> str:
    from datetime import datetime, timezone

    with connect() as conn:
        row = _fetchone(
            conn,
            "SELECT id FROM cases WHERE library_id = ? AND title = ?",
            (library_id, title[:500]),
        )
        if row:
            return row["id"]
        cid = new_id("cs")
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        _execute(
            conn,
            "INSERT INTO cases (id, library_id, title, created_at) VALUES (?, ?, ?, ?)",
            (cid, library_id, title[:500], now),
        )
    return cid


def get_case(case_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = _fetchone(conn, "SELECT * FROM cases WHERE id = ?", (case_id,))
        if not row:
            return None
        case = _row_dict(row)
        recs = _fetchall(
            conn,
            "SELECT id, status, problem, outcome, result_summary, created_at FROM records WHERE case_id = ? ORDER BY created_at",
            (case_id,),
        )
        case["records"] = [_row_dict(r) for r in recs]
    return case


def count_records() -> int:
    with connect() as conn:
        row = _fetchone(conn, "SELECT COUNT(*) AS c FROM records")
    return int(row["c"])


def _table_exists(conn: Any, table_name: str) -> bool:
    if is_postgres():
        row = _fetchone(
            conn,
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = ?
            """,
            (table_name,),
        )
    else:
        row = _fetchone(
            conn,
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        )
    return row is not None


def _principal_id_column(conn: Any) -> str:
    if is_postgres():
        row = _fetchone(
            conn,
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'principals'
              AND column_name IN ('principal_id', 'id')
            ORDER BY CASE column_name WHEN 'principal_id' THEN 0 ELSE 1 END
            LIMIT 1
            """,
        )
        return str(row["column_name"]) if row else "id"
    return "id"


def _list_principals(conn: Any) -> tuple[int, list[dict[str, Any]]]:
    if not _table_exists(conn, "principals"):
        return 0, []
    count_row = _fetchone(conn, "SELECT COUNT(*) AS c FROM principals")
    id_col = _principal_id_column(conn)
    rows = _fetchall(
        conn,
        f"""
        SELECT {id_col} AS id, kind, display_name, created_at
        FROM principals
        ORDER BY created_at DESC
        LIMIT 50
        """,
    )
    return int(count_row["c"]), [_row_dict(r) for r in rows]


def get_system_stats() -> dict[str, Any]:
    with connect() as conn:
        organizations = [_row_dict(r) for r in _fetchall(conn, "SELECT id, name FROM organizations ORDER BY name")]
        libraries = [_row_dict(r) for r in _fetchall(conn, "SELECT id, org_id, name, visibility FROM libraries ORDER BY name")]

        cases_row = _fetchone(conn, "SELECT COUNT(*) AS c FROM cases")
        principals_count, principals = _list_principals(conn)

        status_rows = _fetchall(conn, "SELECT status, COUNT(*) AS c FROM records GROUP BY status")
        by_status = {str(r["status"]): int(r["c"]) for r in status_rows}
        total_records = sum(by_status.values())

        outcome_rows = _fetchall(
            conn,
            "SELECT outcome, COUNT(*) AS c FROM records GROUP BY outcome ORDER BY c DESC, outcome",
        )
        by_outcome = [{"outcome": str(r["outcome"]), "count": int(r["c"])} for r in outcome_rows]

        if is_postgres():
            task_rows = _fetchall(
                conn,
                """
                SELECT COALESCE(payload_json->>'task_type', 'unknown') AS task_type, COUNT(*) AS c
                FROM records
                GROUP BY 1
                ORDER BY c DESC, task_type
                """,
            )
        else:
            task_rows = _fetchall(
                conn,
                """
                SELECT COALESCE(json_extract(payload_json, '$.task_type'), 'unknown') AS task_type,
                       COUNT(*) AS c
                FROM records
                GROUP BY 1
                ORDER BY c DESC, task_type
                """,
            )
        by_task_type = [{"task_type": str(r["task_type"]), "count": int(r["c"])} for r in task_rows]

        lib_record_rows = _fetchall(
            conn,
            "SELECT library_id, status, COUNT(*) AS c FROM records GROUP BY library_id, status",
        )
        lib_case_rows = _fetchall(conn, "SELECT library_id, COUNT(*) AS c FROM cases GROUP BY library_id")
        org_names = {o["id"]: o["name"] for o in organizations}

    lib_records: dict[str, dict[str, int]] = {}
    for row in lib_record_rows:
        lid = str(row["library_id"])
        lib_records.setdefault(lid, {})
        lib_records[lid][str(row["status"])] = int(row["c"])

    lib_cases = {str(r["library_id"]): int(r["c"]) for r in lib_case_rows}

    library_stats = []
    for lib in libraries:
        lid = lib["id"]
        rec = lib_records.get(lid, {})
        rec_total = sum(rec.values())
        library_stats.append(
            {
                **lib,
                "org_name": org_names.get(lib["org_id"], lib["org_id"]),
                "cases": lib_cases.get(lid, 0),
                "records": {
                    "total": rec_total,
                    "by_status": rec,
                },
            }
        )

    return {
        "organizations": {"count": len(organizations), "items": organizations},
        "libraries": {"count": len(libraries), "items": library_stats},
        "users": {
            "count": principals_count,
            "items": principals,
            "note": "OIDC 用户与 API key 持有者登记在 principals 表；dev_auth 管理员不计入。",
        },
        "knowledge": {
            "cases": int(cases_row["c"]),
            "records": {
                "total": total_records,
                "by_status": by_status,
            },
            "by_outcome": by_outcome,
            "by_task_type": by_task_type,
        },
    }


def all_library_ids() -> set[str]:
    with connect() as conn:
        rows = _fetchall(conn, "SELECT id FROM libraries")
    return {r["id"] for r in rows}


from app.storage.search import search_records  # noqa: E402
