import json

from app.models.auth import AclEntry, ApiKeyInfo, AuthAuditEntry, Principal, PrincipalSummary, Role, RoleAssignment, ROLE_TO_LIBRARY_ROLE
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
    keys = row.keys() if hasattr(row, "keys") else ()
    return Library(
        library_id=row["library_id"],
        name=row["name"],
        description=row["description"],
        is_public=bool(row["is_public"]),
        organization_id=row["organization_id"] if "organization_id" in keys else None,
        parent_library_id=row["parent_library_id"] if "parent_library_id" in keys else None,
        is_personal=bool(row["is_personal"]) if "is_personal" in keys else False,
        created_at=row["created_at"],
    )


def _lib_cols() -> str:
    from app.core.config import settings

    if settings.api_version == "v4":
        return "library_id, organization_id, name, description, is_public, created_at"
    return "library_id, name, description, is_public, parent_library_id, is_personal, created_at"


_LIB_COLS = "library_id, name, description, is_public, parent_library_id, is_personal, created_at"


def _load_json_payload(raw):
    return raw if isinstance(raw, dict) else json.loads(raw)


def _load_json_list(raw) -> list[str] | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return [str(item) for item in json.loads(raw)]


def _row_to_principal(row) -> Principal:
    keys = row.keys() if hasattr(row, "keys") else ()
    return Principal(
        principal_id=row["principal_id"],
        kind=row["kind"],
        display_name=row["display_name"],
        sso_user=row["sso_user"],
        created_at=row["created_at"],
        is_admin=bool(row["is_admin"]) if "is_admin" in keys else False,
        metadata_json=_load_json_payload(row["metadata_json"] or "{}"),
    )


def _row_to_api_key(row) -> ApiKeyInfo:
    return ApiKeyInfo(
        key_id=row["key_id"],
        principal_id=row["principal_id"],
        label=row["label"],
        scope_libraries=_load_json_list(row["scope_libraries"]),
        created_at=row["created_at"],
        created_by=row["created_by"],
        last_used_at=row["last_used_at"],
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
    )


def _row_to_acl(row, principal: PrincipalSummary | None = None) -> AclEntry:
    return AclEntry(
        library_id=row["library_id"],
        principal_id=row["principal_id"],
        role=row["role"],
        granted_at=row["granted_at"],
        granted_by=row["granted_by"],
        principal=principal,
    )


def _row_to_role(row) -> Role:
    return Role(
        role_name=row["role_name"],
        scope_type=row["scope_type"],
        permissions=_load_json_list(row["permissions_json"]) or [],
        description=row["description"],
        created_at=row["created_at"],
    )


def _row_to_role_assignment(row, principal: PrincipalSummary | None = None) -> RoleAssignment:
    return RoleAssignment(
        scope_type=row["scope_type"],
        scope_id=row["scope_id"],
        principal_id=row["principal_id"],
        role_name=row["role_name"],
        granted_at=row["granted_at"],
        granted_by=row["granted_by"],
        principal=principal,
    )


def _role_assignment_to_acl(entry: RoleAssignment) -> AclEntry:
    return AclEntry(
        library_id=entry.scope_id or "",
        principal_id=entry.principal_id,
        role=ROLE_TO_LIBRARY_ROLE.get(entry.role_name, "reader"),
        granted_at=entry.granted_at,
        granted_by=entry.granted_by,
        principal=entry.principal,
    )


def _row_to_audit(row) -> AuthAuditEntry:
    return AuthAuditEntry(
        audit_id=row["audit_id"],
        actor_principal_id=row["actor_principal_id"],
        action=row["action"],
        target_principal_id=row["target_principal_id"],
        library_id=row["library_id"],
        payload_json=_load_json_payload(row["payload_json"] or "{}"),
        created_at=row["created_at"],
    )


