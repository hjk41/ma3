from fastapi import APIRouter, Depends

from app.core.security import require_write_library_id
from app.models.relation import RecordRelation, RecordRelationCreate
from app.services.relation_service import create_relation, list_relations_for_record


router = APIRouter(prefix="/relations", tags=["relations"])


@router.post("", response_model=RecordRelation)
def post_relation(
    payload: RecordRelationCreate,
    _: str | None = Depends(require_write_library_id),
) -> RecordRelation:
    return create_relation(payload)


@router.get("/record/{record_id}", response_model=list[RecordRelation])
def get_relations_by_record(record_id: str) -> list[RecordRelation]:
    return list_relations_for_record(record_id)
