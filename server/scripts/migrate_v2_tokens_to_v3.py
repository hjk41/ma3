#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core import config  # noqa: E402
from app.core.auth import hash_token  # noqa: E402
from app.core.time import utc_now_iso  # noqa: E402
from app.storage.db import _json_param, _upsert, get_connection, initialize_database  # noqa: E402


def _configure_db_url(db_url: str | None) -> None:
    if not db_url:
        return
    object.__setattr__(config.settings, "database_url", db_url)
    object.__setattr__(config.settings, "db_backend", "postgresql")


def migrate(*, apply: bool, db_url: str | None = None) -> int:
    _configure_db_url(db_url)
    initialize_database(run_backfill=False)
    with get_connection() as conn:
        libraries = conn.execute(
            "SELECT library_id, name, created_at FROM libraries ORDER BY library_id"
        ).fetchall()
        tokens = conn.execute(
            "SELECT token_id, token_hash, library_id, label, role, created_at FROM tokens ORDER BY token_id"
        ).fetchall()
        if not apply:
            print(f"dry_run_tokens={len(tokens)}")
            print("migrated_tokens=0")
            return 0
        now = utc_now_iso()
        for lib in libraries:
            principal_id = f"legacy:lib:{lib['library_id']}"
            conn.execute(
                _upsert(
                    "principals",
                    ["principal_id"],
                    ["principal_id", "kind", "display_name", "sso_user", "created_at", "is_admin", "metadata_json"],
                ),
                (
                    principal_id,
                    "legacy",
                    f"legacy library {lib['name'] or lib['library_id']}",
                    None,
                    lib["created_at"] or now,
                    False,
                    _json_param({"library_id": lib["library_id"]}),
                ),
            )
        for tok in tokens:
            principal_id = f"legacy:{tok['token_id']}"
            lib_principal_id = f"legacy:lib:{tok['library_id']}"
            conn.execute(
                _upsert(
                    "principals",
                    ["principal_id"],
                    ["principal_id", "kind", "display_name", "sso_user", "created_at", "is_admin", "metadata_json"],
                ),
                (
                    principal_id,
                    "legacy",
                    tok["label"] or tok["token_id"],
                    None,
                    tok["created_at"] or now,
                    False,
                    _json_param({"migrated_from_token": tok["token_id"], "library_id": tok["library_id"]}),
                ),
            )
            conn.execute(
                _upsert(
                    "library_acl",
                    ["library_id", "principal_id"],
                    ["library_id", "principal_id", "role", "granted_at", "granted_by"],
                ),
                (
                    tok["library_id"],
                    principal_id,
                    tok["role"] or "writer",
                    tok["created_at"] or now,
                    lib_principal_id,
                ),
            )
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
                    f"akey_legacy_{tok['token_id']}",
                    tok["token_hash"],
                    principal_id,
                    "v2 token: " + (tok["label"] or tok["token_id"]),
                    _json_param([tok["library_id"]]),
                    tok["created_at"] or now,
                    lib_principal_id,
                    None,
                    None,
                    None,
                ),
            )
            conn.execute(
                _upsert(
                    "auth_audit_log",
                    ["audit_id"],
                    ["audit_id", "actor_principal_id", "action", "target_principal_id", "library_id", "payload_json", "created_at"],
                ),
                (
                    f"aud_migrate_{tok['token_id']}",
                    lib_principal_id,
                    "principal.create",
                    principal_id,
                    tok["library_id"],
                    _json_param({"migrated_from_token": tok["token_id"]}),
                    now,
                ),
            )
    print(f"migrated_tokens={len(tokens)}")
    return len(tokens)


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate v2 library tokens into v3 principals/api_keys/ACLs.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="write changes")
    mode.add_argument("--dry-run", action="store_true", help="show what would be migrated")
    parser.add_argument("--db-url", help="override MA3_DATABASE_URL")
    args = parser.parse_args()
    migrate(apply=bool(args.apply), db_url=args.db_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
