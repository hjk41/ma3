import json
import sqlite3

from app.core.config import settings
from app.models.record import Record


def get_connection() -> sqlite3.Connection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database(run_backfill: bool = True) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS libraries (
                library_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                is_public INTEGER NOT NULL DEFAULT 1,
                parent_library_id TEXT,
                is_personal INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        # Migrations for libraries table
        for col_sql in [
            "ALTER TABLE libraries ADD COLUMN parent_library_id TEXT",
            "ALTER TABLE libraries ADD COLUMN is_personal INTEGER NOT NULL DEFAULT 0",
        ]:
            try:
                conn.execute(col_sql)
            except sqlite3.OperationalError:
                pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tokens (
                token_id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL UNIQUE,
                library_id TEXT NOT NULL,
                label TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'writer',
                created_at TEXT NOT NULL
            )
            """
        )
        # Migration: add role column to tokens if it was created without it
        try:
            conn.execute("ALTER TABLE tokens ADD COLUMN role TEXT NOT NULL DEFAULT 'writer'")
        except sqlite3.OperationalError:
            pass  # column already exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invite_codes (
                code_id TEXT PRIMARY KEY,
                code_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                used_at TEXT,
                used_by_library_id TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS records (
                record_id TEXT PRIMARY KEY,
                library_id TEXT,
                payload_json TEXT NOT NULL
            )
            """
        )
        # Migration: add library_id column to records if it was created without it
        try:
            conn.execute("ALTER TABLE records ADD COLUMN library_id TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        # Migration: add extracted status column for efficient filtering
        try:
            conn.execute("ALTER TABLE records ADD COLUMN status TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        conn.execute(
            "UPDATE records SET status = json_extract(payload_json, '$.status') WHERE status IS NULL"
        )
        # Indexes for common filter columns
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_records_library ON records(library_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_records_status ON records(status)"
        )
        # Migration: drop contentless FTS5 tables if they were created with content=''.
        # Contentless FTS5 tables do not store column data, so WHERE/DELETE on
        # UNINDEXED columns silently returns/deletes nothing. Dropping forces a
        # clean rebuild as a regular FTS5 table (with full column storage).
        for _tbl in ("records_fts_tags", "records_fts_content"):
            _row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (_tbl,)
            ).fetchone()
            if _row and "content=''" in (_row[0] or ""):
                conn.execute(f"DROP TABLE {_tbl}")

        # FTS5: tag index — precise matching against agent-supplied tags
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS records_fts_tags USING fts5(
                record_id UNINDEXED,
                tags,
                tokenize='unicode61'
            )
            """
        )
        # FTS5: content index — broad matching against title/summary/claim
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS records_fts_content USING fts5(
                record_id UNINDEXED,
                title,
                problem_family,
                summary,
                claim,
                tokenize='unicode61'
            )
            """
        )
        # Vector embeddings table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS record_embeddings (
                record_id TEXT PRIMARY KEY,
                embedding BLOB NOT NULL,
                model TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                feedback_id TEXT PRIMARY KEY,
                record_id TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS relations (
                relation_id TEXT PRIMARY KEY,
                from_record_id TEXT NOT NULL,
                to_record_id TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )

    seed_if_empty()
    if run_backfill:
        backfill_search_indexes()


def backfill_search_indexes() -> None:
    """Populate FTS and embedding tables for records that are missing entries.

    Runs at startup; safe to call multiple times (skips already-indexed records).
    """
    from app.storage.repositories import RecordRepository
    from app.storage.fts import fts_upsert
    from app.services.embedding_service import embed_record, serialize_embedding
    from app.core.time import utc_now_iso

    repo = RecordRepository()
    with get_connection() as conn:
        indexed_tag_ids = {
            row[0]
            for row in conn.execute("SELECT record_id FROM records_fts_tags").fetchall()
        }
        indexed_emb_ids = {
            row[0]
            for row in conn.execute(
                "SELECT record_id FROM record_embeddings"
            ).fetchall()
        }

    all_records = repo.list_all()
    now = utc_now_iso()

    with get_connection() as conn:
        for record in all_records:
            if record.record_id not in indexed_tag_ids:
                fts_upsert(conn, record)
            if record.record_id not in indexed_emb_ids:
                embedding = embed_record(record)
                if embedding is not None:
                    conn.execute(
                        "INSERT OR REPLACE INTO record_embeddings"
                        "(record_id, embedding, model, created_at) VALUES (?,?,?,?)",
                        (
                            record.record_id,
                            serialize_embedding(embedding),
                            "all-MiniLM-L6-v2",
                            now,
                        ),
                    )


def seed_if_empty() -> None:
    from app.storage.repositories import RecordRepository

    repo = RecordRepository()
    if repo.count() > 0:
        return
    if not settings.seed_path.exists():
        return
    payload = json.loads(settings.seed_path.read_text(encoding="utf-8"))
    for item in payload:
        repo.insert(Record.model_validate(item))
