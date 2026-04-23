import json

from app.models.library import InviteCode, Library, TokenInfo
from app.models.relation import RecordRelation
from app.models.feedback import Feedback
from app.models.record import Record
from app.storage.db import _json_param, _upsert, get_connection, is_postgres
from app.storage.fts import fts_delete, fts_upsert
from app.services.embedding_service import (
    embed_record,
    serialize_embedding,
    deserialize_embedding,
)
from app.core.time import utc_now_iso


def is_ancestor_or_self(candidate_lib_id: str, target_lib_id: str) -> bool:
    """Return True if candidate_lib_id equals target_lib_id or is an ancestor of it.

    Uses a recursive CTE to walk the parent chain from target upward.
    """
    with get_connection() as conn:
        row = conn.execute(
            """
            WITH RECURSIVE chain(lib_id) AS (
                SELECT ?
                UNION ALL
                SELECT l.parent_library_id
                FROM libraries l
                JOIN chain c ON l.library_id = c.lib_id
                WHERE l.parent_library_id IS NOT NULL
            )
            SELECT COUNT(*) AS cnt FROM chain WHERE lib_id = ?
            """,
            (target_lib_id, candidate_lib_id),
        ).fetchone()
    return bool(row and row["cnt"] > 0)


def _row_to_library(row) -> Library:
    return Library(
        library_id=row["library_id"],
        name=row["name"],
        description=row["description"],
        is_public=bool(row["is_public"]),
        parent_library_id=row["parent_library_id"],
        is_personal=bool(row["is_personal"]),
        created_at=row["created_at"],
    )


_LIB_COLS = "library_id, name, description, is_public, parent_library_id, is_personal, created_at"


def _load_json_payload(raw):
    return raw if isinstance(raw, dict) else json.loads(raw)


