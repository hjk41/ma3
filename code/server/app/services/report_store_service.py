from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.models.mcp_payloads import (
    ACTIVE_REPORT_SUPPORT_MESSAGE,
    Ma3ReportPayload,
    active_report_lacks_support,
)

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
    # Same predicate as Ma3ReportPayload's model validator. MCP preflight
    # (ma3_validate, dry_run, and the write) hits that validator before any
    # database access; this call remains for direct write checks.
    if active_report_lacks_support(
        visibility=payload.visibility,
        evidence=payload.evidence,
        actions=payload.actions,
    ):
        raise HTTPException(status_code=400, detail=ACTIVE_REPORT_SUPPORT_MESSAGE)


def storage_payload(dump: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in dump.items() if key not in _TRANSPORT_KEYS}
