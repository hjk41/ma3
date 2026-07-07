"""Library write buffer: status resolution, publish, and author-only visibility (design/16)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException

from app.core.security import McpAuthContext
from app.services.storage_quota_service import assert_personal_library_write_allowed
from app.storage import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def compute_publish_at(*, buffer_hours: int, from_time: datetime | None = None) -> str:
    base = from_time or _utc_now()
    return _iso(base + timedelta(hours=buffer_hours))


def resolve_report_status(
    *,
    visibility: str,
    report_kind: str,
    library_id: str,
    is_maintainer: bool,
    is_admin_bypass: bool,
) -> tuple[str, str | None]:
    """Return (status, publish_at). publish_at set only when status=buffered."""
    if visibility == "draft":
        return "draft", None
    if report_kind in ("verify", "refute"):
        return "active", None
    if is_maintainer or is_admin_bypass:
        return "active", None
    hours = db.get_library_write_buffer_hours(library_id)
    if hours <= 0:
        return "active", None
    if report_kind in ("new", "supplement"):
        return "buffered", compute_publish_at(buffer_hours=hours)
    return "active", None


def buffer_response_fields(record: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if record.get("status") != "buffered":
        return out
    publish_at = record.get("publish_at")
    out["publish_at"] = publish_at
    if publish_at:
        try:
            due = datetime.fromisoformat(str(publish_at))
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            remaining = (due - _utc_now()).total_seconds() / 3600.0
            out["buffer_hours_remaining"] = max(0.0, round(remaining, 2))
        except ValueError:
            out["buffer_hours_remaining"] = None
    out["readable_by"] = ["author"]
    return out


def publish_record_for_owner(*, record_id: str, auth: McpAuthContext) -> dict[str, Any]:
    if auth.principal.kind == "anonymous":
        raise HTTPException(status_code=403, detail="authentication required")
    record = db.get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="record not found")
    if record.get("status") != "buffered":
        if record.get("status") == "active":
            return {"record_id": record_id, "status": "active", "published": False}
        raise HTTPException(status_code=400, detail="record is not buffered")
    if not db.is_record_owner(record_id, auth.principal.principal_id):
        if str(record["library_id"]) not in auth.readable_library_ids:
            raise HTTPException(status_code=404, detail="record not found")
        raise HTTPException(status_code=403, detail="only the record owner may publish")
    updated = db.publish_buffered_record(record_id)
    if not updated:
        raise HTTPException(status_code=404, detail="record not found")
    payload = updated.get("payload") or {}
    based_on = payload.get("based_on_record_ids") if isinstance(payload, dict) else []
    if isinstance(based_on, list) and based_on:
        db.insert_record_relations(
            source_id=record_id,
            based_on_record_ids=[str(rid) for rid in based_on],
            relation_type=payload.get("relation_type") if isinstance(payload, dict) else None,
        )
    return {"record_id": record_id, "status": "active", "published": True}


def patch_buffered_record_for_owner(
    *,
    record_id: str,
    auth: McpAuthContext,
    problem: str,
    outcome: str,
    result_summary: str,
) -> dict[str, Any]:
    if auth.principal.kind == "anonymous":
        raise HTTPException(status_code=403, detail="authentication required")
    record = db.get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="record not found")
    if record.get("status") != "buffered":
        raise HTTPException(status_code=400, detail="only buffered records may be patched")
    if not db.is_record_owner(record_id, auth.principal.principal_id):
        if str(record["library_id"]) not in auth.readable_library_ids:
            raise HTTPException(status_code=404, detail="record not found")
        raise HTTPException(status_code=403, detail="only the record owner may edit")
    library_id = str(record["library_id"])
    hours = db.get_library_write_buffer_hours(library_id)
    publish_at = compute_publish_at(buffer_hours=hours) if hours > 0 else None
    payload = dict(record.get("payload") or {})
    payload["problem"] = problem
    payload["outcome"] = outcome
    payload["result_summary"] = result_summary
    assert_personal_library_write_allowed(
        library_id=library_id,
        principal_id=auth.principal.principal_id,
        problem=problem,
        outcome=outcome,
        result_summary=result_summary,
        payload=payload,
        exclude_record_id=record_id,
    )
    updated = db.update_buffered_record(
        record_id,
        problem=problem,
        outcome=outcome,
        result_summary=result_summary,
        payload=payload,
        publish_at=publish_at,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="record not found")
    if hours <= 0:
        published = db.publish_buffered_record(record_id)
        if not published:
            raise HTTPException(status_code=404, detail="record not found")
        return {
            "record_id": record_id,
            "status": "active",
            "publish_at": None,
            "patched": True,
            "published": True,
        }
    return {
        "record_id": record_id,
        "status": "buffered",
        "publish_at": publish_at,
        "patched": True,
    }


def can_read_record(
    record: dict[str, Any],
    *,
    principal_id: str | None,
    is_admin: bool,
    readable_library_ids: set[str],
) -> bool:
    library_id = str(record.get("library_id") or "")
    if library_id not in readable_library_ids and not is_admin:
        return False
    status = record.get("status")
    if status == "active":
        return True
    if status == "buffered":
        if is_admin:
            return True
        if principal_id and db.is_record_owner(str(record["id"]), principal_id):
            return True
        return False
    if status == "trashed":
        if is_admin:
            return True
        if principal_id and record.get("created_by") == principal_id:
            return True
        return False
    if is_admin:
        return True
    if principal_id and record.get("created_by") == principal_id:
        return True
    return False


def is_library_settings_editor(library_id: str, principal_id: str, *, is_admin: bool) -> bool:
    if is_admin:
        return True
    from app.services.entitlement_service import can_maintain_library

    return can_maintain_library(principal_id, library_id)
