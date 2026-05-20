#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.core.time import utc_now_iso  # noqa: E402
from app.models.auth import BUILTIN_ROLES, ROLE_SCOPE_TYPES, RoleAssignment  # noqa: E402
from app.storage.db import _json_param, get_connection, initialize_database, is_postgres  # noqa: E402
from app.storage.repositories import PrincipalRepository, RoleAssignmentRepository  # noqa: E402

ROLE_MAP = {"reader": "library_reader", "writer": "library_writer", "admin": "library_admin"}


def _insert_builtin_roles(apply: bool) -> None:
    if not apply:
        return
    now = utc_now_iso()
    with get_connection() as conn:
        for role_name, permissions in BUILTIN_ROLES.items():
            if is_postgres():
                conn.execute(
                    """
                    INSERT INTO roles(role_name, scope_type, permissions_json, description, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (role_name) DO NOTHING
                    """,
                    (role_name, ROLE_SCOPE_TYPES.get(role_name, "library"), _json_param(permissions), f"Built-in {role_name}", now),
                )
            else:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO roles(role_name, scope_type, permissions_json, description, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (role_name, ROLE_SCOPE_TYPES.get(role_name, "library"), _json_param(permissions), f"Built-in {role_name}", now),
                )


def migrate(apply: bool) -> tuple[int, int]:
    initialize_database(run_backfill=False)
    _insert_builtin_roles(apply)
    now = utc_now_iso()
    migrated = 0
    with get_connection() as conn:
        rows = conn.execute("SELECT library_id, principal_id, role, granted_at, granted_by FROM library_acl").fetchall()
    repo = RoleAssignmentRepository()
    for row in rows:
        role_name = ROLE_MAP.get(row["role"])
        if not role_name:
            continue
        exists = repo.get_library_role(row["library_id"], row["principal_id"])
        if exists is not None:
            continue
        migrated += 1
        if apply:
            repo.upsert(RoleAssignment(
                scope_type="library",
                scope_id=row["library_id"],
                principal_id=row["principal_id"],
                role_name=role_name,
                granted_at=row["granted_at"],
                granted_by=row["granted_by"],
            ))
    created_admins = 0
    principals = PrincipalRepository()
    for username in settings.auth_admin_users:
        principal_id = f"user:{username}"
        if principals.get(principal_id) is None:
            created_admins += 1
            if apply:
                principals.upsert_user(username, username, is_admin=True)
        existing = [a for a in repo.list_by_principal(principal_id) if a.scope_type == "system" and a.role_name == "system_admin"]
        if not existing and apply:
            repo.upsert(RoleAssignment(
                scope_type="system",
                scope_id=None,
                principal_id=principal_id,
                role_name="system_admin",
                granted_at=now,
                granted_by=principal_id,
            ))
    return migrated, created_admins


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate ma3 v3 ACLs to v3.1 RBAC role_assignments")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true")
    group.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    apply = bool(args.apply)
    migrated, created_admins = migrate(apply=apply)
    print(f"migrated_assignments={migrated} created_admins={created_admins}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
