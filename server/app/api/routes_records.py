from fastapi import APIRouter, Depends, HTTPException, Header, Query
from typing import Optional

from app.core.security import (
    require_write_library_id,
    require_admin_role,
    resolve_optional_token,
    ResolvedToken,
    _extract_raw,
    _is_admin_key,
)
from app.models.record import Record, RecordCreate, RecordUpdate, PromoteRequest, RejectRequest
from app.services.library_service import accessible_library_ids
from app.services.record_service import (
    create_record,
    get_record,
    update_record,
    promote_record,
    reject_record,
)
from app.storage.repositories import RecordRepository, is_ancestor_or_self


router = APIRouter(prefix="/records", tags=["records"])


def _check_admin_access_to_record(record: Record, admin_library_id: str | None) -> None:
    """Raise 403 if an admin-role token doesn't cover the record's library.

    admin_library_id is None for global admin (full access) or the token's
    library_id for a library-scoped admin token.
    """
    if admin_library_id is None:
        return  # global admin — full access
    record_lib = record.library_id or ""
    if not record_lib or not is_ancestor_or_self(admin_library_id, record_lib):
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
    token: ResolvedToken | None = Depends(resolve_optional_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> dict:
    """Browse accessible records with pagination.

    Returns ``{"records": [...], "total": N, "offset": N, "limit": N}``.

    When called with a library token and ``status=active`` (the default), the
    caller's own library's drafts are always included alongside active records —
    so a library admin can see their pending queue without needing ``status=all``.
    Use ``status=all`` to also include invalid records.
    """
    raw = _extract_raw(x_api_key, authorization)
    is_admin = bool(raw and _is_admin_key(raw))
    lib_ids = accessible_library_ids(token)
    status_filter = None if status == "all" else status
    # When filtering by active status, always surface the caller's own library's
    # drafts so they are visible without needing an explicit status=all.
    own_library_id = token.library_id if (token and status_filter == "active") else None
    records, total = RecordRepository().list_page(
        library_ids=lib_ids,
        status=status_filter,
        offset=offset,
        limit=limit,
        is_admin=is_admin,
        own_library_id=own_library_id,
    )
    return {"records": [r.model_dump() for r in records], "total": total, "offset": offset, "limit": limit}



@router.post("", response_model=Record)
def post_record(
    payload: RecordCreate,
    library_id: str | None = Depends(require_write_library_id),
) -> Record:
    return create_record(payload, library_id=library_id)


@router.get("/{record_id}", response_model=Record)
def get_record_by_id(
    record_id: str,
    token: ResolvedToken | None = Depends(resolve_optional_token),
) -> Record:
    record = get_record(record_id, accessible_library_ids(token))
    if record is None:
        raise HTTPException(status_code=404, detail="record not found")
    return record


@router.patch("/{record_id}", response_model=Record)
def patch_record(
    record_id: str,
    payload: RecordUpdate,
    library_id: str | None = Depends(require_write_library_id),
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
    admin_library_id: str | None = Depends(require_admin_role),
) -> Record:
    """Approve a draft record: moves it to active status.

    Requires an admin-role token for this record's library, or the global admin key.
    Writers cannot promote their own drafts — this enforces the review workflow.
    """
    record = RecordRepository().get(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="record not found")
    _check_admin_access_to_record(record, admin_library_id)
    try:
        return promote_record(record, review_note=body.review_note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/{record_id}/reject", response_model=Record)
def reject_record_endpoint(
    record_id: str,
    body: RejectRequest = RejectRequest(),
    admin_library_id: str | None = Depends(require_admin_role),
) -> Record:
    """Reject a draft (or active) record: marks it invalid so it no longer appears in search.

    Requires an admin-role token for this record's library, or the global admin key.
    """
    record = RecordRepository().get(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="record not found")
    _check_admin_access_to_record(record, admin_library_id)
    try:
        return reject_record(record, review_note=body.review_note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
