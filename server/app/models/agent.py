from pydantic import BaseModel, Field
from typing import Literal

from app.models.common import EnvironmentFingerprint, EvidenceItem, TargetRef, VersionInfo
from app.models.enums import FeedbackType, RelationType
from app.models.feedback import Feedback
from app.models.record import Record
from app.models.relation import RecordRelation


class AgentAction(BaseModel):
    """A single step the agent took while solving the task.

    `action` is required (the verb / step description). `rationale`, `ref`,
    and `note` are all optional; they exist because agents naturally want to
    record *why* they did something and *what link / file* it touched in
    addition to the bare verb. Extra fields are forbidden so payload typos
    (e.g. `step` instead of `action`) fail loudly with the field name.
    """

    action: str
    rationale: str | None = None
    ref: str | None = None
    note: str | None = None

    model_config = {"extra": "forbid"}


class AgentIngestRequest(BaseModel):
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
    based_on_record_id: str | None = None
    feedback_type: FeedbackType | None = None
    relation_type: RelationType | None = None
    applicable_if: list[str] = Field(default_factory=list)
    not_applicable_if: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    dry_run: bool = False
    draft_only: bool = False
    redaction_mode: Literal["auto", "none"] = "auto"


class AgentIngestResponse(BaseModel):
    persisted: bool
    requires_manual_review: bool
    review_reasons: list[str] = Field(default_factory=list)
    dry_run: bool = False
    draft_only: bool = False
    record: Record
    feedback: Feedback | None = None
    relation: RecordRelation | None = None
