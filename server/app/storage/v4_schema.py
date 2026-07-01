"""v4 database schema (greenfield). No tokens, invite_codes, library_acl, or RBAC tables."""

from __future__ import annotations

import sqlite3

from app.storage.db import DatabaseConnection


def initialize_v4_schema(conn: DatabaseConnection) -> None:
    if conn.backend == "postgresql":
        _v4_postgres(conn)
    else:
        _v4_sqlite(conn)
    _v4_content(conn)


def _v4_content(conn: DatabaseConnection) -> None:
    if conn.backend == "postgresql":
        _v4_content_postgres(conn)
    else:
        _v4_content_sqlite(conn)


def _v4_content_sqlite(conn: DatabaseConnection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            record_id TEXT PRIMARY KEY,
            library_id TEXT,
            payload_json TEXT NOT NULL
        )
        """
    )
    for col_sql in ("ALTER TABLE records ADD COLUMN library_id TEXT", "ALTER TABLE records ADD COLUMN status TEXT"):
        try:
            conn.execute(col_sql)
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


def _v4_content_postgres(conn: DatabaseConnection) -> None:
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
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_record_search_index_search_tsv "
        "ON record_search_index USING GIN(search_tsv)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_record_search_index_tags_tsv "
        "ON record_search_index USING GIN(tags_tsv)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_record_search_index_library_status "
        "ON record_search_index(library_id, status)"
    )


def _v4_libraries_sqlite(conn: DatabaseConnection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS libraries (
            library_id TEXT PRIMARY KEY,
            organization_id TEXT,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            is_public INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
    try:
        conn.execute("ALTER TABLE libraries ADD COLUMN organization_id TEXT")
    except Exception:
        pass


def _v4_libraries_postgres(conn: DatabaseConnection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS libraries (
            library_id TEXT PRIMARY KEY,
            organization_id TEXT,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            is_public BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "ALTER TABLE libraries ADD COLUMN IF NOT EXISTS organization_id TEXT"
    )


def _v4_auth_sqlite(conn: DatabaseConnection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS principals (
            principal_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL CHECK (kind IN ('user','service')),
            display_name TEXT NOT NULL,
            sso_user TEXT,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_principals_sso_user ON principals(sso_user) WHERE sso_user IS NOT NULL"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS organizations (
            org_id TEXT PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            plan_tier TEXT NOT NULL DEFAULT 'free',
            member_seat_limit INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL REFERENCES principals(principal_id),
            deleted_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS organization_members (
            org_id TEXT NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            principal_id TEXT NOT NULL REFERENCES principals(principal_id) ON DELETE CASCADE,
            org_role TEXT NOT NULL CHECK (org_role IN ('owner','admin','member')),
            joined_at TEXT NOT NULL,
            invited_by TEXT NOT NULL REFERENCES principals(principal_id),
            PRIMARY KEY (org_id, principal_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_org_members_principal ON organization_members(principal_id)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS library_access (
            library_id TEXT NOT NULL REFERENCES libraries(library_id) ON DELETE CASCADE,
            principal_id TEXT NOT NULL REFERENCES principals(principal_id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('reader','writer','admin')),
            granted_at TEXT NOT NULL,
            granted_by TEXT NOT NULL REFERENCES principals(principal_id),
            PRIMARY KEY (library_id, principal_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_library_access_principal ON library_access(principal_id)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            key_id TEXT PRIMARY KEY,
            key_hash TEXT NOT NULL UNIQUE,
            principal_id TEXT NOT NULL REFERENCES principals(principal_id),
            label TEXT NOT NULL,
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
        """
        CREATE TABLE IF NOT EXISTS api_key_grants (
            key_id TEXT NOT NULL REFERENCES api_keys(key_id) ON DELETE CASCADE,
            library_id TEXT NOT NULL REFERENCES libraries(library_id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('reader','writer','admin')),
            PRIMARY KEY (key_id, library_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            principal_id TEXT NOT NULL REFERENCES principals(principal_id) ON DELETE CASCADE,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            idp_region TEXT NOT NULL DEFAULT 'dev'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_audit_log (
            audit_id TEXT PRIMARY KEY,
            actor_principal_id TEXT NOT NULL,
            action TEXT NOT NULL,
            target_principal_id TEXT,
            organization_id TEXT,
            library_id TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_created_at ON auth_audit_log(created_at)")


def _v4_auth_postgres(conn: DatabaseConnection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS principals (
            principal_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL CHECK (kind IN ('user','service')),
            display_name TEXT NOT NULL,
            sso_user TEXT,
            created_at TEXT NOT NULL,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_principals_sso_user ON principals(sso_user) WHERE sso_user IS NOT NULL"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS organizations (
            org_id TEXT PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            plan_tier TEXT NOT NULL DEFAULT 'free',
            member_seat_limit INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL REFERENCES principals(principal_id),
            deleted_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS organization_members (
            org_id TEXT NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            principal_id TEXT NOT NULL REFERENCES principals(principal_id) ON DELETE CASCADE,
            org_role TEXT NOT NULL CHECK (org_role IN ('owner','admin','member')),
            joined_at TEXT NOT NULL,
            invited_by TEXT NOT NULL REFERENCES principals(principal_id),
            PRIMARY KEY (org_id, principal_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_org_members_principal ON organization_members(principal_id)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS library_access (
            library_id TEXT NOT NULL REFERENCES libraries(library_id) ON DELETE CASCADE,
            principal_id TEXT NOT NULL REFERENCES principals(principal_id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('reader','writer','admin')),
            granted_at TEXT NOT NULL,
            granted_by TEXT NOT NULL REFERENCES principals(principal_id),
            PRIMARY KEY (library_id, principal_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_library_access_principal ON library_access(principal_id)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            key_id TEXT PRIMARY KEY,
            key_hash TEXT NOT NULL UNIQUE,
            principal_id TEXT NOT NULL REFERENCES principals(principal_id),
            label TEXT NOT NULL,
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
        """
        CREATE TABLE IF NOT EXISTS api_key_grants (
            key_id TEXT NOT NULL REFERENCES api_keys(key_id) ON DELETE CASCADE,
            library_id TEXT NOT NULL REFERENCES libraries(library_id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('reader','writer','admin')),
            PRIMARY KEY (key_id, library_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            principal_id TEXT NOT NULL REFERENCES principals(principal_id) ON DELETE CASCADE,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            idp_region TEXT NOT NULL DEFAULT 'dev'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_audit_log (
            audit_id TEXT PRIMARY KEY,
            actor_principal_id TEXT NOT NULL,
            action TEXT NOT NULL,
            target_principal_id TEXT,
            organization_id TEXT,
            library_id TEXT,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_created_at ON auth_audit_log(created_at)")


def _v4_sqlite(conn: DatabaseConnection) -> None:
    _v4_libraries_sqlite(conn)
    _v4_auth_sqlite(conn)


def _v4_postgres(conn: DatabaseConnection) -> None:
    _v4_libraries_postgres(conn)
    _v4_auth_postgres(conn)
