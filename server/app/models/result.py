from pydantic import BaseModel, Field

from app.models.record import Record
from app.models.relation import RecordRelation


class SearchMatch(BaseModel):
    record: Record
    match_score: float
    why_matched: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    relations: list[RecordRelation] = Field(default_factory=list)


class SearchResponse(BaseModel):
    primary_records: list[SearchMatch] = Field(default_factory=list)
    contrasting_records: list[SearchMatch] = Field(default_factory=list)
