from __future__ import annotations

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

    return {
        "status": "ok" if ok else "degraded",
        "service": settings.service_name,
        "version": settings.service_version,
        "min_client_version": settings.min_client_version,
        "database_backend": settings.db_backend,
        "public_base_url": settings.public_base_url,
        "instance_id": settings.instance_id,
        "git_commit": settings.git_commit,
        "features": list(settings.feature_flags) + [
            "v2_agent_context",
            "v2_cases",
            "v2_stats",
            "v2_metrics",
            "v2_doctor",
        ],
        "checks": checks,
    }
