from __future__ import annotations

import gzip
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings


_SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "cookie",
    "ma3_api_key",
    "ma3_admin_key",
    "password",
    "pgpassword",
    "secret",
    "token",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _today_path() -> Path:
    settings.op_log_dir.mkdir(parents=True, exist_ok=True)
    return settings.op_log_dir / f"{_utc_now().date().isoformat()}.jsonl"


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if any(s in k.lower() for s in _SENSITIVE_KEYS):
                out[k] = "<redacted>"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(value, list):
        return [_redact(v) for v in value[:50]]
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "...<truncated>"
    return value


def write_op_log(event_type: str, **fields: Any) -> None:
    """Append one redacted JSONL operation event.

    Logging is best-effort and must never break request handling.
    """
    try:
        event = {
            "ts": _utc_now().isoformat(),
            "event_type": event_type,
            "instance_id": settings.instance_id,
            "git_commit": settings.git_commit,
            **fields,
        }
        if settings.log_redact_raw:
            event = _redact(event)
        with _today_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        return


def archive_completed_logs() -> dict:
    """Compress completed local logs and copy them to MA3_LOG_ARCHIVE_DIR.

    Today's JSONL remains open locally. Older JSONLs are gzipped. Gzipped logs are
    copied to the archive dir and deleted locally after the retention window.
    """
    today = _utc_now().date().isoformat()
    settings.op_log_dir.mkdir(parents=True, exist_ok=True)
    archived: list[str] = []
    compressed: list[str] = []
    deleted: list[str] = []

    for path in sorted(settings.op_log_dir.glob("*.jsonl")):
        if path.stem == today:
            continue
        gz = path.with_suffix(path.suffix + ".gz")
        if not gz.exists():
            with path.open("rb") as src, gzip.open(gz, "wb") as dst:
                shutil.copyfileobj(src, dst)
            compressed.append(str(gz))
        path.unlink(missing_ok=True)

    if settings.log_archive_dir:
        target_dir = settings.log_archive_dir / (settings.instance_id or "unknown-instance")
        target_dir.mkdir(parents=True, exist_ok=True)
        # If op_logs already live on CephFS at the same effective path
        # (MA3_OP_LOG_REALTIME_CEPHFS=1), skip the redundant copy step —
        # the gzipped files are already durable.
        same_dir = settings.op_log_dir.resolve() == target_dir.resolve()
        for gz in sorted(settings.op_log_dir.glob("*.jsonl.gz")):
            target = target_dir / gz.name
            if same_dir:
                archived.append(str(target))
                continue
            shutil.copy2(gz, target)
            archived.append(str(target))
        manifest = {
            "updated_at": _utc_now().isoformat(),
            "instance_id": settings.instance_id,
            "git_commit": settings.git_commit,
            "files": sorted(p.name for p in target_dir.glob("*.jsonl.gz")),
        }
        (target_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    cutoff_ts = _utc_now().timestamp() - settings.log_local_retention_days * 86400
    for gz in sorted(settings.op_log_dir.glob("*.jsonl.gz")):
        if gz.stat().st_mtime < cutoff_ts:
            deleted.append(str(gz))
            gz.unlink(missing_ok=True)

    return {"compressed": compressed, "archived": archived, "deleted": deleted}

