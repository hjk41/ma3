from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import ResolvedPrincipal, current_principal, v3_write_library
from app.models.v2 import Case, CaseUpdate, V2CaseRecordGroup
from app.services.case_service import assert_case_writeable, update_case
from app.services.library_service import effective_library_ids
from app.storage.v2_repositories import CaseRepository, V2GraphRepository, V2RecordRepository, filter_cases_by_topic


router = APIRouter(prefix="/v2/cases", tags=["v2-cases"])


@router.get("", response_model=list[Case])
def list_cases(
    state: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    topic_kind: str | None = Query(default=None, pattern="^(product|component|tag|problem_family)$"),
    topic: str | None = Query(default=None),
    principal: ResolvedPrincipal = Depends(current_principal),
) -> list[Case]:
    lib_ids = effective_library_ids(principal)
    if topic_kind and topic:
        candidates = CaseRepository().list_accessible(
            lib_ids,
            state=state,
            limit=10000,
            offset=0,
        )
        return filter_cases_by_topic(
            candidates,
            topic_kind=topic_kind,
            topic=topic,
            offset=offset,
            limit=limit,
        )
    return CaseRepository().list_accessible(
        lib_ids,
        state=state,
        limit=limit,
        offset=offset,
    )


@router.get("/{case_id}", response_model=V2CaseRecordGroup)
def get_case(
    case_id: str,
    principal: ResolvedPrincipal = Depends(current_principal),
) -> V2CaseRecordGroup:
    lib_ids = effective_library_ids(principal)
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
    library_id: str | None = Depends(v3_write_library),
) -> Case:
    case = CaseRepository().get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    assert_case_writeable(case, library_id)
    return update_case(case, payload)