class PrincipalRepository:
    def upsert(self, principal: Principal) -> Principal:
        from app.core.config import settings

        with get_connection() as conn:
            if settings.api_version == "v4":
                conn.execute(
                    _upsert(
                        "principals",
                        ["principal_id"],
                        [
                            "principal_id",
                            "kind",
                            "display_name",
                            "sso_user",
                            "created_at",
                            "metadata_json",
                        ],
                    ),
                    (
                        principal.principal_id,
                        principal.kind if principal.kind in {"user", "service"} else "user",
                        principal.display_name,
                        principal.sso_user,
                        principal.created_at,
                        _json_param(principal.metadata_json),
                    ),
                )
            else:
                conn.execute(
                    _upsert(
                        "principals",
                        ["principal_id"],
                        [
                            "principal_id",
                            "kind",
                            "display_name",
                            "sso_user",
                            "created_at",
                            "is_admin",
                            "metadata_json",
                        ],
                    ),
                    (
                        principal.principal_id,
                        principal.kind,
                        principal.display_name,
                        principal.sso_user,
                        principal.created_at,
                        principal.is_admin,
                        _json_param(principal.metadata_json),
                    ),
                )
        return principal

    def upsert_user(self, sso_user: str, display_name: str | None = None, *, is_admin: bool = False) -> Principal:
        principal = Principal(
            principal_id=f"user:{sso_user}",
            kind="user",
            display_name=display_name or sso_user,
            sso_user=sso_user,
            created_at=utc_now_iso(),
            is_admin=is_admin,
            metadata_json={},
        )
        self.upsert(principal)
        found = self.get(principal.principal_id)
        return found or principal

    def upsert_service(self, name: str, display_name: str | None = None) -> Principal:
        principal = Principal(
            principal_id=f"service:{name}",
            kind="service",
            display_name=display_name or name,
            sso_user=None,
            created_at=utc_now_iso(),
            is_admin=False,
            metadata_json={},
        )
        self.upsert(principal)
        found = self.get(principal.principal_id)
        return found or principal

    def upsert_legacy(self, principal_id: str, display_name: str, metadata: dict | None = None) -> Principal:
        principal = Principal(
            principal_id=principal_id,
            kind="legacy",
            display_name=display_name,
            sso_user=None,
            created_at=utc_now_iso(),
            is_admin=False,
            metadata_json=metadata or {},
        )
        self.upsert(principal)
        found = self.get(principal.principal_id)
        return found or principal

    def get(self, principal_id: str) -> Principal | None:
        from app.core.config import settings

        cols = (
            "principal_id, kind, display_name, sso_user, created_at, metadata_json"
            if settings.api_version == "v4"
            else "principal_id, kind, display_name, sso_user, created_at, is_admin, metadata_json"
        )
        with get_connection() as conn:
            row = conn.execute(
                f"SELECT {cols} FROM principals WHERE principal_id = ?",
                (principal_id,),
            ).fetchone()
        return _row_to_principal(row) if row else None

    def get_by_sso_user(self, sso_user: str) -> Principal | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT principal_id, kind, display_name, sso_user, created_at, is_admin, metadata_json
                FROM principals WHERE sso_user = ?
                """,
                (sso_user,),
            ).fetchone()
        return _row_to_principal(row) if row else None

    def search(self, prefix: str | None = None, kind: str | None = None, limit: int = 20) -> list[Principal]:
        conditions: list[str] = []
        params: list = []
        if prefix:
            conditions.append("principal_id LIKE ?")
            params.append(f"{prefix}%")
        if kind:
            conditions.append("kind = ?")
            params.append(kind)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT principal_id, kind, display_name, sso_user, created_at, is_admin, metadata_json
                FROM principals {where}
                ORDER BY principal_id ASC
                LIMIT ?
                """,
                params + [limit],
            ).fetchall()
        return [_row_to_principal(row) for row in rows]

    def count(self) -> int:
        with get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM principals").fetchone()
        return int(row["count"])


