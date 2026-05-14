from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.core.security import _extract_raw, _is_admin_key, require_write_library_id, resolve_optional_token, ResolvedToken
from app.models.v2 import Case, CaseUpdate, V2CaseRecordGroup
from app.services.case_service import assert_case_writeable, update_case
from app.services.library_service import accessible_library_ids
from app.storage.v2_repositories import CaseRepository, V2GraphRepository, V2RecordRepository


router = APIRouter(prefix="/v2/cases", tags=["v2-cases"])


def _admin(x_api_key: str | None, authorization: str | None) -> bool:
    raw = _extract_raw(x_api_key, authorization)
    return bool(raw and _is_admin_key(raw))


@router.get("", response_model=list[Case])
def list_cases(
    state: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    token: ResolvedToken | None = Depends(resolve_optional_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> list[Case]:
    return CaseRepository().list_accessible(
        accessible_library_ids(token, is_admin=_admin(x_api_key, authorization)),
        state=state,
        limit=limit,
        offset=offset,
    )


@router.get("/{case_id}", response_model=V2CaseRecordGroup)
def get_case(
    case_id: str,
    token: ResolvedToken | None = Depends(resolve_optional_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> V2CaseRecordGroup:
    lib_ids = accessible_library_ids(token, is_admin=_admin(x_api_key, authorization))
    cases = CaseRepository().list_by_ids_accessible({case_id}, lib_ids)
    if not cases:
        raise HTTPException(status_code=404, detail="case not found")
    records = V2RecordRepository().records_for_cases({case_id}, limit_per_case=100).get(case_id, [])
    relations_by_record = V2GraphRepository().relations_by_record_ids({r.record_id for r in records})
    relations = []
    for items in relations_by_record.values():
        relations.extend(items)
    return V2CaseRecordGroup(case=cases[0], records=records, relations=relations)


@router.patch("/{case_id}", response_model=Case)
def patch_case(
    case_id: str,
    payload: CaseUpdate,
    library_id: str | None = Depends(require_write_library_id),
) -> Case:
    case = CaseRepository().get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    assert_case_writeable(case, library_id)
    return update_case(case, payload)

