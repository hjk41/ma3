"""FTS5 helpers for tag and content full-text search."""
from __future__ import annotations

import sqlite3

from app.storage.db import get_connection


def fts_upsert(conn: sqlite3.Connection, record) -> None:
    """Insert or replace FTS index entries for a record.

    Must be called within an open connection/transaction.
    """
    record_id = record.record_id
    tags_str = " ".join(record.tags) if record.tags else ""

    conn.execute(
        "DELETE FROM records_fts_tags WHERE record_id = ?", (record_id,)
    )
    conn.execute(
        "INSERT INTO records_fts_tags(record_id, tags) VALUES (?, ?)",
        (record_id, tags_str),
    )

    conn.execute(
        "DELETE FROM records_fts_content WHERE record_id = ?", (record_id,)
    )
    conn.execute(
        "INSERT INTO records_fts_content"
        "(record_id, title, problem_family, summary, claim) VALUES (?, ?, ?, ?, ?)",
        (
            record_id,
            record.title or "",
            record.problem_family or "",
            record.summary or "",
            record.claim or "",
        ),
    )


def fts_delete(conn: sqlite3.Connection, record_id: str) -> None:
    """Remove FTS index entries for a record."""
    conn.execute(
        "DELETE FROM records_fts_tags WHERE record_id = ?", (record_id,)
    )
    conn.execute(
        "DELETE FROM records_fts_content WHERE record_id = ?", (record_id,)
    )


def _build_library_filter(accessible_library_ids: set[str]) -> tuple[str, list]:
    """Return (sql_fragment, params) for library access check on the records table."""
    if not accessible_library_ids:
        return "r.library_id IS NULL", []
    placeholders = ",".join("?" * len(accessible_library_ids))
    return (
        f"(r.library_id IS NULL OR r.library_id IN ({placeholders}))",
        list(accessible_library_ids),
    )


def fts_tag_search(
    query: str,
    accessible_library_ids: set[str],
    status_filter: str = "active",
    limit: int = 80,
) -> list[tuple[str, float]]:
    """Search the tag FTS index.

    Returns list of (record_id, bm25_score) sorted best-first (highest score first).
    BM25 returns negative values in SQLite; we negate so higher = better.
    """
    if not query.strip():
        return []

    lib_sql, lib_params = _build_library_filter(accessible_library_ids)
    sql = f"""
        SELECT f.record_id, -bm25(records_fts_tags) AS score
        FROM records_fts_tags f
        JOIN records r ON f.record_id = r.record_id
        WHERE records_fts_tags MATCH ?
          AND {lib_sql}
          AND r.status = ?
        ORDER BY score DESC
        LIMIT ?
    """
    params = [query, *lib_params, status_filter, limit]
    try:
        with get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [(row[0], float(row[1])) for row in rows]
    except sqlite3.OperationalError:
        # FTS syntax error (e.g. special chars in query) — return empty
        return []


def fts_content_search(
    query: str,
    accessible_library_ids: set[str],
    status_filter: str = "active",
    limit: int = 80,
) -> list[tuple[str, float]]:
    """Search the content FTS index (title, problem_family, summary, claim).

    Returns list of (record_id, bm25_score) sorted best-first.
    """
    if not query.strip():
        return []

    lib_sql, lib_params = _build_library_filter(accessible_library_ids)
    sql = f"""
        SELECT f.record_id, -bm25(records_fts_content) AS score
        FROM records_fts_content f
        JOIN records r ON f.record_id = r.record_id
        WHERE records_fts_content MATCH ?
          AND {lib_sql}
          AND r.status = ?
        ORDER BY score DESC
        LIMIT ?
    """
    params = [query, *lib_params, status_filter, limit]
    try:
        with get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [(row[0], float(row[1])) for row in rows]
    except sqlite3.OperationalError:
        return []