class ApiKeyRepository:
    def upsert(self, info: ApiKeyInfo, key_hash: str) -> ApiKeyInfo:
        with get_connection() as conn:
            conn.execute(
                _upsert(
                    "api_keys",
                    ["key_id"],
                    [
                        "key_id",
                        "key_hash",
                        "principal_id",
                        "label",
                        "scope_libraries",
                        "created_at",
                        "created_by",
                        "last_used_at",
                        "expires_at",
                        "revoked_at",
                    ],
                ),
                (
                    info.key_id,
                    key_hash,
                    info.principal_id,
                    info.label,
                    _json_param(info.scope_libraries) if info.scope_libraries is not None else None,
                    info.created_at,
                    info.created_by,
                    info.last_used_at,
                    info.expires_at,
                    info.revoked_at,
                ),
            )
        return info

    def get(self, key_id: str) -> ApiKeyInfo | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT key_id, principal_id, label, scope_libraries, created_at, created_by,
                       last_used_at, expires_at, revoked_at
                FROM api_keys WHERE key_id = ?
                """,
                (key_id,),
            ).fetchone()
        return _row_to_api_key(row) if row else None

    def get_by_hash(self, key_hash: str) -> tuple[ApiKeyInfo, Principal] | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT k.key_id, k.principal_id, k.label, k.scope_libraries, k.created_at,
                       k.created_by, k.last_used_at, k.expires_at, k.revoked_at,
                       p.kind AS principal_kind, p.display_name, p.sso_user,
                       p.created_at AS principal_created_at, p.is_admin, p.metadata_json
                FROM api_keys k
                JOIN principals p ON p.principal_id = k.principal_id
                WHERE k.key_hash = ?
                """,
                (key_hash,),
            ).fetchone()
        if row is None:
            return None
        info = _row_to_api_key(row)
        principal = Principal(
            principal_id=row["principal_id"],
            kind=row["principal_kind"],
            display_name=row["display_name"],
            sso_user=row["sso_user"],
            created_at=row["principal_created_at"],
            is_admin=bool(row["is_admin"]),
            metadata_json=_load_json_payload(row["metadata_json"] or "{}"),
        )
        return info, principal

    def list_by_principal(self, principal_id: str) -> list[ApiKeyInfo]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT key_id, principal_id, label, scope_libraries, created_at, created_by,
                       last_used_at, expires_at, revoked_at
                FROM api_keys WHERE principal_id = ?
                ORDER BY created_at DESC, key_id ASC
                """,
                (principal_id,),
            ).fetchall()
        return [_row_to_api_key(row) for row in rows]

    def list_all(self, limit: int = 500) -> list[ApiKeyInfo]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT key_id, principal_id, label, scope_libraries, created_at, created_by,
                       last_used_at, expires_at, revoked_at
                FROM api_keys
                ORDER BY created_at DESC, key_id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_api_key(row) for row in rows]

    def revoke(self, key_id: str, revoked_at: str) -> bool:
        with get_connection() as conn:
            cursor = conn.execute(
                "UPDATE api_keys SET revoked_at = ? WHERE key_id = ? AND revoked_at IS NULL",
                (revoked_at, key_id),
            )
        return cursor.rowcount > 0

    def update_last_used_at(self, key_id: str, last_used_at: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE key_id = ?",
                (last_used_at, key_id),
            )

    def count_active(self, now_iso: str | None = None) -> int:
        now_iso = now_iso or utc_now_iso()
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM api_keys
                WHERE revoked_at IS NULL AND (expires_at IS NULL OR expires_at > ?)
                """,
                (now_iso,),
            ).fetchone()
        return int(row["count"])


class LibraryAclRepository:
    def upsert(self, entry: AclEntry) -> AclEntry:
        with get_connection() as conn:
            conn.execute(
                _upsert(
                    "library_acl",
                    ["library_id", "principal_id"],
                    ["library_id", "principal_id", "role", "granted_at", "granted_by"],
                ),
                (
                    entry.library_id,
                    entry.principal_id,
                    entry.role,
                    entry.granted_at,
                    entry.granted_by,
                ),
            )
        return entry

    def get_role(self, library_id: str, principal_id: str) -> str | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT role FROM library_acl WHERE library_id = ? AND principal_id = ?",
                (library_id, principal_id),
            ).fetchone()
        return row["role"] if row else None

    def list_by_principal(self, principal_id: str) -> list[AclEntry]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT library_id, principal_id, role, granted_at, granted_by
                FROM library_acl WHERE principal_id = ?
                ORDER BY library_id ASC
                """,
                (principal_id,),
            ).fetchall()
        return [_row_to_acl(row) for row in rows]

    def list_by_library(self, library_id: str) -> list[AclEntry]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT a.library_id, a.principal_id, a.role, a.granted_at, a.granted_by,
                       p.kind, p.display_name
                FROM library_acl a
                LEFT JOIN principals p ON p.principal_id = a.principal_id
                WHERE a.library_id = ?
                ORDER BY a.principal_id ASC
                """,
                (library_id,),
            ).fetchall()
        entries: list[AclEntry] = []
        for row in rows:
            summary = None
            if row["kind"] is not None:
                summary = PrincipalSummary(
                    principal_id=row["principal_id"],
                    kind=row["kind"],
                    display_name=row["display_name"],
                )
            entries.append(_row_to_acl(row, summary))
        return entries

    def delete(self, library_id: str, principal_id: str) -> bool:
        with get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM library_acl WHERE library_id = ? AND principal_id = ?",
                (library_id, principal_id),
            )
        return cursor.rowcount > 0

    def count(self) -> int:
        with get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM library_acl").fetchone()
        return int(row["count"])

    def count_admins(self, library_id: str) -> int:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM library_acl WHERE library_id = ? AND role = 'admin'",
                (library_id,),
            ).fetchone()
        return int(row["count"])


