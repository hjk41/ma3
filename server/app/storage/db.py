import json
import sqlite3
from typing import Any

from app.core.config import settings
from app.models.record import Record

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - exercised only when postgres deps are absent
    psycopg = None
    dict_row = None


class DatabaseConnection:
    def __init__(self, raw_connection: Any, backend: str):
        self._raw = raw_connection
        self.backend = backend

    def __enter__(self) -> "DatabaseConnection":
        self._raw.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool | None:
        return self._raw.__exit__(exc_type, exc, tb)

    def execute(self, sql: str, params: list | tuple | dict | None = None):
        if self.backend == "postgresql":
            sql = sql.replace("?", "%s")
        return self._raw.execute(sql, params or ())


def is_postgres() -> bool:
    return settings.db_backend == "postgresql"


def _connect_sqlite() -> DatabaseConnection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return DatabaseConnection(conn, "sqlite")


def _connect_postgres() -> DatabaseConnection:
    if not settings.database_url:
        raise RuntimeError("MA3_DATABASE_URL is required for PostgreSQL mode")
    if psycopg is None:
        raise RuntimeError(
            "PostgreSQL mode requires psycopg. Install server requirements again."
        )
    conn = psycopg.connect(settings.database_url, row_factory=dict_row)
    return DatabaseConnection(conn, "postgresql")


def get_connection() -> DatabaseConnection:
    if is_postgres():
        return _connect_postgres()
    return _connect_sqlite()


def initialize_database(run_backfill: bool = True) -> None:
    if is_postgres():
        _initialize_postgres()
    else:
        _initialize_sqlite()

    seed_if_empty()
    if run_backfill:
        backfill_search_indexes()


def _initialize_sqlite() -> None:
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
        try:
            conn.execute("ALTER TABLE tokens ADD COLUMN role TEXT NOT NULL DEFAULT 'writer'")
        except sqlite3.OperationalError:
            pass
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
        try:
            conn.execute("ALTER TABLE records ADD COLUMN library_id TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE records ADD COLUMN status TEXT")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            "UPDATE records SET status = json_extract(payload_json, '$.status') WHERE status IS NULL"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_records_library ON records(library_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_records_status ON records(status)")

        for table_name in ("records_fts_tags", "records_fts_content"):
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            ).fetchone()
            if row and "content=''" in (row["sql"] or ""):
                conn.execute(f"DROP TABLE {table_name}")

        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS records_fts_tags USING fts5(
                record_id UNINDEXED,
                tags,
                tokenize='unicode61'
            )
            """
        )
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


def _initialize_postgres() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS libraries (
                library_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                is_public BOOLEAN NOT NULL DEFAULT TRUE,
                parent_library_id TEXT,
                is_personal BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "ALTER TABLE libraries ADD COLUMN IF NOT EXISTS parent_library_id TEXT"
        )
        conn.execute(
            "ALTER TABLE libraries ADD COLUMN IF NOT EXISTS is_personal BOOLEAN NOT NULL DEFAULT FALSE"
        )
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
        conn.execute(
            "ALTER TABLE tokens ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'writer'"
        )
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
                status TEXT,
                payload_json JSONB NOT NULL
            )
            """
        )
        conn.execute("ALTER TABLE records ADD COLUMN IF NOT EXISTS library_id TEXT")
        conn.execute("ALTER TABLE records ADD COLUMN IF NOT EXISTS status TEXT")
        conn.execute(
            "UPDATE records SET status = payload_json->>'status' WHERE status IS NULL"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_records_library ON records(library_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_records_status ON records(status)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS record_embeddings (
                record_id TEXT PRIMARY KEY,
                embedding BYTEA NOT NULL,
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
                payload_json JSONB NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS relations (
                relation_id TEXT PRIMARY KEY,
                from_record_id TEXT NOT NULL,
                to_record_id TEXT NOT NULL,
                payload_json JSONB NOT NULL
            )
            """
        )


def backfill_search_indexes() -> None:
    from app.services.embedding_service import embed_record, serialize_embedding
    from app.storage.fts import fts_upsert
    from app.storage.repositories import RecordRepository
    from app.core.time import utc_now_iso

    repo = RecordRepository()
    with get_connection() as conn:
        indexed_emb_ids = {
            row["record_id"]
            for row in conn.execute("SELECT record_id FROM record_embeddings").fetchall()
        }
        indexed_tag_ids = set()
        if not is_postgres():
            indexed_tag_ids = {
                row["record_id"]
                for row in conn.execute("SELECT record_id FROM records_fts_tags").fetchall()
            }

    all_records = repo.list_all()
    now = utc_now_iso()

    with get_connection() as conn:
        for record in all_records:
            if not is_postgres() and record.record_id not in indexed_tag_ids:
                fts_upsert(conn, record)
            if record.record_id not in indexed_emb_ids:
                embedding = embed_record(record)
                if embedding is not None:
                    conn.execute(
                        _upsert(
                            "record_embeddings",
                            ["record_id"],
                            ["record_id", "embedding", "model", "created_at"],
                        ),
                        (
                            record.record_id,
                            serialize_embedding(embedding),
                            "all-MiniLM-L6-v2",
                            now,
                        ),
                    )


def seed_if_empty() -> None:
    from app.storage.fts import fts_upsert

    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM records").fetchone()
    if row and int(row["count"]) > 0:
        return
    if not settings.seed_path.exists():
        return
    payload = json.loads(settings.seed_path.read_text(encoding="utf-8"))
    records = [Record.model_validate(item) for item in payload]
    with get_connection() as conn:
        for record in records:
            conn.execute(
                _upsert(
                    "records",
                    ["record_id"],
                    ["record_id", "library_id", "status", "payload_json"],
                ),
                (
                    record.record_id,
                    record.library_id,
                    record.status.value,
                    _json_param(record.model_dump()),
                ),
            )
            if not is_postgres():
                fts_upsert(conn, record)


def _upsert(table: str, key_columns: list[str], all_columns: list[str]) -> str:
    placeholders = ", ".join(["?"] * len(all_columns))
    column_sql = ", ".join(all_columns)
    if settings.db_backend == "postgresql":
        update_sql = ", ".join(
            f"{col} = EXCLUDED.{col}" for col in all_columns if col not in key_columns
        )
        conflict_sql = ", ".join(key_columns)
        return (
            f"INSERT INTO {table}({column_sql}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_sql}) DO UPDATE SET {update_sql}"
        )
    return f"INSERT OR REPLACE INTO {table}({column_sql}) VALUES ({placeholders})"


def _json_param(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)
