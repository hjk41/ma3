from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from app.services.doctor_service import backup_doctor_block


def _touch(path, when: datetime) -> None:
    ts = when.timestamp()
    os.utime(path, (ts, ts))


def test_backup_block_legacy_when_disabled(monkeypatch, tmp_path):
    monkeypatch.delenv("MA3_BACKUP_DIR", raising=False)
    monkeypatch.setenv("MA3_PG_ARCHIVE_ENABLE", "0")
    assert backup_doctor_block() == {"mode": "legacy"}


def test_backup_block_reports_lag_and_age(monkeypatch, tmp_path):
    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    instance = "ma3-test"
    wal_dir = tmp_path / "wal" / instance
    wal_dir.mkdir(parents=True)
    wal = wal_dir / "000000010000000000000017"
    wal.write_bytes(b"wal")
    _touch(wal, now - timedelta(seconds=18))

    backup_dir = tmp_path / "basebackups" / instance / "20260520-113000Z"
    backup_dir.mkdir(parents=True)
    base_manifest = backup_dir / "manifest.json"
    base_manifest.write_text(json.dumps({"created_at": "2026-05-20T11:30:00Z"}), encoding="utf-8")

    pitr = tmp_path / "pitr_manifest.json"
    pitr.write_text(
        json.dumps({"created_at": "2026-05-20T11:30:00Z", "basebackup_instance_id": instance}),
        encoding="utf-8",
    )

    monkeypatch.setenv("MA3_PG_ARCHIVE_ENABLE", "1")
    monkeypatch.setenv("MA3_BACKUP_DIR", str(tmp_path))
    monkeypatch.setenv("MA3_INSTANCE_ID", instance)
    monkeypatch.setenv("MA3_PG_ARCHIVE_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("MA3_PG_BASEBACKUP_INTERVAL_MIN", "30")

    block = backup_doctor_block(now=now)

    assert block["mode"] == "pitr"
    assert block["wal_dir"] == f"wal/{instance}"
    assert block["last_archived_wal"] == wal.name
    assert block["archive_lag_seconds"] == 18
    assert block["basebackup_age_seconds"] == 1800
    assert block["pitr_manifest_age_seconds"] == 1800
    assert block["degraded"] is False


def test_backup_block_degraded_when_stale(monkeypatch, tmp_path):
    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    instance = "ma3-test"
    wal_dir = tmp_path / "wal" / instance
    wal_dir.mkdir(parents=True)
    wal = wal_dir / "000000010000000000000018"
    wal.write_bytes(b"wal")
    _touch(wal, now - timedelta(seconds=301))

    backup_dir = tmp_path / "basebackups" / instance / "20260520-100000Z"
    backup_dir.mkdir(parents=True)
    (backup_dir / "manifest.json").write_text(json.dumps({"created_at": "2026-05-20T10:00:00Z"}), encoding="utf-8")
    (tmp_path / "pitr_manifest.json").write_text(json.dumps({"created_at": "2026-05-20T10:00:00Z"}), encoding="utf-8")

    monkeypatch.setenv("MA3_PG_ARCHIVE_ENABLE", "1")
    monkeypatch.setenv("MA3_BACKUP_DIR", str(tmp_path))
    monkeypatch.setenv("MA3_INSTANCE_ID", instance)
    monkeypatch.setenv("MA3_PG_ARCHIVE_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("MA3_PG_BASEBACKUP_INTERVAL_MIN", "30")

    block = backup_doctor_block(now=now)

    assert block["archive_lag_seconds"] == 301
    assert block["basebackup_age_seconds"] == 7200
    assert block["degraded"] is True
