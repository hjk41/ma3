from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.core.config import settings

_pgvector_ready = False


def pgvector_ready() -> bool:
    return _pgvector_ready and is_postgres()


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
            try:
                from pgvector.psycopg import register_vector

                register_vector(conn)
            except Exception:
                pass
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
    blob_type = "BYTEA NOT NULL" if is_postgres() else "BLOB NOT NULL"
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
              visibility TEXT NOT NULL DEFAULT 'private',
              kind TEXT NOT NULL DEFAULT 'custom',
              owner_principal_id TEXT
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
              created_by TEXT,
              created_at TEXT NOT NULL
            )
            """,
        )
        if not _column_exists(conn, "records", "created_by"):
            _execute(conn, "ALTER TABLE records ADD COLUMN created_by TEXT")
        _execute(conn, "CREATE INDEX IF NOT EXISTS idx_records_library_status ON records(library_id, status)")
        _execute(conn, "CREATE INDEX IF NOT EXISTS idx_records_case ON records(case_id)")
        _execute(conn, "CREATE INDEX IF NOT EXISTS idx_records_created_by ON records(created_by)")
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
            CREATE TABLE IF NOT EXISTS record_feedback (
              record_id TEXT NOT NULL,
              principal_id TEXT NOT NULL,
              vote INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY (record_id, principal_id),
              CHECK (vote IN (1, -1))
            )
            """,
        )
        _execute(conn, "CREATE INDEX IF NOT EXISTS idx_record_feedback_record ON record_feedback(record_id)")
        _execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS record_relations (
              source_id TEXT NOT NULL,
              target_id TEXT NOT NULL,
              relation_type TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY (source_id, target_id, relation_type)
            )
            """,
        )
        _execute(conn, "CREATE INDEX IF NOT EXISTS idx_record_relations_target ON record_relations(target_id, relation_type)")
        _execute(
            conn,
            f"""
            CREATE TABLE IF NOT EXISTS record_embeddings (
              record_id TEXT PRIMARY KEY,
              embedding {blob_type},
              model TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """,
        )
        # library_id/status are plain columns required by the write path
        # (upsert_record_embedding) on BOTH backends. They must be added in the
        # schema transaction, independent of pgvector — only embedding_vec and
        # the HNSW index depend on the vector extension (see _migrate_pgvector).
        if not _column_exists(conn, "record_embeddings", "library_id"):
            _execute(conn, "ALTER TABLE record_embeddings ADD COLUMN library_id TEXT")
        if not _column_exists(conn, "record_embeddings", "status"):
            _execute(conn, "ALTER TABLE record_embeddings ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
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
                (settings.default_library_id, settings.default_org_id, "Community Library", "public"),
            )
        else:
            _execute(
                conn,
                "UPDATE libraries SET name = ?, visibility = ? WHERE id = ?",
                ("Community Library", "public", settings.default_library_id),
            )

        if not _column_exists(conn, "libraries", "kind"):
            _execute(conn, "ALTER TABLE libraries ADD COLUMN kind TEXT NOT NULL DEFAULT 'custom'")
        if not _column_exists(conn, "libraries", "owner_principal_id"):
            _execute(conn, "ALTER TABLE libraries ADD COLUMN owner_principal_id TEXT")
        _execute(
            conn,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_libraries_personal_owner
            ON libraries (owner_principal_id)
            WHERE kind = 'personal' AND owner_principal_id IS NOT NULL
            """,
        )
        _execute(
            conn,
            "UPDATE libraries SET kind = ?, owner_principal_id = NULL WHERE id = ?",
            ("community", settings.default_library_id),
        )
        _sync_legacy_library(
            settings.default_library_id,
            org_id=settings.default_org_id,
            name="Community Library",
            visibility="public",
        )

        if not _column_exists(conn, "libraries", "deletion_protection"):
            _execute(conn, "ALTER TABLE libraries ADD COLUMN deletion_protection INTEGER NOT NULL DEFAULT 0")
        if not _column_exists(conn, "libraries", "retention_days"):
            _execute(conn, "ALTER TABLE libraries ADD COLUMN retention_days INTEGER NOT NULL DEFAULT 30")
        if not _column_exists(conn, "records", "trashed_at"):
            _execute(conn, "ALTER TABLE records ADD COLUMN trashed_at TEXT")
        if not _column_exists(conn, "libraries", "write_buffer_hours"):
            _execute(conn, "ALTER TABLE libraries ADD COLUMN write_buffer_hours INTEGER NOT NULL DEFAULT 24")
        if not _column_exists(conn, "records", "publish_at"):
            _execute(conn, "ALTER TABLE records ADD COLUMN publish_at TEXT")
        if not _column_exists(conn, "principals", "display_name_locked"):
            _execute(conn, "ALTER TABLE principals ADD COLUMN display_name_locked INTEGER NOT NULL DEFAULT 0")
        if not _column_exists(conn, "record_relations", "source_deleted"):
            _execute(conn, "ALTER TABLE record_relations ADD COLUMN source_deleted INTEGER NOT NULL DEFAULT 0")

        _execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS write_audit_log (
              id TEXT PRIMARY KEY,
              record_id TEXT NOT NULL,
              library_id TEXT NOT NULL,
              principal_id TEXT NOT NULL,
              api_key_id TEXT NOT NULL,
              report_kind TEXT NOT NULL,
              confirmation TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """,
        )
        _execute(conn, "CREATE INDEX IF NOT EXISTS idx_write_audit_principal ON write_audit_log (principal_id, created_at DESC)")
        _execute(conn, "CREATE INDEX IF NOT EXISTS idx_write_audit_record ON write_audit_log (record_id)")

        _execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS record_deletions (
              record_id TEXT PRIMARY KEY,
              library_id TEXT NOT NULL,
              deleted_by TEXT NOT NULL,
              deleted_at TEXT NOT NULL
            )
            """,
        )

        _execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS report_idempotency (
              idempotency_key TEXT NOT NULL,
              principal_id TEXT NOT NULL,
              record_id TEXT NOT NULL,
              payload_hash TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY (idempotency_key, principal_id)
            )
            """,
        )

        # DB-backed API keys (design/08 §4.2, Phase 2). CREATE IF NOT EXISTS is a
        # no-op where these tables were provisioned by the earlier v4 key-issuance
        # API (e.g. 202), and creates them for fresh installs / sqlite tests.
        _execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS api_keys (
              key_id TEXT PRIMARY KEY,
              key_hash TEXT NOT NULL UNIQUE,
              principal_id TEXT NOT NULL,
              label TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL,
              created_by TEXT,
              last_used_at TEXT,
              expires_at TEXT,
              revoked_at TEXT
            )
            """,
        )
        _execute(conn, "CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys (key_hash)")
        _execute(conn, "CREATE INDEX IF NOT EXISTS idx_api_keys_principal ON api_keys (principal_id)")
        if not _column_exists(conn, "api_keys", "key_prefix"):
            _execute(conn, "ALTER TABLE api_keys ADD COLUMN key_prefix TEXT")
        if not _column_exists(conn, "api_keys", "key_ciphertext"):
            _execute(conn, "ALTER TABLE api_keys ADD COLUMN key_ciphertext TEXT")
        _execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS api_key_grants (
              key_id TEXT NOT NULL,
              library_id TEXT NOT NULL,
              role TEXT NOT NULL,
              PRIMARY KEY (key_id, library_id)
            )
            """,
        )

    # Attribute pre-existing records to their authors so ma3_list_my_writes can
    # enumerate historical uploads. Idempotent; runs after the schema commits.
    backfill_write_audit_log()

    # pgvector setup runs in its OWN connection/transaction. CREATE EXTENSION
    # fails when the pgvector package is absent, which aborts the transaction;
    # keeping it out of the schema transaction above prevents that failure from
    # rolling back all table creation (commit on an aborted tx = rollback).
    if is_postgres():
        _run_pgvector_migration()


def _run_pgvector_migration() -> None:
    try:
        with connect() as conn:
            _migrate_pgvector(conn)
    except Exception:
        pass


def _migrate_pgvector(conn: Any) -> None:
    global _pgvector_ready
    _pgvector_ready = False
    # The app role (e.g. ma3user) often lacks CREATE EXTENSION; deploys pre-create
    # the extension as a superuser. Only attempt CREATE when it is actually missing
    # so a permission error does not abort the rest of the vector migration (which
    # adds embedding_vec + the HNSW index and must run on a fresh schema too).
    already = _fetchone(conn, "SELECT 1 FROM pg_extension WHERE extname = 'vector'")
    if not already:
        try:
            _execute(conn, "CREATE EXTENSION IF NOT EXISTS vector")
        except Exception:
            return
    dim = settings.embedding_dim
    if not _column_exists(conn, "record_embeddings", "library_id"):
        _execute(conn, "ALTER TABLE record_embeddings ADD COLUMN library_id TEXT")
    if not _column_exists(conn, "record_embeddings", "status"):
        _execute(conn, f"ALTER TABLE record_embeddings ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
    vec_col = f"embedding_vec vector({dim})"
    if not _column_exists(conn, "record_embeddings", "embedding_vec"):
        _execute(conn, f"ALTER TABLE record_embeddings ADD COLUMN {vec_col}")
    _execute(
        conn,
        """
        UPDATE record_embeddings e
        SET library_id = r.library_id,
            status = r.status
        FROM records r
        WHERE r.id = e.record_id AND e.library_id IS NULL
        """,
    )
    rows = _fetchall(
        conn,
        "SELECT record_id, embedding FROM record_embeddings WHERE embedding_vec IS NULL",
    )
    from app.services.embedding_service import deserialize_embedding, vector_as_list

    for row in rows:
        blob = row["embedding"]
        if blob is None:
            continue
        if isinstance(blob, memoryview):
            blob = blob.tobytes()
        try:
            vec = vector_as_list(deserialize_embedding(blob))
        except Exception:
            continue
        _execute(
            conn,
            "UPDATE record_embeddings SET embedding_vec = ?::vector WHERE record_id = ?",
            (vec, row["record_id"]),
        )
    try:
        _execute(
            conn,
            f"""
            CREATE INDEX IF NOT EXISTS idx_record_embeddings_hnsw
            ON record_embeddings USING hnsw (embedding_vec vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
            """,
        )
    except Exception:
        pass
    _pgvector_ready = True


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _search_tokens(problem: str) -> list[str]:
    import re

    tokens = [t for t in re.split(r"\s+", problem.strip()) if len(t) >= 2]
    return tokens[:10] or [problem[:200]]


def _fetch_records_by_ids(
    record_ids: list[str],
    library_ids: set[str],
    *,
    active_only: bool = True,
    include_payload: bool = False,
) -> list[dict[str, Any]]:
    if not record_ids or not library_ids:
        return []
    id_placeholders = ",".join("?" for _ in record_ids)
    lib_placeholders = ",".join("?" for _ in library_ids)
    payload_col = ", payload_json" if include_payload else ""
    status_clause = " AND status = 'active'" if active_only else ""
    query = f"""
        SELECT id, library_id, case_id, status, problem, outcome, result_summary, created_at{payload_col}
        FROM records
        WHERE id IN ({id_placeholders})
          AND library_id IN ({lib_placeholders}){status_clause}
    """
    with connect() as conn:
        rows = _fetchall(conn, query, [*record_ids, *library_ids])
    out: list[dict[str, Any]] = []
    for row in rows:
        item = _row_dict(row)
        if include_payload and "payload_json" in item:
            payload = item.pop("payload_json")
            if isinstance(payload, str):
                item["payload"] = json.loads(payload)
            else:
                item["payload"] = payload
        out.append(item)
    return out


def _list_active_record_ids(library_ids: set[str], limit: int | None = None) -> set[str]:
    if not library_ids:
        return set()
    if limit is None:
        limit = settings.vector_scan_limit
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


def count_active_records(library_ids: set[str] | None = None) -> int:
    with connect() as conn:
        if library_ids:
            placeholders = ",".join("?" for _ in library_ids)
            row = _fetchone(
                conn,
                f"SELECT COUNT(*) AS c FROM records WHERE status = 'active' AND library_id IN ({placeholders})",
                list(library_ids),
            )
        else:
            row = _fetchone(conn, "SELECT COUNT(*) AS c FROM records WHERE status = 'active'")
    return int(row["c"])


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
    parts = [problem, outcome, result_summary]
    for action in payload.get("actions") or []:
        if isinstance(action, dict) and action.get("action"):
            parts.append(str(action["action"]))
    for item in payload.get("evidence") or []:
        if isinstance(item, dict) and item.get("summary"):
            parts.append(str(item["summary"]))
    for key in ("applicable_if", "not_applicable_if"):
        for rule in payload.get(key) or []:
            parts.append(str(rule))
    env = payload.get("environment")
    if isinstance(env, dict):
        parts.extend(f"{k}={v}" for k, v in env.items() if v is not None)
    target = payload.get("target")
    if isinstance(target, dict):
        parts.extend(str(target.get(k)) for k in ("product", "component") if target.get(k))
    search_text = " ".join(part for part in parts if part)
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


def upsert_record_embedding(
    *,
    record_id: str,
    embedding: bytes,
    model: str,
    created_at: str,
    library_id: str,
    status: str,
) -> None:
    from app.services.embedding_service import deserialize_embedding, vector_as_list

    with connect() as conn:
        vec_list: list[float] | None = None
        if is_postgres() and pgvector_ready():
            try:
                vec_list = vector_as_list(deserialize_embedding(embedding))
            except Exception:
                vec_list = None
        if is_postgres() and vec_list is not None:
            _execute(
                conn,
                """
                INSERT INTO record_embeddings (
                    record_id, embedding, model, created_at, library_id, status, embedding_vec
                )
                VALUES (?, ?, ?, ?, ?, ?, ?::vector)
                ON CONFLICT (record_id) DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    model = EXCLUDED.model,
                    created_at = EXCLUDED.created_at,
                    library_id = EXCLUDED.library_id,
                    status = EXCLUDED.status,
                    embedding_vec = EXCLUDED.embedding_vec
                """,
                (record_id, embedding, model, created_at, library_id, status, vec_list),
            )
            return
        if is_postgres():
            _execute(
                conn,
                """
                INSERT INTO record_embeddings (record_id, embedding, model, created_at, library_id, status)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (record_id) DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    model = EXCLUDED.model,
                    created_at = EXCLUDED.created_at,
                    library_id = EXCLUDED.library_id,
                    status = EXCLUDED.status
                """,
                (record_id, embedding, model, created_at, library_id, status),
            )
            return
        _execute(
            conn,
            """
            INSERT INTO record_embeddings (record_id, embedding, model, created_at, library_id, status)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (record_id) DO UPDATE SET
                embedding = excluded.embedding,
                model = excluded.model,
                created_at = excluded.created_at,
                library_id = excluded.library_id,
                status = excluded.status
            """,
            (record_id, embedding, model, created_at, library_id, status),
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
    if status == "buffered":
        return
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
    if status == "invalid":
        _delete_record_embeddings(record_id)
        return
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
        library_id=library_id,
        status=status,
    )


def ann_vector_search(library_ids: set[str], query_vector: Any, limit: int) -> dict[str, float]:
    if not pgvector_ready() or not library_ids:
        return {}
    from app.services.embedding_service import vector_as_list

    try:
        vec_list = vector_as_list(query_vector)
    except Exception:
        return {}
    placeholders = ",".join("?" for _ in library_ids)
    sql = f"""
        SELECT record_id, 1 - (embedding_vec <=> ?::vector) AS score
        FROM record_embeddings
        WHERE embedding_vec IS NOT NULL
          AND library_id IN ({placeholders})
          AND status = 'active'
        ORDER BY embedding_vec <=> ?::vector
        LIMIT ?
    """
    params: list[Any] = [vec_list, *library_ids, vec_list, limit]
    with connect() as conn:
        _execute(conn, "SET LOCAL hnsw.ef_search = 80")
        rows = _fetchall(conn, sql, params)
    out: dict[str, float] = {}
    for row in rows:
        score = max(0.0, float(row["score"]))
        if score > 0:
            out[str(row["record_id"])] = score
    return out


def get_idempotent_report(idempotency_key: str, principal_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = _fetchone(
            conn,
            """
            SELECT idempotency_key, principal_id, record_id, payload_hash, created_at
            FROM report_idempotency
            WHERE idempotency_key = ? AND principal_id = ?
            """,
            (idempotency_key, principal_id),
        )
    return _row_dict(row) if row else None


def insert_record(
    *,
    library_id: str,
    case_id: str | None,
    status: str,
    problem: str,
    outcome: str,
    result_summary: str,
    payload: dict[str, Any],
    idempotency_key: str | None = None,
    principal_id: str | None = None,
    payload_hash: str | None = None,
    publish_at: str | None = None,
) -> dict[str, Any]:
    from datetime import datetime, timezone

    rid = new_id("vk")
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    raw = json.dumps(payload)
    idempotent_replay = False
    with connect() as conn:
        if idempotency_key and principal_id:
            existing = _fetchone(
                conn,
                """
                SELECT record_id, payload_hash
                FROM report_idempotency
                WHERE idempotency_key = ? AND principal_id = ?
                """,
                (idempotency_key, principal_id),
            )
            if existing:
                if payload_hash and str(existing["payload_hash"]) != payload_hash:
                    from fastapi import HTTPException

                    raise HTTPException(status_code=409, detail="idempotency_key reused with different payload")
                rid = str(existing["record_id"])
                idempotent_replay = True
                row = _fetchone(conn, "SELECT library_id, case_id, status, created_at FROM records WHERE id = ?", (rid,))
                if not row:
                    idempotent_replay = False
                else:
                    return {
                        "record_id": rid,
                        "library_id": row["library_id"],
                        "case_id": row["case_id"],
                        "status": row["status"],
                        "created_at": row["created_at"],
                        "idempotent_replay": True,
                    }
        if is_postgres():
            _execute(
                conn,
                """
                INSERT INTO records (id, library_id, case_id, status, problem, outcome, result_summary, payload_json, created_by, created_at, publish_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?::jsonb, ?, ?, ?)
                """,
                (rid, library_id, case_id, status, problem, outcome, result_summary, raw, principal_id, now, publish_at),
            )
        else:
            _execute(
                conn,
                """
                INSERT INTO records (id, library_id, case_id, status, problem, outcome, result_summary, payload_json, created_by, created_at, publish_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (rid, library_id, case_id, status, problem, outcome, result_summary, raw, principal_id, now, publish_at),
            )
        if idempotency_key and principal_id and payload_hash:
            _execute(
                conn,
                """
                INSERT INTO report_idempotency (idempotency_key, principal_id, record_id, payload_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (idempotency_key, principal_id) DO NOTHING
                """,
                (idempotency_key, principal_id, rid, payload_hash, now),
            )
            winner = _fetchone(
                conn,
                """
                SELECT record_id, payload_hash
                FROM report_idempotency
                WHERE idempotency_key = ? AND principal_id = ?
                """,
                (idempotency_key, principal_id),
            )
            if winner and str(winner["record_id"]) != rid:
                _execute(conn, "DELETE FROM records WHERE id = ?", (rid,))
                if payload_hash != str(winner["payload_hash"]):
                    from fastapi import HTTPException

                    raise HTTPException(status_code=409, detail="idempotency_key reused with different payload")
                rid = str(winner["record_id"])
                idempotent_replay = True
                row = _fetchone(conn, "SELECT library_id, case_id, status, created_at FROM records WHERE id = ?", (rid,))
                if row:
                    return {
                        "record_id": rid,
                        "library_id": row["library_id"],
                        "case_id": row["case_id"],
                        "status": row["status"],
                        "created_at": row["created_at"],
                        "idempotent_replay": True,
                    }
    if idempotent_replay:
        sync_record_search_index(rid)
        row = get_record(rid)
        return {
            "record_id": rid,
            "library_id": row["library_id"] if row else library_id,
            "case_id": row["case_id"] if row else case_id,
            "status": row["status"] if row else status,
            "created_at": row["created_at"] if row else now,
            "idempotent_replay": True,
        }
    if status == "buffered":
        return {
            "record_id": rid,
            "library_id": library_id,
            "case_id": case_id,
            "status": status,
            "created_at": now,
            "publish_at": publish_at,
            "idempotent_replay": False,
        }
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
    return {
        "record_id": rid,
        "library_id": library_id,
        "case_id": case_id,
        "status": status,
        "created_at": now,
        "idempotent_replay": False,
    }


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


def set_record_feedback(record_id: str, principal_id: str, vote: int) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with connect() as conn:
        _execute(
            conn,
            """
            INSERT INTO record_feedback (record_id, principal_id, vote, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (record_id, principal_id) DO UPDATE SET
              vote = excluded.vote,
              updated_at = excluded.updated_at
            """,
            (record_id, principal_id, vote, now, now),
        )


def clear_record_feedback(record_id: str, principal_id: str) -> None:
    with connect() as conn:
        _execute(
            conn,
            "DELETE FROM record_feedback WHERE record_id = ? AND principal_id = ?",
            (record_id, principal_id),
        )


def get_feedback_summaries(
    record_ids: list[str],
    *,
    principal_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    if not record_ids:
        return {}
    placeholders = ",".join("?" for _ in record_ids)
    with connect() as conn:
        rows = _fetchall(
            conn,
            f"""
            SELECT record_id,
                   SUM(CASE WHEN vote = 1 THEN 1 ELSE 0 END) AS up,
                   SUM(CASE WHEN vote = -1 THEN 1 ELSE 0 END) AS down
            FROM record_feedback
            WHERE record_id IN ({placeholders})
            GROUP BY record_id
            """,
            record_ids,
        )
        my_votes: dict[str, int] = {}
        if principal_id:
            mine = _fetchall(
                conn,
                f"""
                SELECT record_id, vote
                FROM record_feedback
                WHERE principal_id = ? AND record_id IN ({placeholders})
                """,
                [principal_id, *record_ids],
            )
            my_votes = {str(r["record_id"]): int(r["vote"]) for r in mine}

    out: dict[str, dict[str, Any]] = {}
    seen = set(record_ids)
    for row in rows:
        rid = str(row["record_id"])
        seen.discard(rid)
        out[rid] = _feedback_summary_row(int(row["up"]), int(row["down"]), my_votes.get(rid))
    for rid in seen:
        out[rid] = _feedback_summary_row(0, 0, my_votes.get(rid))
    return out


def _feedback_summary_row(up: int, down: int, my_vote: int | None) -> dict[str, Any]:
    summary: dict[str, Any] = {"up": up, "down": down}
    if my_vote is not None:
        summary["my_vote"] = "up" if my_vote == 1 else "down"
    return summary


def list_drafts(library_id: str, limit: int, offset: int, *, include_payload: bool = False) -> list[dict[str, Any]]:
    payload_col = ", payload_json" if include_payload else ""
    with connect() as conn:
        rows = _fetchall(
            conn,
            f"""
            SELECT id, library_id, case_id, status, problem, outcome, result_summary, created_at{payload_col}
            FROM records WHERE library_id = ? AND status = 'draft'
            ORDER BY created_at DESC LIMIT ? OFFSET ?
            """,
            (library_id, limit, offset),
        )
    out: list[dict[str, Any]] = []
    for row in rows:
        item = _row_dict(row)
        if include_payload and "payload_json" in item:
            payload = item.pop("payload_json")
            if isinstance(payload, str):
                item["payload"] = json.loads(payload)
            else:
                item["payload"] = payload
        out.append(item)
    return out


def set_record_status(record_id: str, status: str) -> dict[str, Any] | None:
    with connect() as conn:
        _execute(conn, "UPDATE records SET status = ? WHERE id = ?", (status, record_id))
    sync_record_search_index(record_id)
    return get_record(record_id)


def sync_record_search_index(record_id: str) -> None:
    record = get_record(record_id)
    if not record:
        return
    payload = record.get("payload") or {}
    if status := record.get("status"):
        index_record(
            record_id=record_id,
            library_id=str(record["library_id"]),
            status=str(status),
            problem=str(record["problem"]),
            outcome=str(record["outcome"]),
            result_summary=str(record["result_summary"]),
            payload=payload if isinstance(payload, dict) else {},
            created_at=str(record.get("created_at") or ""),
        )


def _delete_record_embeddings(record_id: str) -> None:
    with connect() as conn:
        if _table_exists(conn, "record_embeddings"):
            _execute(conn, "DELETE FROM record_embeddings WHERE record_id = ?", (record_id,))


def insert_record_relations(
    *,
    source_id: str,
    based_on_record_ids: list[str],
    relation_type: str | None,
) -> None:
    from datetime import datetime, timezone

    if not based_on_record_ids:
        return
    rel_type = relation_type or "derived_from"
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with connect() as conn:
        for target_id in based_on_record_ids:
            _execute(
                conn,
                """
                INSERT INTO record_relations (source_id, target_id, relation_type, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (source_id, target_id, relation_type) DO NOTHING
                """,
                (source_id, target_id, rel_type, now),
            )


def delete_record_relations_for_source(source_id: str) -> None:
    with connect() as conn:
        _execute(conn, "DELETE FROM record_relations WHERE source_id = ?", (source_id,))


def get_record_relations(
    record_ids: list[str],
    *,
    readable_library_ids: set[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if not record_ids:
        return {}
    placeholders = ",".join("?" for _ in record_ids)
    lib_filter = ""
    lib_params: list[Any] = []
    if readable_library_ids is not None:
        if not readable_library_ids:
            return {rid: [] for rid in record_ids}
        lib_placeholders = ",".join("?" for _ in readable_library_ids)
        lib_filter = f" AND r.library_id IN ({lib_placeholders})"
        lib_params = list(readable_library_ids)
    with connect() as conn:
        outgoing = _fetchall(
            conn,
            f"""
            SELECT rr.source_id, rr.target_id, rr.relation_type, rr.created_at
            FROM record_relations rr
            JOIN records r ON r.id = rr.target_id
            WHERE rr.source_id IN ({placeholders}){lib_filter}
            ORDER BY rr.created_at
            """,
            [*record_ids, *lib_params],
        )
        incoming = _fetchall(
            conn,
            f"""
            SELECT rr.source_id, rr.target_id, rr.relation_type, rr.created_at
            FROM record_relations rr
            JOIN records r ON r.id = rr.source_id
            WHERE rr.target_id IN ({placeholders}){lib_filter}
            ORDER BY rr.created_at
            """,
            [*record_ids, *lib_params],
        )
    out: dict[str, list[dict[str, Any]]] = {rid: [] for rid in record_ids}
    for row in outgoing:
        sid = str(row["source_id"])
        out.setdefault(sid, []).append(
            {"direction": "out", "peer_id": row["target_id"], "relation_type": row["relation_type"], "created_at": row["created_at"]}
        )
    for row in incoming:
        tid = str(row["target_id"])
        out.setdefault(tid, []).append(
            {"direction": "in", "peer_id": row["source_id"], "relation_type": row["relation_type"], "created_at": row["created_at"]}
        )
    return out


def get_superseded_record_ids(record_ids: list[str], library_ids: set[str]) -> set[str]:
    if not record_ids or not library_ids:
        return set()
    id_placeholders = ",".join("?" for _ in record_ids)
    lib_placeholders = ",".join("?" for _ in library_ids)
    with connect() as conn:
        rows = _fetchall(
            conn,
            f"""
            SELECT DISTINCT rr.target_id
            FROM record_relations rr
            JOIN records src ON src.id = rr.source_id
            WHERE rr.relation_type = 'supersedes'
              AND rr.target_id IN ({id_placeholders})
              AND src.status = 'active'
              AND src.library_id IN ({lib_placeholders})
            """,
            [*record_ids, *library_ids],
        )
    return {str(row["target_id"]) for row in rows}


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


def get_case(
    case_id: str,
    *,
    library_ids: set[str] | None = None,
    active_only: bool = True,
    include_payload: bool = False,
) -> dict[str, Any] | None:
    with connect() as conn:
        row = _fetchone(conn, "SELECT * FROM cases WHERE id = ?", (case_id,))
        if not row:
            return None
        case = _row_dict(row)
        if library_ids is not None and case.get("library_id") not in library_ids:
            return None
        payload_col = ", payload_json" if include_payload else ""
        status_clause = " AND status = 'active'" if active_only else ""
        recs = _fetchall(
            conn,
            f"""
            SELECT id, library_id, case_id, status, problem, outcome, result_summary, created_by, created_at{payload_col}
            FROM records
            WHERE case_id = ? AND library_id = ?{status_clause}
            ORDER BY created_at
            """,
            (case_id, case["library_id"]),
        )
        records: list[dict[str, Any]] = []
        for rec in recs:
            item = _row_dict(rec)
            if include_payload and "payload_json" in item:
                payload = item.pop("payload_json")
                if isinstance(payload, str):
                    item["payload"] = json.loads(payload)
                else:
                    item["payload"] = payload
            records.append(item)
        case["records"] = records
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


def _column_exists(conn: Any, table_name: str, column_name: str) -> bool:
    if is_postgres():
        row = _fetchone(
            conn,
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ? AND column_name = ?
            """,
            (table_name, column_name),
        )
    else:
        row = _fetchone(conn, f"SELECT 1 FROM pragma_table_info('{table_name}') WHERE name = ?", (column_name,))
    return row is not None


def get_user_principal(principal_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        if not _table_exists(conn, "principals"):
            return None
        id_col = _principal_id_column(conn)
        locked_col = ", display_name_locked" if _column_exists(conn, "principals", "display_name_locked") else ""
        row = _fetchone(
            conn,
            f"SELECT {id_col} AS principal_id, kind, display_name{locked_col}, created_at FROM principals WHERE {id_col} = ?",
            (principal_id,),
        )
    return _row_dict(row) if row else None


def set_user_display_name(principal_id: str, display_name: str) -> dict[str, Any] | None:
    with connect() as conn:
        if not _table_exists(conn, "principals"):
            return None
        id_col = _principal_id_column(conn)
        if _column_exists(conn, "principals", "display_name_locked"):
            _execute(
                conn,
                f"UPDATE principals SET display_name = ?, display_name_locked = 1 WHERE {id_col} = ?",
                (display_name, principal_id),
            )
        else:
            _execute(
                conn,
                f"UPDATE principals SET display_name = ? WHERE {id_col} = ?",
                (display_name, principal_id),
            )
    return get_user_principal(principal_id)


def set_library_name(library_id: str, name: str) -> None:
    with connect() as conn:
        _execute(conn, "UPDATE libraries SET name = ? WHERE id = ?", (name, library_id))


def upsert_user_principal(
    *,
    sso_user: str,
    display_name: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from datetime import datetime, timezone

    principal_id = f"user:{sso_user}"
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload = json.dumps(metadata or {})
    with connect() as conn:
        if not _table_exists(conn, "principals"):
            return {"principal_id": principal_id, "display_name": display_name, "sso_user": sso_user}

        id_col = _principal_id_column(conn)
        has_sso_user = _column_exists(conn, "principals", "sso_user")
        has_metadata = _column_exists(conn, "principals", "metadata_json")
        has_locked = _column_exists(conn, "principals", "display_name_locked")
        if has_locked:
            if is_postgres():
                locked_sql = (
                    "display_name = CASE WHEN principals.display_name_locked = 1 "
                    "THEN principals.display_name ELSE EXCLUDED.display_name END,"
                )
            else:
                locked_sql = (
                    "display_name = CASE WHEN display_name_locked = 1 "
                    "THEN display_name ELSE excluded.display_name END,"
                )
        else:
            locked_sql = (
                "display_name = EXCLUDED.display_name," if is_postgres() else "display_name = excluded.display_name,"
            )

        if is_postgres() and has_sso_user and has_metadata:
            _execute(
                conn,
                f"""
                INSERT INTO principals ({id_col}, kind, display_name, sso_user, created_at, metadata_json)
                VALUES (?, 'user', ?, ?, ?, ?::jsonb)
                ON CONFLICT ({id_col}) DO UPDATE SET
                    {locked_sql}
                    sso_user = EXCLUDED.sso_user,
                    metadata_json = EXCLUDED.metadata_json
                """,
                (principal_id, display_name, sso_user, now, payload),
            )
        elif has_sso_user:
            _execute(
                conn,
                f"""
                INSERT INTO principals ({id_col}, kind, display_name, sso_user, created_at)
                VALUES (?, 'user', ?, ?, ?)
                ON CONFLICT ({id_col}) DO UPDATE SET
                    {locked_sql}
                    sso_user = excluded.sso_user
                """,
                (principal_id, display_name, sso_user, now),
            )
        else:
            _execute(
                conn,
                f"""
                INSERT INTO principals ({id_col}, kind, display_name, created_at)
                VALUES (?, 'user', ?, ?)
                ON CONFLICT ({id_col}) DO UPDATE SET
                    {locked_sql.rstrip(',')}
                """,
                (principal_id, display_name, now),
            )

        row = _fetchone(
            conn,
            f"SELECT {id_col} AS principal_id, display_name FROM principals WHERE {id_col} = ?",
            (principal_id,),
        )

    effective_name = str(row["display_name"]) if row else display_name
    return {"principal_id": principal_id, "display_name": effective_name, "sso_user": sso_user}


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
            "note": (
                "Authing / OIDC 登录用户登记在 principals 表；Agent 使用 API key 不计入。"
                if __import__("app.core.config", fromlist=["settings"]).settings.authing_configured
                else "OIDC 用户与 API key 持有者登记在 principals 表；dev_auth 管理员不计入。"
            ),
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


def get_library(library_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = _fetchone(conn, "SELECT * FROM libraries WHERE id = ?", (library_id,))
    return _row_dict(row) if row else None


def _legacy_libraries_is_mirror(conn: Any) -> bool:
    """True when legacy_libraries is the old FK mirror table (library_id column), not a renamed v1 libraries table."""
    return _table_exists(conn, "legacy_libraries") and _column_exists(conn, "legacy_libraries", "library_id")


def _sync_legacy_library_if_needed(
    conn: Any,
    library_id: str,
    *,
    name: str,
    org_id: str,
    visibility: str,
) -> None:
    """Keep legacy_libraries in sync on migrated Postgres (api_key_grants FK)."""
    if not _legacy_libraries_is_mirror(conn):
        return
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    is_public = visibility == "public"
    if is_postgres():
        _execute(
            conn,
            """
            INSERT INTO legacy_libraries (library_id, organization_id, name, description, is_public, created_at)
            VALUES (?, ?, ?, '', ?, ?)
            ON CONFLICT (library_id) DO UPDATE SET
                name = EXCLUDED.name,
                organization_id = EXCLUDED.organization_id,
                is_public = EXCLUDED.is_public
            """,
            (library_id, org_id, name, is_public, now),
        )
    else:
        _execute(
            conn,
            """
            INSERT OR REPLACE INTO legacy_libraries (library_id, organization_id, name, description, is_public, created_at)
            VALUES (?, ?, ?, '', ?, ?)
            """,
            (library_id, org_id, name, is_public, now),
        )


def _format_library_row(row: dict[str, Any]) -> dict[str, Any]:
    lib_id = str(row["id"])
    kind = str(row.get("kind") or "custom")
    return {
        "library_id": lib_id,
        "name": row["name"],
        "visibility": row["visibility"],
        "kind": kind,
        "owner_principal_id": row.get("owner_principal_id"),
        "write_buffer_hours": int(row.get("write_buffer_hours") if row.get("write_buffer_hours") is not None else 24),
        "is_personal": kind == "personal",
        "is_public_default": lib_id == settings.default_library_id,
    }


def _sync_legacy_library(
    library_id: str,
    *,
    org_id: str,
    name: str,
    visibility: str,
) -> None:
    """Mirror v1 libraries into legacy_libraries when Postgres FKs still reference it."""
    if not is_postgres():
        return
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    is_public = visibility == "public"
    with connect() as conn:
        if not _legacy_libraries_is_mirror(conn):
            return
        if is_postgres():
            _execute(
                conn,
                """
                INSERT INTO legacy_libraries (library_id, organization_id, name, description, is_public, created_at)
                VALUES (?, ?, ?, '', ?, ?)
                ON CONFLICT (library_id) DO UPDATE SET
                    organization_id = EXCLUDED.organization_id,
                    name = EXCLUDED.name,
                    is_public = EXCLUDED.is_public
                """,
                (library_id, org_id, name, is_public, now),
            )
        else:
            _execute(
                conn,
                """
                INSERT OR REPLACE INTO legacy_libraries (library_id, organization_id, name, description, is_public, created_at)
                VALUES (?, ?, ?, '', ?, ?)
                """,
                (library_id, org_id, name, is_public, now),
            )


def create_library(
    library_id: str,
    *,
    name: str,
    visibility: str = "private",
    org_id: str | None = None,
    kind: str = "custom",
    owner_principal_id: str | None = None,
) -> dict[str, Any]:
    org = org_id or settings.default_org_id
    with connect() as conn:
        _execute(
            conn,
            """
            INSERT INTO libraries (
              id, org_id, name, visibility, kind, owner_principal_id,
              deletion_protection, retention_days
            )
            VALUES (?, ?, ?, ?, ?, ?, 0, 30)
            """,
            (library_id, org, name, visibility, kind, owner_principal_id),
        )
    _sync_legacy_library(library_id, org_id=org, name=name, visibility=visibility)
    lib = get_library(library_id)
    assert lib is not None
    return lib


def ensure_library(
    library_id: str,
    *,
    name: str,
    visibility: str = "private",
    org_id: str | None = None,
    kind: str = "custom",
    owner_principal_id: str | None = None,
) -> dict[str, Any]:
    """Create or update library metadata (idempotent bootstrap helper)."""
    existing = get_library(library_id)
    if existing is None:
        return create_library(
            library_id,
            name=name,
            visibility=visibility,
            org_id=org_id,
            kind=kind,
            owner_principal_id=owner_principal_id,
        )
    org = org_id or existing.get("org_id") or settings.default_org_id
    with connect() as conn:
        _execute(
            conn,
            """
            UPDATE libraries
            SET org_id = ?, name = ?, visibility = ?, kind = ?, owner_principal_id = ?
            WHERE id = ?
            """,
            (org, name, visibility, kind, owner_principal_id, library_id),
        )
    _sync_legacy_library(library_id, org_id=org, name=name, visibility=visibility)
    lib = get_library(library_id)
    assert lib is not None
    return lib


def set_deletion_protection(library_id: str, *, enabled: bool, retention_days: int = 30) -> None:
    with connect() as conn:
        _execute(
            conn,
            "UPDATE libraries SET deletion_protection = ?, retention_days = ? WHERE id = ?",
            (1 if enabled else 0, retention_days, library_id),
        )


def list_libraries(library_ids: set[str] | None = None) -> list[dict[str, Any]]:
    cols = "id, name, visibility, kind, owner_principal_id"
    with connect() as conn:
        if library_ids is None:
            rows = _fetchall(conn, f"SELECT {cols} FROM libraries ORDER BY id")
        elif not library_ids:
            return []
        else:
            placeholders = ",".join("?" for _ in library_ids)
            rows = _fetchall(
                conn,
                f"SELECT {cols} FROM libraries WHERE id IN ({placeholders}) ORDER BY id",
                list(library_ids),
            )
    return [_format_library_row(_row_dict(r)) for r in rows]


def get_api_key_by_id(key_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        if not _table_exists(conn, "api_keys"):
            return None
        row = _fetchone(
            conn,
            """
            SELECT key_id, principal_id, label, created_at, revoked_at, expires_at
            FROM api_keys WHERE key_id = ?
            """,
            (key_id,),
        )
    return _row_dict(row) if row else None


def upsert_api_key_grant(key_id: str, library_id: str, role: str) -> None:
    with connect() as conn:
        if not _table_exists(conn, "api_key_grants"):
            return
        existing = _fetchone(
            conn,
            "SELECT 1 FROM api_key_grants WHERE key_id = ? AND library_id = ?",
            (key_id, library_id),
        )
        if existing:
            _execute(
                conn,
                "UPDATE api_key_grants SET role = ? WHERE key_id = ? AND library_id = ?",
                (role, key_id, library_id),
            )
        else:
            _execute(
                conn,
                "INSERT INTO api_key_grants (key_id, library_id, role) VALUES (?, ?, ?)",
                (key_id, library_id, role),
            )


def get_api_key_by_hash(key_hash: str) -> dict[str, Any] | None:
    with connect() as conn:
        if not _table_exists(conn, "api_keys"):
            return None
        row = _fetchone(
            conn,
            """
            SELECT key_id, principal_id, label, created_at, revoked_at, expires_at
            FROM api_keys WHERE key_hash = ?
            """,
            (key_hash,),
        )
    return _row_dict(row) if row else None


def get_api_key_grants(key_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        if not _table_exists(conn, "api_key_grants"):
            return []
        rows = _fetchall(
            conn,
            "SELECT library_id, role FROM api_key_grants WHERE key_id = ?",
            (key_id,),
        )
    return [{"library_id": r["library_id"], "role": r["role"]} for r in rows]


def touch_api_key_last_used(key_id: str, when: str | None = None) -> None:
    from datetime import datetime, timezone

    ts = when or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        with connect() as conn:
            if not _table_exists(conn, "api_keys"):
                return
            _execute(conn, "UPDATE api_keys SET last_used_at = ? WHERE key_id = ?", (ts, key_id))
    except Exception:
        # last_used_at is best-effort telemetry; never fail a request over it.
        pass


def find_personal_library(owner_principal_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = _fetchone(
            conn,
            """
            SELECT id, name, visibility, kind, owner_principal_id
            FROM libraries
            WHERE kind = 'personal' AND owner_principal_id = ?
            ORDER BY id
            LIMIT 1
            """,
            (owner_principal_id,),
        )
    return _format_library_row(_row_dict(row)) if row else None


def count_active_api_keys(principal_id: str) -> int:
    with connect() as conn:
        if not _table_exists(conn, "api_keys"):
            return 0
        row = _fetchone(
            conn,
            "SELECT COUNT(*) AS c FROM api_keys WHERE principal_id = ? AND revoked_at IS NULL",
            (principal_id,),
        )
    return int(row["c"]) if row else 0


def list_api_keys_for_principal(principal_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        if not _table_exists(conn, "api_keys"):
            return []
        rows = _fetchall(
            conn,
            """
            SELECT key_id, key_prefix, principal_id, label, created_at, created_by, last_used_at, expires_at, revoked_at, key_ciphertext
            FROM api_keys
            WHERE principal_id = ? AND revoked_at IS NULL
            ORDER BY created_at DESC
            """,
            (principal_id,),
        )
    out: list[dict[str, Any]] = []
    lib_names = {lib["library_id"]: lib["name"] for lib in list_libraries()}
    for row in rows:
        item = _row_dict(row)
        grants = get_api_key_grants(str(item["key_id"]))
        item["grants"] = [
            {
                "library_id": g["library_id"],
                "library_name": lib_names.get(g["library_id"], g["library_id"]),
                "role": g["role"],
            }
            for g in grants
        ]
        out.append(item)
    return out


def revoke_api_key(key_id: str, *, principal_id: str) -> bool:
    """Soft-revoke legacy/admin keys. Self-service UI uses delete_api_key instead."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with connect() as conn:
        if not _table_exists(conn, "api_keys"):
            return False
        cur = _execute(
            conn,
            """
            UPDATE api_keys
            SET revoked_at = ?
            WHERE key_id = ? AND principal_id = ? AND revoked_at IS NULL
            """,
            (now, key_id, principal_id),
        )
    return bool(getattr(cur, "rowcount", 0))


def get_api_key_for_principal(key_id: str, *, principal_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        if not _table_exists(conn, "api_keys"):
            return None
        row = _fetchone(
            conn,
            """
            SELECT key_id, key_prefix, principal_id, label, created_at, created_by, last_used_at, expires_at, revoked_at, key_ciphertext
            FROM api_keys
            WHERE key_id = ? AND principal_id = ? AND revoked_at IS NULL
            """,
            (key_id, principal_id),
        )
    if not row:
        return None
    item = _row_dict(row)
    grants = get_api_key_grants(str(item["key_id"]))
    lib_names = {lib["library_id"]: lib["name"] for lib in list_libraries()}
    item["grants"] = [
        {
            "library_id": g["library_id"],
            "library_name": lib_names.get(g["library_id"], g["library_id"]),
            "role": g["role"],
        }
        for g in grants
    ]
    return item


def update_api_key_label(key_id: str, *, principal_id: str, label: str) -> dict[str, Any] | None:
    with connect() as conn:
        if not _table_exists(conn, "api_keys"):
            return None
        existing = _fetchone(
            conn,
            "SELECT key_id FROM api_keys WHERE key_id = ? AND principal_id = ? AND revoked_at IS NULL",
            (key_id, principal_id),
        )
        if not existing:
            return None
        _execute(
            conn,
            "UPDATE api_keys SET label = ? WHERE key_id = ? AND principal_id = ?",
            (label, key_id, principal_id),
        )
    return get_api_key_for_principal(key_id, principal_id=principal_id)


def replace_api_key_grants(
    key_id: str,
    *,
    principal_id: str,
    grants: list[dict[str, str]],
) -> dict[str, Any] | None:
    if get_api_key_for_principal(key_id, principal_id=principal_id) is None:
        return None
    with connect() as conn:
        if not _table_exists(conn, "api_key_grants"):
            return None
        _execute(conn, "DELETE FROM api_key_grants WHERE key_id = ?", (key_id,))
        for grant in grants:
            _execute(
                conn,
                "INSERT INTO api_key_grants (key_id, library_id, role) VALUES (?, ?, ?)",
                (key_id, grant["library_id"], grant["role"]),
            )
    return get_api_key_for_principal(key_id, principal_id=principal_id)


def delete_api_key(key_id: str, *, principal_id: str) -> bool:
    with connect() as conn:
        if not _table_exists(conn, "api_keys"):
            return False
        row = _fetchone(
            conn,
            "SELECT key_id FROM api_keys WHERE key_id = ? AND principal_id = ? AND revoked_at IS NULL",
            (key_id, principal_id),
        )
        if not row:
            return False
        _execute(conn, "DELETE FROM api_key_grants WHERE key_id = ?", (key_id,))
        cur = _execute(
            conn,
            "DELETE FROM api_keys WHERE key_id = ? AND principal_id = ?",
            (key_id, principal_id),
        )
    return bool(getattr(cur, "rowcount", 0))


def insert_api_key(
    *,
    key_id: str,
    key_hash: str,
    principal_id: str,
    label: str = "",
    created_by: str | None = None,
    created_at: str | None = None,
    expires_at: str | None = None,
    key_prefix: str | None = None,
    key_ciphertext: str | None = None,
    grants: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Create an API key with grants. Primarily used by tests and key issuance."""
    from datetime import datetime, timezone

    now = created_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with connect() as conn:
        _execute(
            conn,
            """
            INSERT INTO api_keys (key_id, key_hash, principal_id, label, created_at, created_by, expires_at, key_prefix, key_ciphertext)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (key_id, key_hash, principal_id, label, now, created_by or principal_id, expires_at, key_prefix, key_ciphertext),
        )
        for grant in grants or []:
            _execute(
                conn,
                "INSERT INTO api_key_grants (key_id, library_id, role) VALUES (?, ?, ?)",
                (key_id, grant["library_id"], grant["role"]),
            )
    return {"key_id": key_id, "principal_id": principal_id, "grants": grants or []}


def append_write_audit_log(
    *,
    record_id: str,
    library_id: str,
    principal_id: str,
    api_key_id: str,
    report_kind: str,
    confirmation: str,
) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with connect() as conn:
        _execute(
            conn,
            """
            INSERT INTO write_audit_log (
              id, record_id, library_id, principal_id, api_key_id, report_kind, confirmation, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (new_id("wa"), record_id, library_id, principal_id, api_key_id, report_kind, confirmation, now),
        )


def backfill_write_audit_log() -> int:
    """Create write_audit_log rows for pre-existing records that lack one.

    Records written before the audit log existed are attributed to their
    ``created_by`` principal so ``ma3_list_my_writes`` can enumerate historical
    uploads. Records with no known author (``created_by`` NULL — e.g. legacy
    migrated rows) cannot be attributed and are skipped. Idempotent: only rows
    missing an audit entry are inserted, and the audit ``created_at`` mirrors the
    record so chronological ordering stays correct. Historical entries are marked
    ``confirmation='backfilled'`` / ``api_key_id='backfill'`` to distinguish them
    from writes captured live.
    """
    inserted = 0
    with connect() as conn:
        rows = _fetchall(
            conn,
            """
            SELECT r.id, r.library_id, r.created_by, r.payload_json, r.created_at
            FROM records r
            LEFT JOIN write_audit_log w ON w.record_id = r.id
            WHERE w.record_id IS NULL AND r.created_by IS NOT NULL
            """,
        )
        for row in rows:
            payload = row["payload_json"]
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except (TypeError, ValueError):
                    payload = {}
            if not isinstance(payload, dict):
                payload = {}
            report_kind = payload.get("report_kind") or "new"
            confirmation = payload.get("confirmation") or "backfilled"
            _execute(
                conn,
                """
                INSERT INTO write_audit_log (
                  id, record_id, library_id, principal_id, api_key_id, report_kind, confirmation, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("wa"),
                    row["id"],
                    row["library_id"],
                    row["created_by"],
                    "backfill",
                    report_kind,
                    confirmation,
                    row["created_at"],
                ),
            )
            inserted += 1
    return inserted


def get_write_audit_for_record(record_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = _fetchone(
            conn,
            """
            SELECT id, record_id, library_id, principal_id, api_key_id, report_kind, confirmation, created_at
            FROM write_audit_log
            WHERE record_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (record_id,),
        )
    return _row_dict(row) if row else None


def list_write_audit_for_principal(
    principal_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = _fetchall(
            conn,
            """
            SELECT w.id, w.record_id, w.library_id, w.principal_id, w.api_key_id,
                   w.report_kind, w.confirmation, w.created_at, l.name AS library_name,
                   k.key_prefix, r.problem, r.status AS record_status, r.publish_at
            FROM write_audit_log w
            LEFT JOIN libraries l ON l.id = w.library_id
            LEFT JOIN api_keys k ON k.key_id = w.api_key_id
            LEFT JOIN records r ON r.id = w.record_id
            WHERE w.principal_id = ?
            ORDER BY w.created_at DESC
            LIMIT ? OFFSET ?
            """,
            (principal_id, limit, offset),
        )
    return [_row_dict(r) for r in rows]


def count_write_audit_for_principal(principal_id: str) -> int:
    with connect() as conn:
        row = _fetchone(
            conn,
            "SELECT COUNT(*) AS c FROM write_audit_log WHERE principal_id = ?",
            (principal_id,),
        )
    return int(row["c"]) if row else 0


def count_buffered_for_principal(principal_id: str) -> int:
    with connect() as conn:
        row = _fetchone(
            conn,
            """
            SELECT COUNT(*) AS c FROM records
            WHERE status = 'buffered' AND created_by = ?
            """,
            (principal_id,),
        )
    return int(row["c"]) if row else 0


def get_library_write_buffer_hours(library_id: str) -> int:
    lib = get_library(library_id)
    if not lib:
        return 24
    try:
        return max(0, int(lib.get("write_buffer_hours") if lib.get("write_buffer_hours") is not None else 24))
    except (TypeError, ValueError):
        return 24


def set_library_write_buffer_hours(library_id: str, hours: int) -> None:
    hours = max(0, min(hours, 168))
    with connect() as conn:
        _execute(conn, "UPDATE libraries SET write_buffer_hours = ? WHERE id = ?", (hours, library_id))


def publish_buffered_record(record_id: str) -> dict[str, Any] | None:
    record = get_record(record_id)
    if not record or record.get("status") != "buffered":
        return None
    with connect() as conn:
        _execute(
            conn,
            "UPDATE records SET status = ?, publish_at = NULL WHERE id = ? AND status = 'buffered'",
            ("active", record_id),
        )
    sync_record_search_index(record_id)
    return get_record(record_id)


def update_buffered_record(
    record_id: str,
    *,
    problem: str,
    outcome: str,
    result_summary: str,
    payload: dict[str, Any],
    publish_at: str | None,
) -> dict[str, Any] | None:
    record = get_record(record_id)
    if not record or record.get("status") != "buffered":
        return None
    raw = json.dumps(payload)
    with connect() as conn:
        if is_postgres():
            _execute(
                conn,
                """
                UPDATE records
                SET problem = ?, outcome = ?, result_summary = ?, payload_json = ?::jsonb, publish_at = ?
                WHERE id = ? AND status = 'buffered'
                """,
                (problem, outcome, result_summary, raw, publish_at, record_id),
            )
        else:
            _execute(
                conn,
                """
                UPDATE records
                SET problem = ?, outcome = ?, result_summary = ?, payload_json = ?, publish_at = ?
                WHERE id = ? AND status = 'buffered'
                """,
                (problem, outcome, result_summary, raw, publish_at, record_id),
            )
    return get_record(record_id)


def publish_due_buffered_records(*, limit: int = 500) -> int:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with connect() as conn:
        rows = _fetchall(
            conn,
            """
            SELECT id FROM records
            WHERE status = 'buffered' AND publish_at IS NOT NULL AND publish_at <= ?
            ORDER BY publish_at ASC
            LIMIT ?
            """,
            (now, limit),
        )
    count = 0
    for row in rows:
        rid = str(row["id"])
        if publish_buffered_record(rid):
            record = get_record(rid)
            payload = (record or {}).get("payload") or {}
            based_on = payload.get("based_on_record_ids") if isinstance(payload, dict) else []
            if isinstance(based_on, list) and based_on:
                insert_record_relations(
                    source_id=rid,
                    based_on_record_ids=[str(x) for x in based_on],
                    relation_type=payload.get("relation_type") if isinstance(payload, dict) else None,
                )
            count += 1
    return count


def search_author_buffered_records(
    library_ids: set[str],
    principal_id: str,
    problem: str,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    if not library_ids or not problem.strip():
        return []
    placeholders = ",".join("?" for _ in library_ids)
    op = "ILIKE" if is_postgres() else "LIKE"
    pattern = f"%{problem.strip()[:200]}%"
    with connect() as conn:
        rows = _fetchall(
            conn,
            f"""
            SELECT * FROM records
            WHERE library_id IN ({placeholders})
              AND status = 'buffered'
              AND created_by = ?
              AND (problem {op} ? OR result_summary {op} ?)
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [*library_ids, principal_id, pattern, pattern, limit],
        )
    out: list[dict[str, Any]] = []
    for row in rows:
        item = _row_dict(row)
        payload = item.pop("payload_json", None)
        if isinstance(payload, str):
            item["payload"] = json.loads(payload)
        else:
            item["payload"] = payload
        out.append(item)
    return out


def list_feedback_for_principal(
    principal_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = _fetchall(
            conn,
            """
            SELECT f.record_id, f.vote, f.updated_at,
                   r.problem, r.library_id, r.status,
                   l.name AS library_name
            FROM record_feedback f
            LEFT JOIN records r ON r.id = f.record_id
            LEFT JOIN libraries l ON l.id = r.library_id
            WHERE f.principal_id = ?
            ORDER BY f.updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (principal_id, limit, offset),
        )
    return [_row_dict(r) for r in rows]


def count_feedback_for_principal(principal_id: str) -> int:
    with connect() as conn:
        row = _fetchone(
            conn,
            "SELECT COUNT(*) AS c FROM record_feedback WHERE principal_id = ?",
            (principal_id,),
        )
    return int(row["c"]) if row else 0


def get_library_stats(library_id: str) -> dict[str, Any] | None:
    lib = get_library(library_id)
    if not lib:
        return None
    with connect() as conn:
        case_row = _fetchone(conn, "SELECT COUNT(*) AS c FROM cases WHERE library_id = ?", (library_id,))
        status_rows = _fetchall(
            conn,
            "SELECT status, COUNT(*) AS c FROM records WHERE library_id = ? GROUP BY status",
            (library_id,),
        )
        if is_postgres():
            outcome_rows = _fetchall(
                conn,
                """
                SELECT outcome, COUNT(*) AS c FROM records
                WHERE library_id = ? AND status = 'active'
                GROUP BY outcome ORDER BY c DESC, outcome
                """,
                (library_id,),
            )
            task_rows = _fetchall(
                conn,
                """
                SELECT COALESCE(payload_json->>'task_type', 'unknown') AS task_type, COUNT(*) AS c
                FROM records WHERE library_id = ? AND status = 'active'
                GROUP BY 1 ORDER BY c DESC, task_type
                """,
                (library_id,),
            )
        else:
            outcome_rows = _fetchall(
                conn,
                """
                SELECT outcome, COUNT(*) AS c FROM records
                WHERE library_id = ? AND status = 'active'
                GROUP BY outcome ORDER BY c DESC, outcome
                """,
                (library_id,),
            )
            task_rows = _fetchall(
                conn,
                """
                SELECT COALESCE(json_extract(payload_json, '$.task_type'), 'unknown') AS task_type,
                       COUNT(*) AS c
                FROM records WHERE library_id = ? AND status = 'active'
                GROUP BY 1 ORDER BY c DESC, task_type
                """,
                (library_id,),
            )
        org_row = _fetchone(conn, "SELECT name FROM organizations WHERE id = ?", (lib.get("org_id"),))
    by_status = {str(r["status"]): int(r["c"]) for r in status_rows}
    return {
        **lib,
        "org_name": org_row["name"] if org_row else str(lib.get("org_id") or ""),
        "cases": int(case_row["c"]) if case_row else 0,
        "records": {
            "total": sum(by_status.values()),
            "by_status": by_status,
        },
        "by_outcome": [{"outcome": str(r["outcome"]), "count": int(r["c"])} for r in outcome_rows],
        "by_task_type": [{"task_type": str(r["task_type"]), "count": int(r["c"])} for r in task_rows],
    }


def get_record_deletion(record_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = _fetchone(conn, "SELECT * FROM record_deletions WHERE record_id = ?", (record_id,))
    return _row_dict(row) if row else None


def insert_record_deletion(*, record_id: str, library_id: str, deleted_by: str) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with connect() as conn:
        _execute(
            conn,
            """
            INSERT INTO record_deletions (record_id, library_id, deleted_by, deleted_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (record_id) DO NOTHING
            """,
            (record_id, library_id, deleted_by, now),
        )


def delete_record_search_index(record_id: str) -> None:
    with connect() as conn:
        if _table_exists(conn, "record_search_index"):
            _execute(conn, "DELETE FROM record_search_index WHERE record_id = ?", (record_id,))


def mark_relations_source_deleted(record_id: str) -> None:
    with connect() as conn:
        _execute(
            conn,
            """
            UPDATE record_relations
            SET source_deleted = 1
            WHERE target_id = ? OR source_id = ?
            """,
            (record_id, record_id),
        )


def relation_source_deleted(*, source_id: str, target_id: str) -> bool:
    with connect() as conn:
        row = _fetchone(
            conn,
            """
            SELECT source_deleted FROM record_relations
            WHERE source_id = ? AND target_id = ?
            LIMIT 1
            """,
            (source_id, target_id),
        )
    parsed = _row_dict(row)
    return bool(parsed and parsed.get("source_deleted"))


def set_trashed_at(record_id: str, trashed_at: str) -> None:
    with connect() as conn:
        _execute(conn, "UPDATE records SET trashed_at = ? WHERE id = ?", (trashed_at, record_id))


def is_record_owner(record_id: str, principal_id: str) -> bool:
    record = get_record(record_id)
    if not record:
        return False
    if record.get("created_by") == principal_id:
        return True
    audit = get_write_audit_for_record(record_id)
    return audit is not None and audit.get("principal_id") == principal_id


def hard_delete_record(record_id: str, *, deleted_by: str) -> None:
    record = get_record(record_id)
    if not record:
        return
    library_id = str(record["library_id"])
    insert_record_deletion(record_id=record_id, library_id=library_id, deleted_by=deleted_by)
    mark_relations_source_deleted(record_id)
    with connect() as conn:
        _execute(conn, "DELETE FROM records WHERE id = ?", (record_id,))
    _delete_record_embeddings(record_id)
    delete_record_search_index(record_id)


def soft_delete_record(record_id: str) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with connect() as conn:
        _execute(
            conn,
            "UPDATE records SET status = ?, trashed_at = ? WHERE id = ?",
            ("trashed", now, record_id),
        )
    sync_record_search_index(record_id)


def restore_trashed_record(record_id: str) -> None:
    with connect() as conn:
        _execute(
            conn,
            "UPDATE records SET status = ?, trashed_at = NULL WHERE id = ?",
            ("active", record_id),
        )
    sync_record_search_index(record_id)


def purge_expired_trashed_record(record_id: str, *, deleted_by: str) -> None:
    hard_delete_record(record_id, deleted_by=deleted_by)


def library_deletion_protection(library_id: str) -> tuple[bool, int]:
    lib = get_library(library_id)
    if not lib:
        return False, 30
    return bool(lib.get("deletion_protection")), int(lib.get("retention_days") or 30)


def is_trash_restore_expired(record_id: str) -> bool:
    record = get_record(record_id)
    if not record or record.get("status") != "trashed":
        return False
    trashed_at = record.get("trashed_at")
    if not trashed_at:
        return False
    protected, retention_days = library_deletion_protection(str(record["library_id"]))
    if not protected:
        return False
    from datetime import datetime, timedelta, timezone

    try:
        ts = datetime.fromisoformat(str(trashed_at))
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    expiry = ts + timedelta(days=retention_days)
    return datetime.now(timezone.utc) >= expiry


from app.storage.search import search_records  # noqa: E402
