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

try:
    from psycopg_pool import ConnectionPool
except ImportError:  # pragma: no cover - exercised only when postgres deps are absent
    ConnectionPool = None

from app.services.perf_service import record_connection_checkout, record_db_query


class DatabaseConnection:
    def __init__(self, raw_connection: Any, backend: str, context_manager: Any | None = None):
        self._raw = raw_connection
        self.backend = backend
        self._context_manager = context_manager

    def __enter__(self) -> "DatabaseConnection":
        if self._context_manager is not None:
            self._raw = self._context_manager.__enter__()
        else:
            self._raw.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool | None:
        if self._context_manager is not None:
            return self._context_manager.__exit__(exc_type, exc, tb)
        return self._raw.__exit__(exc_type, exc, tb)

    def execute(self, sql: str, params: list | tuple | dict | None = None):
        if self.backend == "postgresql":
            sql = sql.replace("?", "%s")
        operation = sql.strip().split(None, 1)[0].lower() if sql.strip() else "execute"
        record_db_query(operation)
        return self._raw.execute(sql, params or ())


def is_postgres() -> bool:
    return settings.db_backend == "postgresql"


def _connect_sqlite() -> DatabaseConnection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return DatabaseConnection(conn, "sqlite")


_pg_pool: Any | None = None


def _get_postgres_pool():
    global _pg_pool
    if not settings.database_url:
        raise RuntimeError("MA3_DATABASE_URL is required for PostgreSQL mode")
    if psycopg is None:
        raise RuntimeError(
            "PostgreSQL mode requires psycopg. Install server requirements again."
        )
    if ConnectionPool is None:
        raise RuntimeError(
            "PostgreSQL pooling requires psycopg_pool. Install psycopg[pool]."
        )
    if _pg_pool is None:
        _pg_pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            timeout=settings.db_pool_timeout_seconds,
            kwargs={"row_factory": dict_row},
            open=True,
        )
    return _pg_pool


def close_postgres_pool() -> None:
    global _pg_pool
    if _pg_pool is not None:
        _pg_pool.close()
        _pg_pool = None


def _connect_postgres() -> DatabaseConnection:
    if not settings.db_pool_enabled:
        if not settings.database_url:
            raise RuntimeError("MA3_DATABASE_URL is required for PostgreSQL mode")
        if psycopg is None:
            raise RuntimeError(
                "PostgreSQL mode requires psycopg. Install server requirements again."
            )
        record_connection_checkout()
        return DatabaseConnection(
            psycopg.connect(settings.database_url, row_factory=dict_row),
            "postgresql",
        )
    pool = _get_postgres_pool()
    record_connection_checkout()
    return DatabaseConnection(None, "postgresql", context_manager=pool.connection())


def get_connection() -> DatabaseConnection:
    if is_postgres():
        return _connect_postgres()
    record_connection_checkout()
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
        _initialize_auth_sqlite(conn)
        _initialize_v2_sqlite(conn)


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
        _ensure_postgres_jsonb_payload(conn, "records")
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
        _ensure_postgres_jsonb_payload(conn, "feedback")
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
        _ensure_postgres_jsonb_payload(conn, "relations")
        _initialize_auth_postgres(conn)
        _initialize_v2_postgres(conn)