class RoleRepository:
    def upsert(self, role: Role) -> Role:
        with get_connection() as conn:
            conn.execute(
                _upsert(
                    "roles",
                    ["role_name"],
                    ["role_name", "scope_type", "permissions_json", "description", "created_at"],
                ),
                (role.role_name, role.scope_type, _json_param(role.permissions), role.description, role.created_at),
            )
        return role

    def list(self) -> list[Role]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT role_name, scope_type, permissions_json, description, created_at
                FROM roles ORDER BY role_name ASC
                """
            ).fetchall()
        return [_row_to_role(row) for row in rows]

    def get(self, role_name: str) -> Role | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT role_name, scope_type, permissions_json, description, created_at
                FROM roles WHERE role_name = ?
                """,
                (role_name,),
            ).fetchone()
        return _row_to_role(row) if row else None


class RoleAssignmentRepository:
    def upsert(self, entry: RoleAssignment) -> RoleAssignment:
        with get_connection() as conn:
            conn.execute(
                """
                DELETE FROM role_assignments
                WHERE scope_type = ? AND COALESCE(scope_id, '') = COALESCE(?, '') AND principal_id = ?
                """,
                (entry.scope_type, entry.scope_id, entry.principal_id),
            )
            conn.execute(
                """
                INSERT INTO role_assignments(scope_type, scope_id, principal_id, role_name, granted_at, granted_by)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (entry.scope_type, entry.scope_id, entry.principal_id, entry.role_name, entry.granted_at, entry.granted_by),
            )
        return entry

    def list_by_principal(self, principal_id: str) -> list[RoleAssignment]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT scope_type, scope_id, principal_id, role_name, granted_at, granted_by
                FROM role_assignments WHERE principal_id = ?
                ORDER BY scope_type ASC, scope_id ASC, role_name ASC
                """,
                (principal_id,),
            ).fetchall()
        return [_row_to_role_assignment(row) for row in rows]

    def list_by_scope(self, scope_type: str, scope_id: str | None = None) -> list[RoleAssignment]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT a.scope_type, a.scope_id, a.principal_id, a.role_name, a.granted_at, a.granted_by,
                       p.kind, p.display_name
                FROM role_assignments a
                LEFT JOIN principals p ON p.principal_id = a.principal_id
                WHERE a.scope_type = ? AND COALESCE(a.scope_id, '') = COALESCE(?, '')
                ORDER BY a.principal_id ASC
                """,
                (scope_type, scope_id),
            ).fetchall()
        entries: list[RoleAssignment] = []
        for row in rows:
            summary = None
            if row["kind"] is not None:
                summary = PrincipalSummary(
                    principal_id=row["principal_id"],
                    kind=row["kind"],
                    display_name=row["display_name"],
                )
            entries.append(_row_to_role_assignment(row, summary))
        return entries

    def get_library_role(self, library_id: str, principal_id: str) -> str | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT role_name FROM role_assignments
                WHERE scope_type = 'library' AND scope_id = ? AND principal_id = ?
                """,
                (library_id, principal_id),
            ).fetchone()
        return ROLE_TO_LIBRARY_ROLE.get(row["role_name"]) if row else None

    def list_library_acl(self, library_id: str) -> list[AclEntry]:
        return [_role_assignment_to_acl(entry) for entry in self.list_by_scope("library", library_id)]

    def count_library_admins(self, library_id: str) -> int:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count FROM role_assignments
                WHERE scope_type = 'library' AND scope_id = ? AND role_name = 'library_admin'
                """,
                (library_id,),
            ).fetchone()
        return int(row["count"])

    def delete(self, scope_type: str, scope_id: str | None, principal_id: str) -> bool:
        with get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM role_assignments
                WHERE scope_type = ? AND COALESCE(scope_id, '') = COALESCE(?, '') AND principal_id = ?
                """,
                (scope_type, scope_id, principal_id),
            )
        return cursor.rowcount > 0

    def count(self) -> int:
        with get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM role_assignments").fetchone()
        return int(row["count"])


