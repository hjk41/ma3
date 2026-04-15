from pydantic import BaseModel

from app.models.enums import RelationType


class RecordRelationCreate(BaseModel):
    from_record_id: str
    to_record_id: str
    relation_type: RelationType
    summary: str | None = None


class RecordRelation(RecordRelationCreate):
    relation_id: str
    created_at: str
