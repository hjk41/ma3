from fastapi import APIRouter, Depends

from app.core.security import v3_write_library
from app.models.relation import RecordRelation, RecordRelationCreate
from app.services.relation_service import create_relation, list_relations_for_record


router = APIRouter(prefix="/relations", tags=["relations"])


@router.post("", response_model=RecordRelation)
def post_relation(
    payload: RecordRelationCreate,
    _: str | None = Depends(v3_write_library),
) -> RecordRelation:
    return create_relation(payload)


@router.get("/record/{record_id}", response_model=list[RecordRelation])
def get_relations_by_record(record_id: str) -> list[RecordRelation]:
    return list_relations_for_record(record_id)