def _initialize_auth_sqlite(conn: DatabaseConnection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS principals (
            principal_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            display_name TEXT NOT NULL,
            sso_user TEXT,
            created_at TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_principals_sso_user "
        "ON principals(sso_user) WHERE sso_user IS NOT NULL"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            key_id TEXT PRIMARY KEY,
            key_hash TEXT NOT NULL UNIQUE,
            principal_id TEXT NOT NULL REFERENCES principals(principal_id),
            label TEXT NOT NULL,
            scope_libraries TEXT,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL REFERENCES principals(principal_id),
            last_used_at TEXT,
            expires_at TEXT,
            revoked_at TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_principal ON api_keys(principal_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(revoked_at) "
        "WHERE revoked_at IS NULL"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS library_acl (
            library_id TEXT NOT NULL REFERENCES libraries(library_id) ON DELETE CASCADE,
            principal_id TEXT NOT NULL REFERENCES principals(principal_id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('reader','writer','admin')),
            granted_at TEXT NOT NULL,
            granted_by TEXT NOT NULL REFERENCES principals(principal_id),
            PRIMARY KEY (library_id, principal_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_acl_principal ON library_acl(principal_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_audit_log (
            audit_id TEXT PRIMARY KEY,
            actor_principal_id TEXT NOT NULL,
            action TEXT NOT NULL,
            target_principal_id TEXT,
            library_id TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_created_at ON auth_audit_log(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_actor ON auth_audit_log(actor_principal_id)")


def _initialize_auth_postgres(conn: DatabaseConnection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS principals (
            principal_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            display_name TEXT NOT NULL,
            sso_user TEXT,
            created_at TEXT NOT NULL,
            is_admin BOOLEAN NOT NULL DEFAULT FALSE,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_principals_sso_user "
        "ON principals(sso_user) WHERE sso_user IS NOT NULL"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            key_id TEXT PRIMARY KEY,
            key_hash TEXT NOT NULL UNIQUE,
            principal_id TEXT NOT NULL REFERENCES principals(principal_id),
            label TEXT NOT NULL,
            scope_libraries JSONB,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL REFERENCES principals(principal_id),
            last_used_at TEXT,
            expires_at TEXT,
            revoked_at TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_principal ON api_keys(principal_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(revoked_at) "
        "WHERE revoked_at IS NULL"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS library_acl (
            library_id TEXT NOT NULL REFERENCES libraries(library_id) ON DELETE CASCADE,
            principal_id TEXT NOT NULL REFERENCES principals(principal_id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('reader','writer','admin')),
            granted_at TEXT NOT NULL,
            granted_by TEXT NOT NULL REFERENCES principals(principal_id),
            PRIMARY KEY (library_id, principal_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_acl_principal ON library_acl(principal_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_audit_log (
            audit_id TEXT PRIMARY KEY,
            actor_principal_id TEXT NOT NULL,
            action TEXT NOT NULL,
            target_principal_id TEXT,
            library_id TEXT,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_created_at ON auth_audit_log(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_actor ON auth_audit_log(actor_principal_id)")


def _ensure_postgres_jsonb_payload(conn: DatabaseConnection, table: str) -> None:
    """Normalize legacy PostgreSQL JSON payload columns to JSONB.

    v1 dumps may contain payload_json TEXT because the shared repository code
    stored JSON as strings for SQLite compatibility. v2 PostgreSQL queries use
    JSONB operators, so normalize before any -> or ->> expression runs. The cast
    is idempotent when the column is already JSONB.
    """
    if table not in {"records", "feedback", "relations"}:
        raise ValueError(f"unexpected payload table: {table}")
    conn.execute(
        f"ALTER TABLE {table} ALTER COLUMN payload_json TYPE JSONB USING payload_json::jsonb"
    )


def _initialize_v2_sqlite(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cases (
            case_id TEXT PRIMARY KEY,
            library_id TEXT,
            state TEXT NOT NULL,
            target_product TEXT NOT NULL DEFAULT '',
            target_component TEXT,
            updated_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_library_state ON cases(library_id, state)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_target ON cases(target_product, target_component)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS search_events (
            event_id TEXT PRIMARY KEY,
            library_id TEXT,
            created_at TEXT NOT NULL,
            route TEXT NOT NULL,
            latency_ms REAL NOT NULL DEFAULT 0,
            result_count INTEGER NOT NULL DEFAULT 0,
            case_count INTEGER NOT NULL DEFAULT 0,
            full_scan INTEGER NOT NULL DEFAULT 0,
            error_type TEXT,
            query_hash TEXT,
            payload_json TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_search_events_created ON search_events(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_search_events_hash ON search_events(query_hash)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS search_feedback (
            feedback_id TEXT PRIMARY KEY,
            query_hash TEXT,
            record_id TEXT,
            case_id TEXT,
            judgment TEXT NOT NULL,
            created_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_search_feedback_judgment ON search_feedback(judgment)")


def _initialize_v2_postgres(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cases (
            case_id TEXT PRIMARY KEY,
            library_id TEXT,
            state TEXT NOT NULL,
            target_product TEXT NOT NULL DEFAULT '',
            target_component TEXT,
            updated_at TEXT NOT NULL,
            payload_json JSONB NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_library_state ON cases(library_id, state)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_target ON cases(target_product, target_component)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS search_events (
            event_id TEXT PRIMARY KEY,
            library_id TEXT,
            created_at TEXT NOT NULL,
            route TEXT NOT NULL,
            latency_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
            result_count INTEGER NOT NULL DEFAULT 0,
            case_count INTEGER NOT NULL DEFAULT 0,
            full_scan BOOLEAN NOT NULL DEFAULT FALSE,
            error_type TEXT,
            query_hash TEXT,
            payload_json JSONB NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_search_events_created ON search_events(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_search_events_hash ON search_events(query_hash)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS search_feedback (
            feedback_id TEXT PRIMARY KEY,
            query_hash TEXT,
            record_id TEXT,
            case_id TEXT,
            judgment TEXT NOT NULL,
            created_at TEXT NOT NULL,
            payload_json JSONB NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_search_feedback_judgment ON search_feedback(judgment)")
    conn.execute(
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
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_record_search_index_search_tsv ON record_search_index USING GIN(search_tsv)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_record_search_index_tags_tsv ON record_search_index USING GIN(tags_tsv)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_record_search_index_library_status ON record_search_index(library_id, status)")


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
            if is_postgres() or record.record_id not in indexed_tag_ids:
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
