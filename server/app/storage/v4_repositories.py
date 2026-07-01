from __future__ import annotations

import json
import re

from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.models.auth import ApiKeyInfo, Principal
from app.models.v4_org import (
    ApiKeyGrant,
    LibraryAccessEntry,
    Organization,
    OrganizationMember,
    SessionRecord,
)
from app.storage.db import _json_param, _upsert, get_connection, is_postgres


_SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


def normalize_org_slug(raw: str) -> str:
    slug = raw.strip().lower().replace(" ", "-")
    slug = re.sub(r"[^a-z0-9-]+", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug or not _SLUG_RE.match(slug):
        raise ValueError("invalid org slug")
    return slug


def _load_json(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    return json.loads(raw)


class OrganizationRepository:
    def insert(self, org: Organization) -> None:
        with get_connection() as conn:
            conn.execute(
                _upsert(
                    "organizations",
                    ["org_id"],
                    [
                        "org_id",
                        "slug",
                        "name",
                        "description",
                        "plan_tier",
                        "member_seat_limit",
                        "created_at",
                        "created_by",
                        "deleted_at",
                    ],
                ),
                (
                    org.org_id,
                    org.slug,
                    org.name,
                    org.description,
                    org.plan_tier,
                    org.member_seat_limit,
                    org.created_at,
                    org.created_by,
                    org.deleted_at,
                ),
            )

    def get(self, org_id: str) -> Organization | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT org_id, slug, name, description, plan_tier, member_seat_limit,
                       created_at, created_by, deleted_at
                FROM organizations WHERE org_id = ? AND deleted_at IS NULL
                """,
                (org_id,),
            ).fetchone()
        return _row_org(row) if row else None

    def get_by_slug(self, slug: str) -> Organization | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT org_id, slug, name, description, plan_tier, member_seat_limit,
                       created_at, created_by, deleted_at
                FROM organizations WHERE slug = ? AND deleted_at IS NULL
                """,
                (slug,),
            ).fetchone()
        return _row_org(row) if row else None

    def list_for_principal(self, principal_id: str) -> list[Organization]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT o.org_id, o.slug, o.name, o.description, o.plan_tier, o.member_seat_limit,
                       o.created_at, o.created_by, o.deleted_at
                FROM organizations o
                JOIN organization_members m ON m.org_id = o.org_id
                WHERE m.principal_id = ? AND o.deleted_at IS NULL
                ORDER BY o.created_at ASC
                """,
                (principal_id,),
            ).fetchall()
        return [_row_org(r) for r in rows]

    def update_seat_limit(self, org_id: str, member_seat_limit: int, plan_tier: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE organizations SET member_seat_limit = ?, plan_tier = ? WHERE org_id = ?",
                (member_seat_limit, plan_tier, org_id),
            )


class OrganizationMemberRepository:
    def insert(self, member: OrganizationMember) -> None:
        with get_connection() as conn:
            conn.execute(
                _upsert(
                    "organization_members",
                    ["org_id", "principal_id"],
                    ["org_id", "principal_id", "org_role", "joined_at", "invited_by"],
                ),
                (
                    member.org_id,
                    member.principal_id,
                    member.org_role,
                    member.joined_at,
                    member.invited_by,
                ),
            )

    def count(self, org_id: str) -> int:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM organization_members WHERE org_id = ?",
                (org_id,),
            ).fetchone()
        return int(row["c"])

    def get_role(self, org_id: str, principal_id: str) -> str | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT org_role FROM organization_members WHERE org_id = ? AND principal_id = ?",
                (org_id, principal_id),
            ).fetchone()
        return row["org_role"] if row else None

    def list_members(self, org_id: str) -> list[OrganizationMember]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT org_id, principal_id, org_role, joined_at, invited_by
                FROM organization_members WHERE org_id = ?
                ORDER BY joined_at ASC
                """,
                (org_id,),
            ).fetchall()
        return [_row_member(r) for r in rows]

    def delete(self, org_id: str, principal_id: str) -> bool:
        with get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM organization_members WHERE org_id = ? AND principal_id = ?",
                (org_id, principal_id),
            )
        return cur.rowcount > 0


class LibraryAccessRepository:
    def upsert(self, entry: LibraryAccessEntry) -> None:
        with get_connection() as conn:
            conn.execute(
                _upsert(
                    "library_access",
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

    def list_by_library(self, library_id: str) -> list[LibraryAccessEntry]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT library_id, principal_id, role, granted_at, granted_by
                FROM library_access WHERE library_id = ?
                """,
                (library_id,),
            ).fetchall()
        return [_row_access(r) for r in rows]

    def list_by_principal(self, principal_id: str) -> list[LibraryAccessEntry]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT library_id, principal_id, role, granted_at, granted_by
                FROM library_access WHERE principal_id = ?
                """,
                (principal_id,),
            ).fetchall()
        return [_row_access(r) for r in rows]

    def get_role(self, library_id: str, principal_id: str) -> str | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT role FROM library_access WHERE library_id = ? AND principal_id = ?",
                (library_id, principal_id),
            ).fetchone()
        return row["role"] if row else None

    def delete(self, library_id: str, principal_id: str) -> bool:
        with get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM library_access WHERE library_id = ? AND principal_id = ?",
                (library_id, principal_id),
            )
        return cur.rowcount > 0


