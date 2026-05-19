from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.storage.db import get_connection


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
