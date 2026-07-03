#!/usr/bin/env python3
"""Bootstrap a personal library + dual-grant API key (ADR-011 / design-08 slice).

Creates (idempotently):
  - a principal
  - a personal library owned by that principal
  - an API key with writer grants on the personal library and lib_default

Usage:
  python scripts/seed_personal_library_key.py \\
    --principal-id user:alice \\
    --display-name Alice \\
    --library-id lib_personal_alice \\
    --library-name "Alice personal library" \\
    --key-label alice-agent
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.services.api_key_service import hash_key  # noqa: E402
from app.storage import db  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed personal library + dual-grant API key")
    parser.add_argument("--principal-id", required=True, help="e.g. user:alice")
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--library-id", required=True)
    parser.add_argument("--library-name", required=True)
    parser.add_argument("--key-id", default=None, help="Stable key id; generated if omitted")
    parser.add_argument("--key-label", default="agent-key")
    parser.add_argument(
        "--public-role",
        default="writer",
        choices=("reader", "writer", "admin"),
        help="Grant role on lib_default (default writer for eval scenario)",
    )
    parser.add_argument(
        "--plaintext-key",
        default=None,
        help="Use an existing plaintext key (hash stored); if omitted and key is new, one is generated",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    db.initialize_database()

    sso_user = args.principal_id.removeprefix("user:")
    db.upsert_user_principal(sso_user=sso_user, display_name=args.display_name)
    db.ensure_library(
        args.library_id,
        name=args.library_name,
        visibility="private",
        kind="personal",
        owner_principal_id=args.principal_id,
    )

    key_id = args.key_id or f"key_{secrets.token_hex(6)}"
    existing = db.get_api_key_by_id(key_id)
    created = existing is None
    plaintext = args.plaintext_key
    if created and not plaintext:
        plaintext = f"ma3k_{secrets.token_hex(16)}"

    if created:
        assert plaintext is not None
        db.insert_api_key(
            key_id=key_id,
            key_hash=hash_key(plaintext),
            principal_id=args.principal_id,
            label=args.key_label,
            grants=[
                {"library_id": args.library_id, "role": "writer"},
                {"library_id": settings.default_library_id, "role": args.public_role},
            ],
        )
    else:
        db.upsert_api_key_grant(key_id, args.library_id, "writer")
        db.upsert_api_key_grant(key_id, settings.default_library_id, args.public_role)

    print(f"principal_id={args.principal_id}")
    print(f"library_id={args.library_id}")
    print(f"key_id={key_id}")
    if created and plaintext:
        print(f"plaintext_key={plaintext}")
    else:
        print("plaintext_key=(existing key unchanged; not printed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
