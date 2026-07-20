#!/usr/bin/env python3
"""Create or rotate the self-host bootstrap API key (no OIDC required).

Writes plaintext to MA3_BOOTSTRAP_KEY_FILE (default ./data/bootstrap_api_key.txt).

  python scripts/bootstrap_selfhost.py
  python scripts/bootstrap_selfhost.py --force
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.bootstrap_selfhost import ensure_bootstrap_key  # noqa: E402
from app.storage import db  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap self-host admin API key")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rotate key even if bootstrap file already exists",
    )
    args = parser.parse_args()
    db.initialize_database()
    result = ensure_bootstrap_key(force_new=args.force)
    if result is None:
        print("skipped (OIDC configured, bootstrap disabled, or key file already present)")
        print("use --force to rotate, or unset OIDC / set MA3_BOOTSTRAP_SELFHOST=1")
        return 0
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
