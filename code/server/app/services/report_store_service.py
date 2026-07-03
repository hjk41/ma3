from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.models.mcp_payloads import Ma3ReportPayload

_TRANSPORT_KEYS = frozenset(
    {
        "dry_run",
        "include_full_json",
        "client_version",
        "visibility",
        "redaction_mode",
        "case_assignment_mode",
        "idempotency_key",
    }
)

_ALLOWED_RELATION_TYPES = frozenset({"derived_from", "supersedes", "related"})


def validate_report_write(payload: Ma3ReportPayload, *, is_maintainer: bool) -> None:
    rel = payload.relation_type or "derived_from"
    if rel not in _ALLOWED_RELATION_TYPES:
        raise HTTPException(status_code=400, detail=f"unsupported relation_type: {rel}")
    if rel == "supersedes" and not is_maintainer:
        raise HTTPException(status_code=403, detail="supersedes relations require maintainer access")
    if payload.redaction_mode == "none" and not is_maintainer:
        raise HTTPException(status_code=403, detail="redaction_mode=none requires maintainer access")
    status = "draft" if payload.visibility == "draft" else "active"
    if status == "active" and not payload.evidence and not payload.actions:
        raise HTTPException(
            status_code=400,
            detail="active records require at least one evidence item or action; use visibility=draft otherwise",
        )


def storage_payload(dump: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in dump.items() if key not in _TRANSPORT_KEYS}
