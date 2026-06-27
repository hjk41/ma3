"""Search helpers for tag and content matching across supported databases."""
from __future__ import annotations

import sqlite3

from app.core.config import settings
from app.core.time import utc_now_iso
from app.models.enums import SEARCHABLE_RECORD_STATUSES
from app.storage.db import get_connection, is_postgres


# Default candidate-retrieval status filter. Kept broad (active + stale +
# superseded) so soft-decayed records still reach the scorer; ranking then
# pushes them below active knowledge. See enums.SEARCHABLE_RECORD_STATUSES.
_DEFAULT_SEARCH_STATUSES: tuple[str, ...] = tuple(s.value for s in SEARCHABLE_RECORD_STATUSES)


def _status_values(status_filter: "str | tuple[str, ...] | list[str] | None") -> tuple[str, ...]:
    """Normalise a status filter into a tuple of status value strings.

    Accepts a single status string (legacy callers), an iterable of statuses,
    or ``None`` (meaning "use the default searchable set").
    """
    if status_filter is None:
        return _DEFAULT_SEARCH_STATUSES
    if isinstance(status_filter, str):
        return (status_filter,)
    return tuple(s.value if hasattr(s, "value") else str(s) for s in status_filter)


def fts_upsert(conn, record) -> None:
    """Insert or replace FTS index entries for a record.

    Must be called within an open connection/transaction.
    """
    record_id = record.record_id
    tags_str = " ".join(record.tags) if record.tags else ""
    if is_postgres():
        search_text = " ".join(
            part for part in [record.title, record.problem_family, record.summary, record.claim]
            if part
        )
        conn.execute(
            """
            INSERT INTO record_search_index(
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
                record.record_id,
                record.library_id,
                record.status.value if hasattr(record.status, "value") else str(record.status),
                search_text,
                tags_str,
                search_text,
                tags_str,
                getattr(record, "updated_at", None) or utc_now_iso(),
            ),
        )
        return

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


def fts_delete(conn, record_id: str) -> None:
    """Remove FTS index entries for a record."""
    if is_postgres():
        conn.execute("DELETE FROM record_search_index WHERE record_id = ?", (record_id,))
        return
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
    status_filter: "str | tuple[str, ...] | list[str] | None" = None,
    limit: int = 80,
) -> list[tuple[str, float]]:
    """Search the tag FTS index.

    Returns list of (record_id, bm25_score) sorted best-first (highest score first).
    BM25 returns negative values in SQLite; we negate so higher = better.
    """
    if not query.strip():
        return []

    if is_postgres():
        if settings.search_index_mode == "materialized":
            hits = _pg_materialized_tag_search(query, accessible_library_ids, status_filter, limit)
            if hits is not None:
                return hits
        return _pg_tag_search(query, accessible_library_ids, status_filter, limit)

    lib_sql, lib_params = _build_library_filter(accessible_library_ids)
    statuses = _status_values(status_filter)
    status_ph = ",".join("?" * len(statuses))
    sql = f"""
        SELECT f.record_id, -bm25(records_fts_tags) AS score
        FROM records_fts_tags f
        JOIN records r ON f.record_id = r.record_id
        WHERE records_fts_tags MATCH ?
          AND {lib_sql}
          AND r.status IN ({status_ph})
        ORDER BY score DESC
        LIMIT ?
    """
    params = [query, *lib_params, *statuses, limit]
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
    status_filter: "str | tuple[str, ...] | list[str] | None" = None,
    limit: int = 80,
) -> list[tuple[str, float]]:
    """Search the content FTS index (title, problem_family, summary, claim).

    Returns list of (record_id, bm25_score) sorted best-first.
    """
    if not query.strip():
        return []

    if is_postgres():
        if settings.search_index_mode == "materialized":
            hits = _pg_materialized_content_search(query, accessible_library_ids, status_filter, limit)
            if hits is not None:
                return hits
        return _pg_content_search(query, accessible_library_ids, status_filter, limit)

    lib_sql, lib_params = _build_library_filter(accessible_library_ids)
    statuses = _status_values(status_filter)
    status_ph = ",".join("?" * len(statuses))
    sql = f"""
        SELECT f.record_id, -bm25(records_fts_content) AS score
        FROM records_fts_content f
        JOIN records r ON f.record_id = r.record_id
        WHERE records_fts_content MATCH ?
          AND {lib_sql}
          AND r.status IN ({status_ph})
        ORDER BY score DESC
        LIMIT ?
    """
    params = [query, *lib_params, *statuses, limit]
    try:
        with get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [(row[0], float(row[1])) for row in rows]
    except sqlite3.OperationalError:
        return []


def _pg_library_filter(alias: str, accessible_library_ids: set[str]) -> tuple[str, list]:
    if not accessible_library_ids:
        return f"{alias}.library_id IS NULL", []
    placeholders = ",".join("?" * len(accessible_library_ids))
    return (
        f"({alias}.library_id IS NULL OR {alias}.library_id IN ({placeholders}))",
        list(accessible_library_ids),
    )



def _pg_materialized_tag_search(
    query: str,
    accessible_library_ids: set[str],
    status_filter,
    limit: int,
) -> list[tuple[str, float]] | None:
    lib_sql, lib_params = _pg_library_filter("i", accessible_library_ids)
    statuses = _status_values(status_filter)
    status_ph = ",".join("?" * len(statuses))
    sql = f"""
        SELECT i.record_id,
               ts_rank_cd(i.tags_tsv, websearch_to_tsquery('simple', ?)) AS score
        FROM record_search_index i
        WHERE i.tags_tsv @@ websearch_to_tsquery('simple', ?)
          AND {lib_sql}
          AND i.status IN ({status_ph})
        ORDER BY score DESC
        LIMIT ?
    """
    params = [query, query, *lib_params, *statuses, limit]
    try:
        with get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [(row["record_id"], float(row["score"])) for row in rows]
    except Exception:
        return None


def _pg_materialized_content_search(
    query: str,
    accessible_library_ids: set[str],
    status_filter,
    limit: int,
) -> list[tuple[str, float]] | None:
    lib_sql, lib_params = _pg_library_filter("i", accessible_library_ids)
    statuses = _status_values(status_filter)
    status_ph = ",".join("?" * len(statuses))
    sql = f"""
        SELECT i.record_id,
               ts_rank_cd(i.search_tsv, websearch_to_tsquery('simple', ?)) AS score
        FROM record_search_index i
        WHERE i.search_tsv @@ websearch_to_tsquery('simple', ?)
          AND {lib_sql}
          AND i.status IN ({status_ph})
        ORDER BY score DESC
        LIMIT ?
    """
    params = [query, query, *lib_params, *statuses, limit]
    try:
        with get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [(row["record_id"], float(row["score"])) for row in rows]
    except Exception:
        return None

def _pg_tag_search(
    query: str,
    accessible_library_ids: set[str],
    status_filter,
    limit: int,
) -> list[tuple[str, float]]:
    lib_sql, lib_params = _pg_library_filter("r", accessible_library_ids)
    statuses = _status_values(status_filter)
    status_ph = ",".join("?" * len(statuses))
    sql = f"""
        SELECT r.record_id,
               ts_rank_cd(
                   to_tsvector('simple', COALESCE(tags.tags_text, '')),
                   websearch_to_tsquery('simple', ?)
               ) AS score
        FROM records r
        LEFT JOIN LATERAL (
            SELECT string_agg(value, ' ') AS tags_text
            FROM jsonb_array_elements_text(COALESCE(r.payload_json->'tags', '[]'::jsonb)) AS value
        ) AS tags ON TRUE
        WHERE to_tsvector('simple', COALESCE(tags.tags_text, '')) @@ websearch_to_tsquery('simple', ?)
          AND {lib_sql}
          AND r.status IN ({status_ph})
        ORDER BY score DESC
        LIMIT ?
    """
    params = [query, query, *lib_params, *statuses, limit]
    try:
        with get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [(row["record_id"], float(row["score"])) for row in rows]
    except Exception:
        return []


def _pg_content_search(
    query: str,
    accessible_library_ids: set[str],
    status_filter,
    limit: int,
) -> list[tuple[str, float]]:
    lib_sql, lib_params = _pg_library_filter("r", accessible_library_ids)
    statuses = _status_values(status_filter)
    status_ph = ",".join("?" * len(statuses))
    content_expr = (
        "concat_ws(' ', "
        "COALESCE(r.payload_json->>'title', ''), "
        "COALESCE(r.payload_json->>'problem_family', ''), "
        "COALESCE(r.payload_json->>'summary', ''), "
        "COALESCE(r.payload_json->>'claim', '')"
        ")"
    )
    sql = f"""
        SELECT r.record_id,
               ts_rank_cd(
                   to_tsvector('simple', {content_expr}),
                   websearch_to_tsquery('simple', ?)
               ) AS score
        FROM records r
        WHERE to_tsvector('simple', {content_expr}) @@ websearch_to_tsquery('simple', ?)
          AND {lib_sql}
          AND r.status IN ({status_ph})
        ORDER BY score DESC
        LIMIT ?
    """
    params = [query, query, *lib_params, *statuses, limit]
    try:
        with get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [(row["record_id"], float(row["score"])) for row in rows]
    except Exception:
        return []
