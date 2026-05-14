from app.models.common import ResultSummary, TargetRef
from app.models.enums import ExecutionMode, RiskLevel, VerificationLevel
from app.models.knowledge import KnowledgeCreate
from app.models.record import Record, RecordCreate
from app.services.record_service import create_record


def _knowledge_kind_to_problem_family(knowledge_kind: str) -> str:
    return knowledge_kind.replace("_", "-")


def _build_record_create(payload: KnowledgeCreate) -> RecordCreate:
    title = payload.title or payload.question

    # Build a source-detail note for the claim field
    source_parts = [f"source_type={payload.source_type.value}"]
    if payload.authority:
        source_parts.append(f"authority={payload.authority}")
    if payload.source_ref:
        source_parts.append(f"ref={payload.source_ref}")
    claim = f"{payload.summary} [{', '.join(source_parts)}]"

    return RecordCreate(
        title=title,
        problem_family=_knowledge_kind_to_problem_family(payload.knowledge_kind.value),
        summary=payload.summary,
        claim=claim,
        target=TargetRef(product="knowledge", component=payload.knowledge_kind.value),
        result=ResultSummary(outcome="recorded", summary=payload.summary),
        status=payload.status,
        visibility_scope=payload.visibility_scope,
        applicable_if=payload.applicable_if,
        not_applicable_if=payload.not_applicable_if,
        source_type=payload.source_type.value,
        tags=payload.tags,
        question=payload.question,
        scope=payload.scope,
        knowledge_kind=payload.knowledge_kind.value,
        # Non-experiential knowledge is never auto-executed
        execution_mode=ExecutionMode.manual_only,
        risk_level=RiskLevel.low,
        verification_level=VerificationLevel.l0,
    )


def create_knowledge(payload: KnowledgeCreate, library_id: str | None = None) -> Record:
    record_payload = _build_record_create(payload)
    return create_record(record_payload, library_id=library_id, redaction_mode=payload.redaction_mode)