class ApiKeyGrantRepository:
    def replace_for_key(self, key_id: str, grants: list[ApiKeyGrant]) -> None:
        with get_connection() as conn:
            conn.execute("DELETE FROM api_key_grants WHERE key_id = ?", (key_id,))
            for grant in grants:
                conn.execute(
                    """
                    INSERT INTO api_key_grants(key_id, library_id, role)
                    VALUES (?, ?, ?)
                    """,
                    (grant.key_id, grant.library_id, grant.role),
                )

    def list_by_key(self, key_id: str) -> list[ApiKeyGrant]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT key_id, library_id, role FROM api_key_grants WHERE key_id = ?",
                (key_id,),
            ).fetchall()
        return [ApiKeyGrant(**dict(r)) for r in rows]

    def list_by_keys(self, key_ids: list[str]) -> dict[str, list[ApiKeyGrant]]:
        if not key_ids:
            return {}
        placeholders = ",".join("?" for _ in key_ids)
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT key_id, library_id, role FROM api_key_grants WHERE key_id IN ({placeholders})",
                tuple(key_ids),
            ).fetchall()
        out: dict[str, list[ApiKeyGrant]] = {}
        for row in rows:
            g = ApiKeyGrant(**dict(row))
            out.setdefault(g.key_id, []).append(g)
        return out


class SessionRepository:
    def insert(self, session: SessionRecord) -> None:
        with get_connection() as conn:
            conn.execute(
                _upsert(
                    "sessions",
                    ["session_id"],
                    ["session_id", "principal_id", "expires_at", "created_at", "idp_region"],
                ),
                (
                    session.session_id,
                    session.principal_id,
                    session.expires_at,
                    session.created_at,
                    session.idp_region,
                ),
            )

    def get(self, session_id: str) -> SessionRecord | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT session_id, principal_id, expires_at, created_at, idp_region FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return SessionRecord(**dict(row))

    def delete(self, session_id: str) -> None:
        with get_connection() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))


def _row_org(row) -> Organization:
    return Organization(
        org_id=row["org_id"],
        slug=row["slug"],
        name=row["name"],
        description=row["description"],
        plan_tier=row["plan_tier"],
        member_seat_limit=int(row["member_seat_limit"]),
        created_at=row["created_at"],
        created_by=row["created_by"],
        deleted_at=row["deleted_at"],
    )


def _row_member(row) -> OrganizationMember:
    return OrganizationMember(**dict(row))


def _row_access(row) -> LibraryAccessEntry:
    return LibraryAccessEntry(**dict(row))


def new_org_id() -> str:
    return new_id("org")


def _row_api_key(row) -> ApiKeyInfo:
    return ApiKeyInfo(
        key_id=row["key_id"],
        principal_id=row["principal_id"],
        label=row["label"],
        scope_libraries=None,
        created_at=row["created_at"],
        created_by=row["created_by"],
        last_used_at=row["last_used_at"],
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
    )


class V4ApiKeyRepository:
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
                SELECT key_id, principal_id, label, created_at, created_by,
                       last_used_at, expires_at, revoked_at
                FROM api_keys WHERE key_id = ?
                """,
                (key_id,),
            ).fetchone()
        return _row_api_key(row) if row else None

    def get_by_hash(self, key_hash: str) -> tuple[ApiKeyInfo, Principal] | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT k.key_id, k.principal_id, k.label, k.created_at, k.created_by,
                       k.last_used_at, k.expires_at, k.revoked_at,
                       p.kind AS principal_kind, p.display_name, p.sso_user,
                       p.created_at AS principal_created_at, p.metadata_json
                FROM api_keys k
                JOIN principals p ON p.principal_id = k.principal_id
                WHERE k.key_hash = ?
                """,
                (key_hash,),
            ).fetchone()
        if row is None:
            return None
        info = _row_api_key(row)
        principal = Principal(
            principal_id=row["principal_id"],
            kind=row["principal_kind"],
            display_name=row["display_name"],
            sso_user=row["sso_user"],
            created_at=row["principal_created_at"],
            is_admin=False,
            metadata_json=_load_json(row["metadata_json"] or "{}"),
        )
        return info, principal

    def list_by_principal(self, principal_id: str) -> list[ApiKeyInfo]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT key_id, principal_id, label, created_at, created_by,
                       last_used_at, expires_at, revoked_at
                FROM api_keys
                WHERE principal_id = ? AND revoked_at IS NULL
                ORDER BY created_at DESC
                """,
                (principal_id,),
            ).fetchall()
        return [_row_api_key(r) for r in rows]

    def touch_last_used(self, key_id: str, ts: str) -> None:
        with get_connection() as conn:
            conn.execute("UPDATE api_keys SET last_used_at = ? WHERE key_id = ?", (ts, key_id))

    def revoke(self, key_id: str, ts: str) -> None:
        with get_connection() as conn:
            conn.execute("UPDATE api_keys SET revoked_at = ? WHERE key_id = ?", (ts, key_id))
