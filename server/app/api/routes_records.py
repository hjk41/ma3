from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from app.core.security import (
    ResolvedPrincipal,
    current_principal,
    effective_libraries,
    v3_write_library,
)
from app.models.record import Record, RecordCreate, RecordUpdate, PromoteRequest, RejectRequest
from app.services.library_service import effective_library_ids
from app.services.record_service import (
    create_record,
    delete_record,
    get_record,
    update_record,
    promote_record,
    reject_record,
)
from app.storage.repositories import RecordRepository


router = APIRouter(prefix="/records", tags=["records"])


def _check_admin_access_to_record(record: Record, principal: ResolvedPrincipal) -> None:
    if principal.is_admin_bypass:
        return
    if principal.kind == "anonymous":
        raise HTTPException(status_code=401, detail="admin credentials required")
    record_lib = record.library_id or ""
    if not record_lib or effective_libraries(principal, role_at_least="admin").get(record_lib) != "admin":
        raise HTTPException(
            status_code=403,
            detail="admin token does not cover this record's library",
        )


def _require_write_access(record: Record, library_id: str | None) -> None:
    """Raise 403 if the caller's library_id doesn't match the record's library."""
    if library_id is not None and record.library_id != library_id:
        raise HTTPException(status_code=403, detail="no write access to this record's library")


@router.get("", response_model=dict)
def list_records(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default="active", description="Filter by status: active, draft, invalid, or 'all'"),
    principal: ResolvedPrincipal = Depends(current_principal),
) -> dict:
    """Browse accessible records with pagination."""
    lib_ids = effective_library_ids(principal)
    status_filter = None if status == "all" else status
    own_library_id = principal.library_id if (principal.library_id and status_filter == "active") else None
    records, total = RecordRepository().list_page(
        library_ids=lib_ids,
        status=status_filter,
        offset=offset,
        limit=limit,
        is_admin=principal.is_admin_bypass,
        own_library_id=own_library_id,
    )
    return {"records": [r.model_dump() for r in records], "total": total, "offset": offset, "limit": limit}


@router.post("", response_model=Record)
def post_record(
    payload: RecordCreate,
    library_id: str | None = Depends(v3_write_library),
) -> Record:
    return create_record(payload, library_id=library_id)


@router.get("/{record_id}", response_model=Record)
def get_record_by_id(
    record_id: str,
    principal: ResolvedPrincipal = Depends(current_principal),
) -> Record:
    record = get_record(record_id, effective_library_ids(principal))
    if record is None:
        raise HTTPException(status_code=404, detail="record not found")
    return record


@router.patch("/{record_id}", response_model=Record)
def patch_record(
    record_id: str,
    payload: RecordUpdate,
    library_id: str | None = Depends(v3_write_library),
) -> Record:
    """Update editable fields on an existing record. Status transitions use dedicated endpoints."""
    record = RecordRepository().get(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="record not found")
    _require_write_access(record, library_id)
    return update_record(record, payload)


@router.patch("/{record_id}/promote", response_model=Record)
def promote_record_endpoint(
    record_id: str,
    body: PromoteRequest = PromoteRequest(),
    principal: ResolvedPrincipal = Depends(current_principal),
) -> Record:
    """Approve a draft record: moves it to active status."""
    record = RecordRepository().get(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="record not found")
    _check_admin_access_to_record(record, principal)
    try:
        return promote_record(record, review_note=body.review_note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/{record_id}/reject", response_model=Record)
def reject_record_endpoint(
    record_id: str,
    body: RejectRequest = RejectRequest(),
    principal: ResolvedPrincipal = Depends(current_principal),
) -> Record:
    """Reject a draft (or active) record: marks it invalid so it no longer appears in search."""
    record = RecordRepository().get(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="record not found")
    _check_admin_access_to_record(record, principal)
    try:
        return reject_record(record, review_note=body.review_note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{record_id}", response_model=dict)
def delete_record_endpoint(
    record_id: str,
    principal: ResolvedPrincipal = Depends(current_principal),
) -> dict:
    """Delete a record permanently."""
    record = RecordRepository().get(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="record not found")
    _check_admin_access_to_record(record, principal)
    deleted = delete_record(record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="record not found")
    return {"ok": True, "record_id": record_id}
