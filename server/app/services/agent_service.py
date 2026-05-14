import re

from app.models.agent import AgentIngestRequest, AgentIngestResponse
from app.models.common import ResultSummary, StepItem
from app.models.enums import FeedbackType, RecordStatus, RelationType
from app.models.feedback import FeedbackCreate
from app.models.record import Record, RecordCreate
from app.models.relation import RecordRelationCreate
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.services.feedback_service import create_feedback
from app.services.record_service import create_record
from app.services.redaction import redact_value
from app.services.relation_service import create_relation
from app.services.risk_service import AgentRiskAssessment, assess_agent_ingest_risk


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "general"


def _build_title(payload: AgentIngestRequest) -> str:
    product = payload.target.product
    return f"{product}: {payload.result_summary}".strip()


def _build_summary(payload: AgentIngestRequest) -> str:
    parts = [payload.problem, payload.result_summary]
    if payload.observations:
        parts.append(payload.observations[0])
    return ". ".join(part.strip().rstrip(".") for part in parts if part).strip() + "."


def _build_claim(payload: AgentIngestRequest) -> str:
    return f"For {payload.goal}, the reported outcome was {payload.outcome}: {payload.result_summary}."


def _build_steps(payload: AgentIngestRequest) -> list[StepItem]:
    return [
        StepItem(order=index + 1, action=item.action, note=item.note)
        for index, item in enumerate(payload.actions)
    ]


def _build_record_create(
    payload: AgentIngestRequest,
    assessment: AgentRiskAssessment,
) -> RecordCreate:
    return RecordCreate(
        title=_build_title(payload),
        problem_family=_slugify(payload.task_type),
        summary=_build_summary(payload),
        claim=_build_claim(payload),
        target=payload.target,
        environment=payload.environment,
        versions=payload.versions,
        steps=_build_steps(payload),
        result=ResultSummary(
            outcome=payload.outcome,
            summary=payload.result_summary,
            details=payload.observations,
        ),
        evidence=payload.evidence,
        applicable_if=payload.applicable_if,
        not_applicable_if=payload.not_applicable_if,
        tags=payload.tags,
        status=assessment.status,
        visibility_scope=assessment.visibility_scope,
        risk_level=assessment.risk_level,
        execution_mode=assessment.execution_mode,
        source_type="agent_ingest",
    )


def _preview_record(
    payload: RecordCreate,
    library_id: str | None = None,
    redaction_mode: str = "auto",
) -> Record:
    sanitized = RecordCreate.model_validate(redact_value(payload.model_dump(), mode=redaction_mode))
    now = utc_now_iso()
    return Record(
        record_id=f"preview_{new_id('vk')}",
        library_id=library_id,
        created_at=now,
        updated_at=now,
        **sanitized.model_dump(),
    )


def ingest_agent_report(
    payload: AgentIngestRequest,
    library_id: str | None = None,
) -> AgentIngestResponse:
    assessment = assess_agent_ingest_risk(payload)
    record_payload = _build_record_create(payload, assessment)

    if payload.dry_run:
        return AgentIngestResponse(
            persisted=False,
            requires_manual_review=assessment.requires_manual_review,
            review_reasons=assessment.review_reasons,
            dry_run=True,
            draft_only=False,
            record=_preview_record(record_payload, library_id, payload.redaction_mode),
            feedback=None,
            relation=None,
        )

    record = create_record(record_payload, library_id=library_id, redaction_mode=payload.redaction_mode)

    feedback = None
    relation = None

    if payload.based_on_record_id:
        feedback = create_feedback(
            FeedbackCreate(
                record_id=payload.based_on_record_id,
                feedback_type=payload.feedback_type or FeedbackType.derived_record,
                summary=payload.result_summary,
                environment=payload.environment,
                result=ResultSummary(
                    outcome=payload.outcome,
                    summary=payload.result_summary,
                    details=payload.observations,
                ),
            )
        )
        relation = create_relation(
            RecordRelationCreate(
                from_record_id=record.record_id,
                to_record_id=payload.based_on_record_id,
                relation_type=payload.relation_type or RelationType.derived_from,
                summary=payload.result_summary,
            )
        )

    return AgentIngestResponse(
        persisted=True,
        requires_manual_review=assessment.requires_manual_review,
        review_reasons=assessment.review_reasons,
        dry_run=False,
        draft_only=False,
        record=record,
        feedback=feedback,
        relation=relation,
    )
