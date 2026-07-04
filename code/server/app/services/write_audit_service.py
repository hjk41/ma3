"""Write confirmation, audit log, and owner delete/restore (ADR-013 / design-10)."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.core.config import settings
from app.core.security import McpAuthContext
from app.models.mcp_payloads import Ma3ReportPayload
from app.storage import db

_VALID_REPORT_KINDS = frozenset({"verify", "refute", "supplement", "new"})
_VALID_CONFIRMATIONS = frozenset({"user_confirmed", "agent_judged", "verify_direct"})
_LEGACY_DEFAULT_VIAS = frozenset({"dev_api_key", "writer_api_key", "maintainer_api_key"})


class ReportWritePlan:
    __slots__ = ("library_id", "report_kind", "confirmation", "selection_reason")

    def __init__(
        self,
        *,
        library_id: str,
        report_kind: str,
        confirmation: str,
        selection_reason: str,
    ) -> None:
        self.library_id = library_id
        self.report_kind = report_kind
        self.confirmation = confirmation
        self.selection_reason = selection_reason


def resolve_report_write_plan(payload: Ma3ReportPayload, auth: McpAuthContext) -> ReportWritePlan:
    """Resolve target library and audit metadata for ma3_report."""
    report_kind = payload.report_kind or "new"

    if report_kind not in _VALID_REPORT_KINDS:
        raise HTTPException(status_code=400, detail=f"unsupported report_kind: {report_kind}")

    if report_kind in ("verify", "refute"):
        if not payload.target_record_id:
            raise HTTPException(status_code=400, detail="target_record_id required for verify/refute")
        target = db.get_record(payload.target_record_id)
        if not target or target["library_id"] not in auth.readable_library_ids:
            raise HTTPException(status_code=404, detail="target record not found")
        library_id = str(target["library_id"])
        if library_id not in auth.writable_library_ids:
            _raise_library_not_writable(library_id, auth)
        return ReportWritePlan(
            library_id=library_id,
            report_kind=report_kind,
            confirmation="verify_direct",
            selection_reason="verify_target_library",
        )

    confirmation = payload.confirmation or "agent_judged"
    if confirmation not in _VALID_CONFIRMATIONS or confirmation == "verify_direct":
        raise HTTPException(status_code=400, detail=f"invalid confirmation: {confirmation}")

    if payload.library_id:
        library_id = payload.library_id
        selection_reason = "explicit_library_id"
        if library_id not in auth.writable_library_ids:
            _raise_library_not_writable(library_id, auth)
    elif _uses_legacy_default_path(auth):
        library_id = _legacy_default_writable_library(auth)
        selection_reason = "legacy_default_library"
    else:
        library_id = _default_personal_writable_library(auth)
        selection_reason = "default_owned_personal_library"

    return ReportWritePlan(
        library_id=library_id,
        report_kind=report_kind,
        confirmation=confirmation,
        selection_reason=selection_reason,
    )


def _uses_legacy_default_path(auth: McpAuthContext) -> bool:
    """Dev bypass and env-configured writer/maintainer keys keep lib_default default."""
    if auth.principal.is_admin_bypass:
        return True
    return auth.principal.via in _LEGACY_DEFAULT_VIAS


def _legacy_default_writable_library(auth: McpAuthContext) -> str:
    writable = auth.writable_library_ids
    if not writable:
        raise HTTPException(status_code=403, detail="writer access required")
    if settings.default_library_id in writable:
        return settings.default_library_id
    return sorted(writable)[0]


def _default_personal_writable_library(auth: McpAuthContext) -> str:
    libs = db.list_libraries(auth.writable_library_ids)
    principal_id = auth.principal.principal_id
    personal = [
        lib
        for lib in libs
        if lib.get("kind") == "personal" and lib.get("owner_principal_id") == principal_id
    ]
    if len(personal) == 1:
        return str(personal[0]["library_id"])
    if len(personal) == 0:
        _raise_library_selection_required(
            error="library_id_required",
            reason="no writable personal library found; pass library_id explicitly",
            writable_libraries=libs,
        )
    _raise_library_selection_required(
        error="ambiguous_library_id",
        reason="multiple writable personal libraries found; pass library_id explicitly",
        writable_libraries=libs,
    )


def _format_library_choice(lib: dict[str, Any]) -> str:
    return f'{lib["library_id"]} ("{lib["name"]}", {lib.get("kind", "custom")})'


def _library_selection_error_message(
    *,
    error: str,
    reason: str,
    writable_libraries: list[dict[str, Any]],
) -> str:
    if writable_libraries:
        choices = ", ".join(_format_library_choice(lib) for lib in writable_libraries)
        return f"{error}: {reason}. Writable libraries: {choices}."
    return f"{error}: {reason}."


def _raise_library_selection_required(
    *,
    error: str,
    reason: str,
    writable_libraries: list[dict[str, Any]],
) -> None:
    message = _library_selection_error_message(
        error=error,
        reason=reason,
        writable_libraries=writable_libraries,
    )
    raise HTTPException(
        status_code=400,
        detail={
            "error": error,
            "reason": reason,
            "message": message,
            "writable_libraries": writable_libraries,
        },
    )


def _raise_library_not_writable(library_id: str, auth: McpAuthContext) -> None:
    writable_libraries = db.list_libraries(auth.writable_library_ids)
    choices = ", ".join(_format_library_choice(lib) for lib in writable_libraries) or "(none)"
    message = (
        f"library_not_writable: {library_id} is not writable with this key. "
        f"Writable libraries: {choices}."
    )
    raise HTTPException(
        status_code=403,
        detail={
            "error": "library_not_writable",
            "library_id": library_id,
            "message": message,
            "writable_libraries": writable_libraries,
        },
    )


def append_write_audit(
    *,
    record_id: str,
    library_id: str,
    auth: McpAuthContext,
    report_kind: str,
    confirmation: str,
) -> None:
    if auth.principal.kind == "anonymous":
        return
    db.append_write_audit_log(
        record_id=record_id,
        library_id=library_id,
        principal_id=auth.principal.principal_id,
        api_key_id=auth.api_key_id or auth.principal.principal_id,
        report_kind=report_kind,
        confirmation=confirmation,
    )


def format_my_writes(rows: list[dict[str, Any]], *, key_prefix: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        entry = {
            "created_at": row["created_at"],
            "record_id": row["record_id"],
            "library_id": row["library_id"],
            "library_name": row.get("library_name") or row["library_id"],
            "report_kind": row["report_kind"],
            "confirmation": row["confirmation"],
            "status": row.get("record_status") or "active",
            "publish_at": row.get("publish_at"),
        }
        if key_prefix:
            entry["key_prefix"] = key_prefix
        out.append(entry)
    return out


def delete_record_for_owner(*, record_id: str, auth: McpAuthContext) -> dict[str, Any]:
    if auth.principal.kind == "anonymous":
        raise HTTPException(status_code=403, detail="authentication required")

    record = db.get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="record not found")

    principal_id = auth.principal.principal_id
    is_owner = db.is_record_owner(record_id, principal_id)
    if not is_owner:
        if str(record["library_id"]) not in auth.readable_library_ids:
            raise HTTPException(status_code=404, detail="record not found")
        raise HTTPException(status_code=403, detail="only the record owner may delete")

    library_id = str(record["library_id"])
    protected, _retention = db.library_deletion_protection(library_id)

    if protected:
        db.soft_delete_record(record_id)
        return {"deleted": True, "mode": "soft", "record_id": record_id}

    db.hard_delete_record(record_id, deleted_by=principal_id)
    return {"deleted": True, "mode": "hard", "record_id": record_id}


def restore_record_for_caller(*, record_id: str, auth: McpAuthContext) -> dict[str, Any]:
    if auth.principal.kind == "anonymous":
        raise HTTPException(status_code=403, detail="authentication required")

    record = db.get_record(record_id)
    if not record:
        tomb = db.get_record_deletion(record_id)
        if tomb and str(tomb["library_id"]) not in auth.readable_library_ids:
            raise HTTPException(status_code=404, detail="record not found")
        if tomb:
            raise HTTPException(status_code=400, detail="already_purged")
        raise HTTPException(status_code=404, detail="record not found")

    library_id = str(record["library_id"])
    principal_id = auth.principal.principal_id
    is_owner = db.is_record_owner(record_id, principal_id)
    is_maintainer = auth.principal.is_admin_bypass or library_id in auth.maintainer_library_ids

    if not (is_owner or is_maintainer):
        if library_id not in auth.readable_library_ids:
            raise HTTPException(status_code=404, detail="record not found")
        if record.get("status") != "trashed":
            raise HTTPException(status_code=400, detail="record is not trashed")
        raise HTTPException(status_code=403, detail="restore requires owner or maintainer")

    if record.get("status") != "trashed":
        raise HTTPException(status_code=400, detail="record is not trashed")

    protected, _retention = db.library_deletion_protection(library_id)
    if not protected:
        raise HTTPException(status_code=400, detail="library does not support restore")

    if db.is_trash_restore_expired(record_id):
        db.purge_expired_trashed_record(record_id, deleted_by="system:retention")
        raise HTTPException(status_code=400, detail="already_purged")

    db.restore_trashed_record(record_id)
    return {"restored": True, "record_id": record_id}
