from __future__ import annotations

from typing import Any, Literal

from fastapi import HTTPException, Request

from app.auth.session import resolve_session_user
from app.core.config import settings
from app.core.security import McpAuthContext
from app.storage import db

VoteAction = Literal["up", "down", "clear"]


def _vote_to_int(vote: VoteAction) -> int:
    return 1 if vote == "up" else -1


def resolve_mcp_feedback_principal(auth: McpAuthContext) -> str:
    if auth.principal.kind == "anonymous":
        raise HTTPException(status_code=403, detail="authentication required for feedback")
    return auth.principal.principal_id


def resolve_ui_feedback_principal(request: Request) -> str:
    if settings.authing_configured:
        user = resolve_session_user(request)
        if user is None:
            raise HTTPException(status_code=401, detail="authentication required")
        return user.principal_id
    session_id = request.cookies.get("ma3_ui_session")
    if not session_id:
        raise HTTPException(status_code=401, detail="authentication required for feedback")
    return f"ui:session:{session_id[:64]}"


def _ensure_record_feedback_target(record: dict[str, Any], readable_library_ids: set[str] | None) -> None:
    if record.get("status") != "active":
        raise HTTPException(status_code=400, detail="feedback only allowed on active records")
    if readable_library_ids is not None and record.get("library_id") not in readable_library_ids:
        raise HTTPException(status_code=403, detail="record not readable")


def apply_record_feedback(
    *,
    record_id: str,
    principal_id: str,
    vote: VoteAction,
    readable_library_ids: set[str] | None = None,
) -> dict[str, Any]:
    record = db.get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="record not found")
    _ensure_record_feedback_target(record, readable_library_ids)

    if vote == "clear":
        db.clear_record_feedback(record_id, principal_id)
    else:
        db.set_record_feedback(record_id, principal_id, _vote_to_int(vote))

    summary = db.get_feedback_summaries([record_id], principal_id=principal_id)[record_id]
    return {
        "record_id": record_id,
        "feedback": summary,
    }


def attach_feedback_to_records(
    records: list[dict[str, Any]],
    *,
    principal_id: str | None = None,
) -> list[dict[str, Any]]:
    record_ids = [str(r["id"]) for r in records if r.get("id")]
    if not record_ids:
        return records
    summaries = db.get_feedback_summaries(record_ids, principal_id=principal_id)
    enriched: list[dict[str, Any]] = []
    for record in records:
        row = dict(record)
        rid = row.get("id")
        if rid:
            row["feedback"] = summaries.get(str(rid), {"up": 0, "down": 0})
        enriched.append(row)
    return enriched
