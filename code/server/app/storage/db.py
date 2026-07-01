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


def search_records(library_ids: set[str], problem: str, limit: int = 20) -> list[dict[str, Any]]:
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


def all_library_ids() -> set[str]:
    with connect() as conn:
        rows = _fetchall(conn, "SELECT id FROM libraries")
    return {r["id"] for r in rows}
