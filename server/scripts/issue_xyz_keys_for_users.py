#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core import config  # noqa: E402
from app.core.security import ResolvedPrincipal  # noqa: E402
from app.storage.db import initialize_database  # noqa: E402
from app.storage.repositories import LibraryRepository, PrincipalRepository  # noqa: E402
from app.services.auth_service import grant_library_access, issue_api_key  # noqa: E402


ADMIN_ACTOR = ResolvedPrincipal(
    principal_id="admin:root",
    kind="admin",
    display_name="ma3 root admin",
    via="admin_key",
    is_admin_bypass=True,
)


def _users(raw: str | None, path: str | None) -> list[str]:
    values: list[str] = []
    if raw:
        values.extend(raw.split(","))
    if path:
        values.extend(Path(path).read_text(encoding="utf-8").splitlines())
    return sorted({item.strip() for item in values if item.strip()})


def _xyz_library_id() -> str:
    if config.settings.xyz_library_id:
        return config.settings.xyz_library_id
    candidates = [lib for lib in LibraryRepository().list_all() if lib.name.strip().lower() == "xyz"]
    if len(candidates) == 1:
        return candidates[0].library_id
    raise SystemExit("MA3_XYZ_LIBRARY_ID is required unless exactly one library is named 'xyz'")


def issue(users: list[str], *, apply: bool, out: Path) -> dict:
    initialize_database(run_backfill=False)
    xyz = _xyz_library_id()
    result: dict[str, dict] = {}
    if not apply:
        return {user: {"principal_id": f"user:{user}", "library_id": xyz, "dry_run": True} for user in users}
    principals = PrincipalRepository()
    for user in users:
        principal = principals.upsert_user(user, user)
        grant_library_access(xyz, principal.principal_id, "writer", actor=ADMIN_ACTOR)
        issued = issue_api_key(
            principal.principal_id,
            "xyz default",
            [xyz],
            None,
            actor=ADMIN_ACTOR,
        )
        result[user] = {
            "principal_id": principal.principal_id,
            "library_id": xyz,
            "key_id": issued.info.key_id,
            "raw": issued.raw,
        }
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    os.chmod(out, stat.S_IRUSR | stat.S_IWUSR)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue per-user ma3 xyz-library API keys.")
    parser.add_argument("--users", help="comma-separated SSO usernames")
    parser.add_argument("--users-file", help="file with one SSO username per line")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="write keys and output raw secrets")
    mode.add_argument("--dry-run", action="store_true", help="show what would be issued")
    parser.add_argument("--out", required=True, help="output JSON path (written mode 0600 in --apply)")
    args = parser.parse_args()
    users = _users(args.users, args.users_file)
    if not users:
        raise SystemExit("no users supplied")
    out = Path(args.out)
    result = issue(users, apply=bool(args.apply), out=out)
    if args.apply:
        print(str(out))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