class AuthAuditRepository:
    def insert(self, entry: AuthAuditEntry) -> AuthAuditEntry:
        with get_connection() as conn:
            conn.execute(
                _upsert(
                    "auth_audit_log",
                    ["audit_id"],
                    [
                        "audit_id",
                        "actor_principal_id",
                        "action",
                        "target_principal_id",
                        "library_id",
                        "payload_json",
                        "created_at",
                    ],
                ),
                (
                    entry.audit_id,
                    entry.actor_principal_id,
                    entry.action,
                    entry.target_principal_id,
                    entry.library_id,
                    _json_param(entry.payload_json),
                    entry.created_at,
                ),
            )
        return entry

    def list(
        self,
        *,
        since: str | None = None,
        actor: str | None = None,
        action: str | None = None,
        limit: int = 100,
    ) -> list[AuthAuditEntry]:
        conditions: list[str] = []
        params: list = []
        if since:
            conditions.append("created_at >= ?")
            params.append(since)
        if actor:
            conditions.append("actor_principal_id = ?")
            params.append(actor)
        if action:
            conditions.append("action = ?")
            params.append(action)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT audit_id, actor_principal_id, action, target_principal_id,
                       library_id, payload_json, created_at
                FROM auth_audit_log {where}
                ORDER BY created_at DESC, audit_id ASC
                LIMIT ?
                """,
                params + [limit],
            ).fetchall()
        return [_row_to_audit(row) for row in rows]

    def count_by_action(self) -> dict[str, int]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT action, COUNT(*) AS count FROM auth_audit_log GROUP BY action"
            ).fetchall()
        return {row["action"]: int(row["count"]) for row in rows}

    def count_admin_bypass_recent(self, since: str) -> int:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count FROM auth_audit_log
                WHERE action = 'principal.assume_admin' AND created_at >= ?
                """,
                (since,),
            ).fetchone()
        return int(row["count"])


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

    def find_ids_by_exact_tags_accessible(
        self,
        tags: list[str],
        library_ids: set[str],
        status: "str | tuple[str, ...] | list[str] | None" = None,
        limit: int = 200,
    ) -> list[tuple[str, int]]:
        """Return record IDs with exact case-insensitive tag matches.

        This is a metadata candidate-expansion path, not final authorization or
        ranking. It intentionally does not rely on FTS tokenization so rare tags
        containing punctuation such as ``hpc-x`` and ``jobssh`` are not lost.

        ``status`` accepts a single status string, an iterable of statuses, or
        ``None`` (the default searchable set: active + stale + superseded).
        Soft-decayed records are kept so they can be re-ranked, not dropped.
        """
        from app.models.enums import SEARCHABLE_RECORD_STATUSES

        normalized_tags = sorted({tag.strip().lower() for tag in tags if tag and tag.strip()})
        if not normalized_tags:
            return []

        if status is None:
            statuses = tuple(s.value for s in SEARCHABLE_RECORD_STATUSES)
        elif isinstance(status, str):
            statuses = (status,)
        else:
            statuses = tuple(s.value if hasattr(s, "value") else str(s) for s in status)
        status_ph = ",".join("?" * len(statuses))

        tag_placeholders = ",".join("?" * len(normalized_tags))
        params: list = list(normalized_tags)
        if not library_ids:
            lib_clause = "AND r.library_id IS NULL"
            lib_params: list = []
        else:
            lib_placeholders = ",".join("?" * len(library_ids))
            lib_clause = f"AND (r.library_id IS NULL OR r.library_id IN ({lib_placeholders}))"
            lib_params = list(library_ids)

        if is_postgres():
            sql = f"""
                SELECT r.record_id, COUNT(*) AS match_count
                FROM records r
                JOIN LATERAL jsonb_array_elements_text(COALESCE(r.payload_json->'tags', '[]'::jsonb)) AS tag(value) ON TRUE
                WHERE lower(tag.value) IN ({tag_placeholders})
                  {lib_clause}
                  AND r.status IN ({status_ph})
                GROUP BY r.record_id
                ORDER BY match_count DESC, r.record_id ASC
                LIMIT ?
            """
        else:
            sql = f"""
                SELECT r.record_id, COUNT(*) AS match_count
                FROM records r
                JOIN json_each(r.payload_json, '$.tags') AS tag
                WHERE lower(tag.value) IN ({tag_placeholders})
                  {lib_clause}
                  AND r.status IN ({status_ph})
                GROUP BY r.record_id
                ORDER BY match_count DESC, r.record_id ASC
                LIMIT ?
            """

        with get_connection() as conn:
            rows = conn.execute(sql, params + lib_params + [*statuses, limit]).fetchall()
        return [(row["record_id"], int(row["match_count"])) for row in rows]

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
        return self.list_by_record_ids({record_id}).get(record_id, [])

    def list_by_record_ids(self, record_ids: set[str]) -> dict[str, list[Feedback]]:
        if not record_ids:
            return {}
        placeholders = ",".join("?" * len(record_ids))
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT record_id, payload_json FROM feedback WHERE record_id IN ({placeholders})",
                list(record_ids),
            ).fetchall()
        grouped: dict[str, list[Feedback]] = {record_id: [] for record_id in record_ids}
        for row in rows:
            grouped.setdefault(row["record_id"], []).append(
                Feedback.model_validate(_load_json_payload(row["payload_json"]))
            )
        return grouped


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
        return self.list_by_record_ids({record_id}).get(record_id, [])

    def list_by_record_ids(self, record_ids: set[str]) -> dict[str, list[RecordRelation]]:
        if not record_ids:
            return {}
        placeholders = ",".join("?" * len(record_ids))
        params = list(record_ids) + list(record_ids)
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT payload_json
                FROM relations
                WHERE from_record_id IN ({placeholders}) OR to_record_id IN ({placeholders})
                """,
                params,
            ).fetchall()
        grouped: dict[str, list[RecordRelation]] = {record_id: [] for record_id in record_ids}
        for row in rows:
            relation = RecordRelation.model_validate(_load_json_payload(row["payload_json"]))
            if relation.from_record_id in grouped:
                grouped[relation.from_record_id].append(relation)
            if relation.to_record_id in grouped and relation.to_record_id != relation.from_record_id:
                grouped[relation.to_record_id].append(relation)
        return grouped


class LibraryRepository:
    def insert(self, library: Library) -> None:
        from app.core.config import settings

        with get_connection() as conn:
            if settings.api_version == "v4":
                conn.execute(
                    _upsert(
                        "libraries",
                        ["library_id"],
                        [
                            "library_id",
                            "organization_id",
                            "name",
                            "description",
                            "is_public",
                            "created_at",
                        ],
                    ),
                    (
                        library.library_id,
                        library.organization_id,
                        library.name,
                        library.description,
                        library.is_public,
                        library.created_at,
                    ),
                )
            else:
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
        cols = _lib_cols()
        with get_connection() as conn:
            row = conn.execute(
                f"SELECT {cols} FROM libraries WHERE library_id = ?",
                (library_id,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_library(row)

    def list_all(self) -> list[Library]:
        cols = _lib_cols()
        with get_connection() as conn:
            rows = conn.execute(f"SELECT {cols} FROM libraries").fetchall()
        return [_row_to_library(r) for r in rows]

    def list_public(self) -> list[Library]:
        cols = _lib_cols()
        with get_connection() as conn:
            public_clause = "is_public = 1" if not is_postgres() else "is_public IS TRUE"
            rows = conn.execute(
                f"SELECT {cols} FROM libraries WHERE {public_clause}"
            ).fetchall()
        return [_row_to_library(r) for r in rows]

    def list_children(self, parent_library_id: str) -> list[Library]:
        cols = _lib_cols()
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT {cols} FROM libraries WHERE parent_library_id = ?",
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