class RecordRepository:
    def insert(self, record: Record) -> None:
        with get_connection() as conn:
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

        # Generate and store embedding (outside the main transaction so a slow
        # model load does not block the write connection)
        embedding = embed_record(record)
        if embedding is not None:
            with get_connection() as conn:
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
                        utc_now_iso(),
                    ),
                )

    def get(self, record_id: str) -> Record | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT payload_json FROM records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
        if row is None:
            return None
        return Record.model_validate(_load_json_payload(row["payload_json"]))

    def list_all(self) -> list[Record]:
        with get_connection() as conn:
            rows = conn.execute("SELECT payload_json FROM records").fetchall()
        return [Record.model_validate(_load_json_payload(row["payload_json"])) for row in rows]

    def list_accessible(self, library_ids: set[str]) -> list[Record]:
        """Return records in accessible libraries plus legacy records (library_id IS NULL)."""
        if not library_ids:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT payload_json FROM records WHERE library_id IS NULL"
                ).fetchall()
        else:
            placeholders = ",".join("?" * len(library_ids))
            query = (
                f"SELECT payload_json FROM records "
                f"WHERE library_id IS NULL OR library_id IN ({placeholders})"
            )
            with get_connection() as conn:
                rows = conn.execute(query, list(library_ids)).fetchall()
        return [Record.model_validate(_load_json_payload(row["payload_json"])) for row in rows]

    def list_by_library(self, library_id: str) -> list[Record]:
        """Return all records belonging to a specific library (for admin/review use)."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM records WHERE library_id = ?",
                (library_id,),
            ).fetchall()
        return [Record.model_validate(_load_json_payload(row["payload_json"])) for row in rows]

    def list_page(
        self,
        library_ids: set[str],
        status: str | None,
        offset: int,
        limit: int,
        is_admin: bool = False,
        own_library_id: str | None = None,
    ) -> tuple[list[Record], int]:
        """Return a page of accessible records plus total count matching the same filter.

        Draft records with ``library_id IS NULL`` (legacy/unowned) are only shown to admin.

        When ``own_library_id`` is supplied and ``status == "active"``, the query
        uses a compound predicate so that the caller's own library's drafts are
        always included alongside the normally filtered rows — no separate
        ``status=all`` call is required for a library admin to see their queue.
        """
        # Build WHERE clause
        conditions: list[str] = []
        params: list = []

        # --- library visibility filter ---
        if is_admin:
            pass  # No library filter — admin sees all records
        elif library_ids:
            placeholders = ",".join("?" * len(library_ids))
            if status == "draft":
                # Drafts: only records explicitly owned by an accessible library
                conditions.append(f"library_id IN ({placeholders})")
            else:
                # Active/invalid/all: include legacy NULL-library records too
                conditions.append(f"(library_id IS NULL OR library_id IN ({placeholders}))")
            params.extend(library_ids)
        else:
            conditions.append("library_id IS NULL")

        # --- status filter ---
        if status and own_library_id:
            # Compound: (normal status filter) OR (own-library drafts)
            # Ensures library admins always see their pending queue without status=all.
            normal_cond = f"status = ?"
            own_draft_cond = f"(library_id = ? AND status = 'draft')"
            conditions.append(f"({normal_cond} OR {own_draft_cond})")
            params.extend([status, own_library_id])
        elif status:
            # Plain status filter
            conditions.append("status = ?")
            params.append(status)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        with get_connection() as conn:
            total = int(
                conn.execute(
                    f"SELECT COUNT(*) AS count FROM records {where}", params
                ).fetchone()["count"]
            )
            order_by = (
                "rowid ASC"
                if not is_postgres()
                else "COALESCE(payload_json->>'created_at', '') ASC, record_id ASC"
            )
            rows = conn.execute(
                f"SELECT payload_json FROM records {where} "
                f"ORDER BY {order_by} LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
        records = [Record.model_validate(_load_json_payload(r["payload_json"])) for r in rows]
        return records, total

    def count(self) -> int:
        with get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM records").fetchone()
        return int(row["count"])

    def delete(self, record_id: str) -> bool:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            if row is None:
                return False
            fts_delete(conn, record_id)
            conn.execute(
                "DELETE FROM record_embeddings WHERE record_id = ?",
                (record_id,),
            )
            conn.execute(
                "DELETE FROM feedback WHERE record_id = ?",
                (record_id,),
            )
            conn.execute(
                "DELETE FROM relations WHERE from_record_id = ? OR to_record_id = ?",
                (record_id, record_id),
            )
            conn.execute(
                "DELETE FROM records WHERE record_id = ?",
                (record_id,),
            )
        return True

    def delete_by_library(self, library_id: str) -> int:
        """Delete all records belonging to a library. Returns count deleted."""
        with get_connection() as conn:
            # Fetch record_ids first; FTS5 virtual tables require direct equality
            # comparisons (WHERE col = ?) — subquery-based IN clauses are silently ignored.
            record_ids = [
                row["record_id"]
                for row in conn.execute(
                    "SELECT record_id FROM records WHERE library_id = ?", (library_id,)
                ).fetchall()
            ]
            for record_id in record_ids:
                fts_delete(conn, record_id)
            if record_ids:
                placeholders = ",".join("?" * len(record_ids))
                conn.execute(
                    f"DELETE FROM record_embeddings WHERE record_id IN ({placeholders})",
                    record_ids,
                )
            cursor = conn.execute(
                "DELETE FROM records WHERE library_id = ?", (library_id,)
            )
        return cursor.rowcount

    def get_batch_accessible(
        self, record_ids: set[str], library_ids: set[str]
    ) -> list[Record]:
        """Fetch a specific set of records, filtered to accessible libraries."""
        if not record_ids:
            return []
        id_placeholders = ",".join("?" * len(record_ids))
        if not library_ids:
            lib_clause = "AND library_id IS NULL"
            lib_params: list = []
        else:
            lib_placeholders = ",".join("?" * len(library_ids))
            lib_clause = f"AND (library_id IS NULL OR library_id IN ({lib_placeholders}))"
            lib_params = list(library_ids)
        sql = (
            f"SELECT payload_json FROM records "
            f"WHERE record_id IN ({id_placeholders}) {lib_clause}"
        )
        with get_connection() as conn:
            rows = conn.execute(sql, list(record_ids) + lib_params).fetchall()
        return [Record.model_validate(_load_json_payload(row["payload_json"])) for row in rows]

    def get_embeddings_batch(
        self, record_ids: set[str]
    ) -> dict:
        """Return {record_id: np.ndarray} for all records that have stored embeddings."""
        if not record_ids:
            return {}
        placeholders = ",".join("?" * len(record_ids))
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT record_id, embedding FROM record_embeddings "
                f"WHERE record_id IN ({placeholders})",
                list(record_ids),
            ).fetchall()
        return {row["record_id"]: deserialize_embedding(row["embedding"]) for row in rows}


class FeedbackRepository:
    def insert(self, feedback: Feedback) -> None:
        with get_connection() as conn:
            conn.execute(
                _upsert(
                    "feedback",
                    ["feedback_id"],
                    ["feedback_id", "record_id", "payload_json"],
                ),
                (
                    feedback.feedback_id,
                    feedback.record_id,
                    _json_param(feedback.model_dump()),
                ),
            )

    def list_by_record(self, record_id: str) -> list[Feedback]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM feedback WHERE record_id = ?",
                (record_id,),
            ).fetchall()
        return [Feedback.model_validate(_load_json_payload(row["payload_json"])) for row in rows]


class RelationRepository:
    def insert(self, relation: RecordRelation) -> None:
        with get_connection() as conn:
            conn.execute(
                _upsert(
                    "relations",
                    ["relation_id"],
                    ["relation_id", "from_record_id", "to_record_id", "payload_json"],
                ),
                (
                    relation.relation_id,
                    relation.from_record_id,
                    relation.to_record_id,
                    _json_param(relation.model_dump()),
                ),
            )

    def list_by_record(self, record_id: str) -> list[RecordRelation]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM relations
                WHERE from_record_id = ? OR to_record_id = ?
                """,
                (record_id, record_id),
            ).fetchall()
        return [
            RecordRelation.model_validate(_load_json_payload(row["payload_json"]))
            for row in rows
        ]


