from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal

from app.models.agent import AgentAction
from app.models.common import EnvironmentFingerprint, EvidenceItem, TargetRef, VersionInfo
from app.models.record import Record
from app.models.relation import RecordRelation


class Case(BaseModel):
    case_id: str
    library_id: str | None = None
    title: str
    summary: str = ""
    problem_family: str = ""
    target: TargetRef
    state: str = "open"
    canonical_record_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str
    last_record_at: str | None = None
    payload: dict = Field(default_factory=dict)


class CaseUpdate(BaseModel):
    title: str | None = None
    summary: str | None = None
    state: str | None = None
    canonical_record_id: str | None = None
    tags: list[str] | None = None


class CaseAssignment(BaseModel):
    result: str
    case: Case | None = None
    confidence: float = 0.0
    candidates: list[dict] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    overridden: bool = False


class V2CaseRecordGroup(BaseModel):
    case: Case
    records: list[Record] = Field(default_factory=list)
    relations: list[RecordRelation] = Field(default_factory=list)
    match_score: float = 0.0
    why_matched: list[str] = Field(default_factory=list)


class V2SearchExplain(BaseModel):
    query_hash: str
    ranking_config_version: str
    candidate_count: int = 0
    candidate_pool_limit: int = 0
    returned_record_count: int = 0
    returned_case_count: int = 0
    full_scan: bool = False
    stages: list[dict] = Field(default_factory=list)
    score_breakdown: list[dict] = Field(default_factory=list)
    debug_candidates: list[dict] = Field(default_factory=list)


class V2AgentContextRequest(BaseModel):
    problem: str
    task_type: str
    goal: str
    target: TargetRef
    environment: EnvironmentFingerprint | None = None
    versions: VersionInfo | None = None
    observations: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    max_cases: int = Field(default=3, ge=1, le=20)
    max_records_per_case: int = Field(default=3, ge=1, le=10)
    include_explain: bool = False


class V2AgentContextResponse(BaseModel):
    cases: list[V2CaseRecordGroup] = Field(default_factory=list)
    ungrouped_records: list[Record] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    explain: V2SearchExplain | None = None
    server: dict = Field(default_factory=dict)


class V2AgentReportRequest(BaseModel):
    problem: str
    task_type: str
    goal: str
    target: TargetRef
    environment: EnvironmentFingerprint | None = None
    versions: VersionInfo | None = None
    observations: list[str] = Field(default_factory=list)
    actions: list[AgentAction] = Field(default_factory=list)
    outcome: str
    result_summary: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    based_on_record_ids: list[str] = Field(default_factory=list)
    relation_type: str | None = None
    applicable_if: list[str] = Field(default_factory=list)
    not_applicable_if: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    case_id: str | None = None
    case_assignment_mode: str = "auto"
    dry_run: bool = False
    redaction_mode: Literal["auto", "none"] = "auto"


class V2AgentReportResponse(BaseModel):
    persisted: bool
    record: Record
    case_assignment: CaseAssignment
    relations_created: list[RecordRelation] = Field(default_factory=list)
    feedback_created: list[dict] = Field(default_factory=list)
    requires_manual_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)


class SearchFeedbackRequest(BaseModel):
    query_id: str | None = None
    query_hash: str | None = None
    record_id: str | None = None
    case_id: str | None = None
    judgment: str
    expected_record_id: str | None = None
    comment: str | None = None


class SearchFeedbackResponse(BaseModel):
    feedback_id: str
    persisted: bool = True


class TopicBucket(BaseModel):
    name: str
    count: int
    kind: str


class TopicsResponse(BaseModel):
    products: list[TopicBucket] = Field(default_factory=list)
    components: list[TopicBucket] = Field(default_factory=list)
    tags: list[TopicBucket] = Field(default_factory=list)
    problem_families: list[TopicBucket] = Field(default_factory=list)
    totals: dict = Field(default_factory=dict)
