from __future__ import annotations

from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.models.common import ResultSummary, StepItem
from app.models.enums import FeedbackType, RelationType
from app.models.feedback import FeedbackCreate
from app.models.record import Record, RecordCreate
from app.models.relation import RecordRelationCreate
from app.models.v2 import (
    CaseAssignment,
    V2AgentReportRequest,
    V2AgentReportResponse,
)
from app.services.case_service import assign_case, slugify, touch_case_with_record
from app.services.feedback_service import create_feedback
from app.services.metrics_service import metrics
from app.services.op_log_service import write_op_log
from app.services.record_service import _allow_secret_preservation, create_record
from app.services.redaction import redact_value
from app.services.relation_service import create_relation
from app.services.risk_service import assess_agent_ingest_risk
from app.models.agent import AgentIngestRequest
from app.storage.repositories import RecordRepository


def _agent_risk_payload(payload: V2AgentReportRequest) -> AgentIngestRequest:
    return AgentIngestRequest(
        problem=payload.problem,
        task_type=payload.task_type,
        goal=payload.goal,
        target=payload.target,
        environment=payload.environment,
        versions=payload.versions,
        observations=payload.observations,
        actions=payload.actions,
        outcome=payload.outcome,
        result_summary=payload.result_summary,
        evidence=payload.evidence,
        based_on_record_id=payload.based_on_record_ids[0] if payload.based_on_record_ids else None,
        applicable_if=payload.applicable_if,
        not_applicable_if=payload.not_applicable_if,
        tags=payload.tags,
        dry_run=payload.dry_run,
        redaction_mode=payload.redaction_mode,
    )


def _record_payload(payload: V2AgentReportRequest, assessment, case_id: str | None) -> RecordCreate:
    return RecordCreate(
        title=f"{payload.target.product}: {payload.result_summary}".strip(),
        problem_family=slugify(payload.task_type),
        summary=". ".join(x for x in [payload.problem, payload.result_summary] if x),
        claim=f"For {payload.goal}, the reported outcome was {payload.outcome}: {payload.result_summary}.",
        target=payload.target,
        environment=payload.environment,
        versions=payload.versions,
        steps=[
            StepItem(order=i + 1, action=a.action, note=a.note)
            for i, a in enumerate(payload.actions)
        ],
        result=ResultSummary(
            outcome=payload.outcome,
            summary=payload.result_summary,
            details=payload.observations,
        ),
        evidence=payload.evidence,
        applicable_if=payload.applicable_if,
        not_applicable_if=payload.not_applicable_if,
        status=assessment.status,
        visibility_scope=assessment.visibility_scope,
        risk_level=assessment.risk_level,
        execution_mode=assessment.execution_mode,
        source_type="v2_agent_report",
        tags=payload.tags,
        case_id=case_id,
    )


def _preview_record(
    payload: RecordCreate,
    library_id: str | None,
    redaction_mode: str = "auto",
) -> Record:
    sanitized = RecordCreate.model_validate(
        redact_value(
            payload.model_dump(),
            mode=redaction_mode,
            allow_secret_preservation=_allow_secret_preservation(library_id),
        )
    )
    now = utc_now_iso()
    return Record(
        record_id=f"preview_{new_id('vk')}",
        library_id=library_id,
        created_at=now,
        updated_at=now,
        **sanitized.model_dump(),
    )


def ingest_v2_agent_report(
    payload: V2AgentReportRequest,
    library_id: str | None,
    accessible_library_ids: set[str],
) -> V2AgentReportResponse:
    record_repo = RecordRepository()
    based_on_records = [
        r for rid in payload.based_on_record_ids
        if (r := record_repo.get(rid)) is not None
        and (r.library_id is None or r.library_id in accessible_library_ids)
    ]

    if payload.dry_run and not payload.case_id:
        assignment = CaseAssignment(
            result="dry_run",
            case=None,
            confidence=0.0,
            reasons=["dry_run does not create or auto-assign a new case"],
        )
    else:
        assignment = assign_case(payload, library_id, accessible_library_ids, based_on_records)

    assessment = assess_agent_ingest_risk(_agent_risk_payload(payload))
    record_payload = _record_payload(payload, assessment, assignment.case.case_id if assignment.case else None)
    if payload.dry_run:
        record = _preview_record(record_payload, library_id, payload.redaction_mode)
        write_op_log(
            "agent_report",
            operation_result="dry_run",
            library_id=library_id,
            case_id=assignment.case.case_id if assignment.case else None,
            record_id=record.record_id,
            payload_summary={"outcome": payload.outcome, "task_type": payload.task_type},
        )
        return V2AgentReportResponse(
            persisted=False,
            record=record,
            case_assignment=assignment,
            requires_manual_review=assessment.requires_manual_review,
            review_reasons=assessment.review_reasons,
        )

    record = create_record(record_payload, library_id=library_id, redaction_mode=payload.redaction_mode)
    if assignment.case is not None:
        assignment.case = touch_case_with_record(assignment.case, record)

    relations = []
    feedback = []
    relation_type = RelationType(payload.relation_type) if payload.relation_type else RelationType.derived_from
    for prior in based_on_records:
        feedback_item = create_feedback(
            FeedbackCreate(
                record_id=prior.record_id,
                feedback_type=FeedbackType.derived_record,
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
                to_record_id=prior.record_id,
                relation_type=relation_type,
                summary=payload.result_summary,
            )
        )
        feedback.append(feedback_item.model_dump())
        relations.append(relation)

    metrics.record_ingest(payload.outcome, assessment.risk_level.value)
    metrics.record_case_assignment(assignment.result)
    write_op_log(
        "agent_report",
        operation_result="persisted",
        library_id=library_id,
        case_id=record.case_id,
        record_id=record.record_id,
        payload_summary={
            "outcome": payload.outcome,
            "task_type": payload.task_type,
            "case_assignment": assignment.result,
            "risk_level": assessment.risk_level.value,
        },
    )
    return V2AgentReportResponse(
        persisted=True,
        record=record,
        case_assignment=assignment,
        relations_created=relations,
        feedback_created=feedback,
        requires_manual_review=assessment.requires_manual_review,
        review_reasons=assessment.review_reasons,
    )