class LibraryRepository:
    def insert(self, library: Library) -> None:
        with get_connection() as conn:
            conn.execute(
                _upsert(
                    "libraries",
                    ["library_id"],
                    [
                        "library_id",
                        "name",
                        "description",
                        "is_public",
                        "parent_library_id",
                        "is_personal",
                        "created_at",
                    ],
                ),
                (
                    library.library_id,
                    library.name,
                    library.description,
                    library.is_public,
                    library.parent_library_id,
                    library.is_personal,
                    library.created_at,
                ),
            )

    def get(self, library_id: str) -> Library | None:
        with get_connection() as conn:
            row = conn.execute(
                f"SELECT {_LIB_COLS} FROM libraries WHERE library_id = ?",
                (library_id,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_library(row)

    def list_all(self) -> list[Library]:
        with get_connection() as conn:
            rows = conn.execute(f"SELECT {_LIB_COLS} FROM libraries").fetchall()
        return [_row_to_library(r) for r in rows]

    def list_public(self) -> list[Library]:
        with get_connection() as conn:
            public_clause = "is_public = 1" if not is_postgres() else "is_public IS TRUE"
            rows = conn.execute(
                f"SELECT {_LIB_COLS} FROM libraries WHERE {public_clause}"
            ).fetchall()
        return [_row_to_library(r) for r in rows]

    def list_children(self, parent_library_id: str) -> list[Library]:
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT {_LIB_COLS} FROM libraries WHERE parent_library_id = ?",
                (parent_library_id,),
            ).fetchall()
        return [_row_to_library(r) for r in rows]

    def delete(self, library_id: str) -> bool:
        with get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM libraries WHERE library_id = ?", (library_id,)
            )
        return cursor.rowcount > 0


class TokenRepository:
    def insert(
        self,
        token_id: str,
        token_hash: str,
        library_id: str,
        label: str,
        role: str,
        created_at: str,
    ) -> None:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO tokens(token_id, token_hash, library_id, label, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (token_id, token_hash, library_id, label, role, created_at),
            )

    def get_by_hash(self, token_hash: str) -> TokenInfo | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT token_id, library_id, label, role, created_at FROM tokens WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        return TokenInfo(
            token_id=row["token_id"],
            library_id=row["library_id"],
            label=row["label"],
            role=row["role"],
            created_at=row["created_at"],
        )

    def list_by_library(self, library_id: str) -> list[TokenInfo]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT token_id, library_id, label, role, created_at FROM tokens WHERE library_id = ?",
                (library_id,),
            ).fetchall()
        return [
            TokenInfo(
                token_id=row["token_id"],
                library_id=row["library_id"],
                label=row["label"],
                role=row["role"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def delete(self, token_id: str) -> bool:
        with get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM tokens WHERE token_id = ?", (token_id,)
            )
        return cursor.rowcount > 0

    def delete_by_library(self, library_id: str) -> int:
        """Delete all tokens belonging to a library. Returns count deleted."""
        with get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM tokens WHERE library_id = ?", (library_id,)
            )
        return cursor.rowcount


class InviteCodeRepository:
    def insert(self, invite: InviteCode, code_hash: str) -> None:
        with get_connection() as conn:
            conn.execute(
                _upsert(
                    "invite_codes",
                    ["code_id"],
                    ["code_id", "code_hash", "created_at", "used_at", "used_by_library_id"],
                ),
                (
                    invite.code_id,
                    code_hash,
                    invite.created_at,
                    invite.used_at,
                    invite.used_by_library_id,
                ),
            )

    def get_by_hash(self, code_hash: str) -> InviteCode | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT code_id, created_at, used_at, used_by_library_id FROM invite_codes WHERE code_hash = ?",
                (code_hash,),
            ).fetchone()
        if row is None:
            return None
        return InviteCode(
            code_id=row["code_id"],
            created_at=row["created_at"],
            used_at=row["used_at"],
            used_by_library_id=row["used_by_library_id"],
        )

    def mark_used(self, code_id: str, used_at: str, used_by_library_id: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE invite_codes SET used_at = ?, used_by_library_id = ? WHERE code_id = ?",
                (used_at, used_by_library_id, code_id),
            )
