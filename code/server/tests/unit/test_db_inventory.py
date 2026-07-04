from __future__ import annotations

import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER_ROOT / "scripts"))
import db_inventory  # noqa: E402


def test_compare_ok_after_full_backfill():
    pre = {
        "v1_records": 23,
        "v1_cases": 23,
        "legacy_records": 104,
        "legacy_importable": 104,
        "legacy_overlap_v1": 0,
        "legacy_seed_skipped": 0,
    }
    post = {
        "v1_records": 127,
        "v1_cases": 89,
        "legacy_importable": 0,
    }
    backfill = {"records_imported": 104, "records_indexed": 104}
    assert db_inventory.compare_inventory(pre, post, backfill=backfill) == []


def test_compare_fails_when_v1_shrinks():
    pre = {"v1_records": 23, "legacy_importable": 0}
    post = {"v1_records": 20, "legacy_importable": 0}
    errors = db_inventory.compare_inventory(pre, post)
    assert any("decreased" in e for e in errors)


def test_compare_fails_when_backfill_incomplete():
    pre = {"v1_records": 23, "legacy_importable": 104, "legacy_records": 104}
    post = {"v1_records": 50, "legacy_importable": 77}
    backfill = {"records_imported": 27}
    errors = db_inventory.compare_inventory(pre, post, backfill=backfill)
    assert len(errors) >= 2
