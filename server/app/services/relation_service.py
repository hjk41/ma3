from fastapi import HTTPException

from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.models.relation import RecordRelation, RecordRelationCreate
from app.services.redaction import redact_value
from app.storage.repositories import RecordRepository, RelationRepository


def create_relation(payload: RecordRelationCreate) -> RecordRelation:
    record_repo = RecordRepository()
    if record_repo.get(payload.from_record_id) is None:
        raise HTTPException(status_code=404, detail="from_record not found")
    if record_repo.get(payload.to_record_id) is None:
        raise HTTPException(status_code=404, detail="to_record not found")

    sanitized = RecordRelationCreate.model_validate(redact_value(payload.model_dump()))
    relation = RecordRelation(
        relation_id=new_id("rel"),
        created_at=utc_now_iso(),
        **sanitized.model_dump(),
    )
    RelationRepository().insert(relation)
    return relation


def list_relations_for_record(record_id: str) -> list[RecordRelation]:
    return RelationRepository().list_by_record(record_id)
