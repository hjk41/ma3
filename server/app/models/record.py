from pydantic import BaseModel, Field

from app.models.common import (
    EnvironmentFingerprint,
    EvidenceItem,
    ResultSummary,
    StepItem,
    TargetRef,
    VersionInfo,
)
from app.models.enums import (
    ExecutionMode,
    RecordStatus,
    RiskLevel,
    VerificationLevel,
    VisibilityScope,
)


class RecordCreate(BaseModel):
    title: str
    problem_family: str
    summary: str
    claim: str
    target: TargetRef
    environment: EnvironmentFingerprint | None = None
    versions: VersionInfo | None = None
    steps: list[StepItem] = Field(default_factory=list)
    result: ResultSummary
    evidence: list[EvidenceItem] = Field(default_factory=list)
    applicable_if: list[str] = Field(default_factory=list)
    not_applicable_if: list[str] = Field(default_factory=list)
    status: RecordStatus = RecordStatus.active
    verification_level: VerificationLevel = VerificationLevel.l1
    visibility_scope: VisibilityScope = VisibilityScope.public
    risk_level: RiskLevel = RiskLevel.medium
    execution_mode: ExecutionMode = ExecutionMode.review_before_apply
    source_type: str = "manual"
    tags: list[str] = Field(default_factory=list)
    # v2: primary Case/Thread assignment. Optional for legacy records.
    case_id: str | None = None
    # Q&A knowledge fields (optional, populated by /knowledge endpoint)
    question: str | None = None
    scope: str | None = None
    knowledge_kind: str | None = None


class RecordUpdate(BaseModel):
    """Partial update — only supplied fields are applied. Status changes use dedicated endpoints."""
    title: str | None = None
    summary: str | None = None
    claim: str | None = None
    steps: list[StepItem] | None = None
    evidence: list[EvidenceItem] | None = None
    applicable_if: list[str] | None = None
    not_applicable_if: list[str] | None = None
    verification_level: VerificationLevel | None = None
    visibility_scope: VisibilityScope | None = None
    risk_level: RiskLevel | None = None
    execution_mode: ExecutionMode | None = None


class PromoteRequest(BaseModel):
    review_note: str | None = None


class RejectRequest(BaseModel):
    review_note: str | None = None


class Record(RecordCreate):
    record_id: str
    library_id: str | None = None
    review_note: str | None = None
    reviewed_at: str | None = None
    created_at: str
    updated_at: str
