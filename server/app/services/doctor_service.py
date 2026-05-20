from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import settings
from app.storage.db import get_connection


def _parse_utc_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _safe_int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _newest_file(path: Path) -> Path | None:
    try:
        files = [p for p in path.iterdir() if p.is_file()]
    except Exception:
        return None
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def backup_doctor_block(now: datetime | None = None) -> dict:
    """Best-effort PITR backup diagnostics for /v2/doctor."""
    if os.environ.get("MA3_PG_ARCHIVE_ENABLE", "0") != "1":
        return {"mode": "legacy"}
    backup_dir_raw = os.environ.get("MA3_BACKUP_DIR") or ""
    if not backup_dir_raw:
        return {"mode": "legacy"}

    now = now or datetime.now(timezone.utc)
    backup_dir = Path(backup_dir_raw)
    instance_id = os.environ.get("MA3_INSTANCE_ID") or settings.instance_id or "unknown-instance"
    archive_timeout = _safe_int_env("MA3_PG_ARCHIVE_TIMEOUT_SECONDS", 60)
    interval_min = _safe_int_env("MA3_PG_BASEBACKUP_INTERVAL_MIN", 30)
    wal_dir = Path(os.environ.get("MA3_PG_ARCHIVE_DIR") or backup_dir / "wal" / instance_id)
    manifest_path = backup_dir / "pitr_manifest.json"

    block: dict = {
        "mode": "pitr",
        "wal_dir": str(wal_dir.relative_to(backup_dir)) if wal_dir.is_absolute() and wal_dir.is_relative_to(backup_dir) else str(wal_dir),
        "degraded": False,
    }

    newest_wal = _newest_file(wal_dir)
    if newest_wal is not None:
        last_archived = datetime.fromtimestamp(newest_wal.stat().st_mtime, tz=timezone.utc)
        block["last_archived_wal"] = newest_wal.name
        block["last_archived_at"] = last_archived.isoformat().replace("+00:00", "Z")
        block["archive_lag_seconds"] = max(0, int((now - last_archived).total_seconds()))

    base_manifest = None
    base_root = backup_dir / "basebackups" / instance_id
    try:
        manifests = list(base_root.glob("*/manifest.json"))
    except Exception:
        manifests = []
    if manifests:
        base_manifest = max(manifests, key=lambda p: p.stat().st_mtime)
        try:
            payload = json.loads(base_manifest.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        base_at = (
            _parse_utc_datetime(payload.get("created_at"))
            or _parse_utc_datetime(payload.get("timestamp"))
            or datetime.fromtimestamp(base_manifest.stat().st_mtime, tz=timezone.utc)
        )
        block["last_basebackup_at"] = base_at.isoformat().replace("+00:00", "Z")
        block["basebackup_age_seconds"] = max(0, int((now - base_at).total_seconds()))

    if manifest_path.is_file():
        try:
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest_payload = {}
        manifest_at = _parse_utc_datetime(manifest_payload.get("created_at")) or datetime.fromtimestamp(
            manifest_path.stat().st_mtime, tz=timezone.utc
        )
        block["pitr_manifest_age_seconds"] = max(0, int((now - manifest_at).total_seconds()))
        if manifest_payload.get("basebackup_instance_id"):
            block["basebackup_instance_id"] = manifest_payload.get("basebackup_instance_id")

    if block.get("archive_lag_seconds", 0) > 5 * archive_timeout:
        block["degraded"] = True
    if block.get("basebackup_age_seconds", 0) > 2 * interval_min * 60:
        block["degraded"] = True
    return block


def server_doctor() -> dict:
    checks = []
    ok = True
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1").fetchone()
        checks.append({"name": "database", "status": "ok", "backend": settings.db_backend})
    except Exception as exc:  # pragma: no cover - defensive diagnostic
        ok = False
        checks.append({"name": "database", "status": "error", "error": str(exc)})

    try:
        with get_connection() as conn:
            conn.execute("SELECT COUNT(*) AS count FROM cases").fetchone()
        checks.append({"name": "v2_schema", "status": "ok"})
    except Exception as exc:  # pragma: no cover - defensive diagnostic
        ok = False
        checks.append({"name": "v2_schema", "status": "error", "error": str(exc)})

    if settings.db_backend == "postgresql":
        try:
            with get_connection() as conn:
                records = int(conn.execute("SELECT COUNT(*) AS count FROM records").fetchone()["count"])
                indexed = int(conn.execute("SELECT COUNT(*) AS count FROM record_search_index").fetchone()["count"])
            status = "ok" if indexed >= records else "degraded"
            if status != "ok":
                ok = False
            checks.append({
                "name": "record_search_index",
                "status": status,
                "mode": settings.search_index_mode,
                "records": records,
                "indexed": indexed,
            })
        except Exception as exc:  # pragma: no cover - defensive diagnostic
            ok = False
            checks.append({"name": "record_search_index", "status": "error", "error": str(exc)})

    auth = {
        "mode": "v3",
        "principals": 0,
        "api_keys_active": 0,
        "acl_entries": 0,
        "legacy_tokens": 0,
        "admin_bypass_used_recent": 0,
    }
    try:
        with get_connection() as conn:
            auth["principals"] = int(conn.execute("SELECT COUNT(*) AS count FROM principals").fetchone()["count"])
            auth["api_keys_active"] = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS count FROM api_keys
                    WHERE revoked_at IS NULL AND (expires_at IS NULL OR expires_at > ?)
                    """,
                    (datetime.now(timezone.utc).isoformat(),),
                ).fetchone()["count"]
            )
            auth["acl_entries"] = int(conn.execute("SELECT COUNT(*) AS count FROM library_acl").fetchone()["count"])
            auth["legacy_tokens"] = int(conn.execute("SELECT COUNT(*) AS count FROM tokens").fetchone()["count"])
            since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            auth["admin_bypass_used_recent"] = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS count FROM auth_audit_log
                    WHERE action = 'principal.assume_admin' AND created_at >= ?
                    """,
                    (since,),
                ).fetchone()["count"]
            )
        checks.append({"name": "auth_v3_schema", "status": "ok"})
    except Exception as exc:  # pragma: no cover - defensive diagnostic
        ok = False
        checks.append({"name": "auth_v3_schema", "status": "error", "error": str(exc)})

    backup = backup_doctor_block()
    if backup.get("degraded"):
        ok = False

    return {
        "status": "ok" if ok else "degraded",
        "service": settings.service_name,
        "version": settings.service_version,
        "min_client_version": settings.min_client_version,
        "database_backend": settings.db_backend,
        "public_base_url": settings.public_base_url,
        "instance_id": settings.instance_id,
        "git_commit": settings.git_commit,
        "job_name": settings.job_name,
        "deployed_at": settings.started_at,
        "auth_mode": "v3",
        "auth": auth,
        "backup": backup,
        "features": list(settings.feature_flags) + [
            "v2_agent_context",
            "v2_cases",
            "v2_stats",
            "v2_metrics",
            "v2_doctor",
            "remote_mcp",
        ],
        "mcp": {"endpoint": "/mcp", "transport": "streamable-http-jsonrpc", "tool_schema_version": "ma3.mcp.v1"},
        "checks": checks,
    }
