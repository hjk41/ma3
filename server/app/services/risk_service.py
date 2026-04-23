import re
from dataclasses import dataclass

from app.models.agent import AgentIngestRequest
from app.models.enums import ExecutionMode, RecordStatus, RiskLevel, VisibilityScope


@dataclass(slots=True)
class AgentRiskAssessment:
    risk_level: RiskLevel
    execution_mode: ExecutionMode
    status: RecordStatus
    visibility_scope: VisibilityScope
    requires_manual_review: bool
    review_reasons: list[str]


CRITICAL_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "request touches sandbox or security-boundary bypass behavior",
        re.compile(
            r"(?i)\b("
            r"disable sandbox|bypass sandbox|turn off sandbox|skip sandbox|"
            r"disable security boundar(?:y|ies)|bypass security|"
            r"disable safety|turn off safety|skip approvals entirely"
            r")\b"
        ),
    ),
    (
        "request includes credential export or secret exfiltration language",
        re.compile(
            r"(?i)\b("
            r"export credential|export secret|dump credential|dump secret|"
            r"print token|reveal token|exfiltrat(?:e|ion)|copy password"
            r")\b"
        ),
    ),
    (
        "request includes destructive filesystem behavior",
        re.compile(
            r"(?i)\b("
            r"rm\s+-rf|remove-item\b.*-recurse|del\s+/s|format-volume|"
            r"drop table|truncate table|reset --hard"
            r")\b"
        ),
    ),
    (
        "request includes privileged or production remote execution language",
        re.compile(
            r"(?i)\b("
            r"sudo\b|run as administrator|privilege escalation|"
            r"remote exec|remote execution|ssh\b.*\bprod(?:uction)?\b|"
            r"kubectl\b.*\bprod(?:uction)?\b"
            r")\b"
        ),
    ),
]

HIGH_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "request touches secrets or authentication material",
        re.compile(
            r"(?i)\b("
            r"api[_ -]?key|token|password|secret|credential|session cookie|"
            r"access key|private key|kubeconfig"
            r")\b"
        ),
    ),
    (
        "request changes machine-wide or admin-level configuration",
        re.compile(
            r"(?i)\b("
            r"machinepolicy|localmachine|registry|executionpolicy|service account|"
            r"administrator privileges|admin rights"
            r")\b"
        ),
    ),
]

LOW_RISK_TASK_TYPES = {
    "documentation",
    "summarization",
    "indexing",
    "triage",
    "read_only_search",
}


def _collect_text(payload: AgentIngestRequest) -> str:
    parts = [
        payload.problem,
        payload.task_type,
        payload.goal,
        payload.outcome,
        payload.result_summary,
        *payload.observations,
        *payload.applicable_if,
        *payload.not_applicable_if,
    ]
    for action in payload.actions:
        parts.append(action.action)
        if action.note:
            parts.append(action.note)
    for item in payload.evidence:
        parts.append(item.kind)
        parts.append(item.summary)
        if item.ref:
            parts.append(item.ref)
    return "\n".join(part for part in parts if part)


def assess_agent_ingest_risk(payload: AgentIngestRequest) -> AgentRiskAssessment:
    combined = _collect_text(payload)
    critical_reasons = [
        reason for reason, pattern in CRITICAL_RULES if pattern.search(combined)
    ]
    if critical_reasons:
        return AgentRiskAssessment(
            risk_level=RiskLevel.critical,
            execution_mode=ExecutionMode.never_auto_apply,
            status=RecordStatus.active,
            visibility_scope=VisibilityScope.private,
            requires_manual_review=True,
            review_reasons=critical_reasons,
        )

    high_reasons = [reason for reason, pattern in HIGH_RULES if pattern.search(combined)]
    if high_reasons:
        return AgentRiskAssessment(
            risk_level=RiskLevel.high,
            execution_mode=ExecutionMode.manual_only,
            status=RecordStatus.active,
            visibility_scope=VisibilityScope.tenant,
            requires_manual_review=True,
            review_reasons=high_reasons,
        )

    normalized_task_type = payload.task_type.strip().lower().replace(" ", "_")
    if normalized_task_type in LOW_RISK_TASK_TYPES:
        return AgentRiskAssessment(
            risk_level=RiskLevel.low,
            execution_mode=ExecutionMode.safe_to_apply,
            status=RecordStatus.active,
            visibility_scope=VisibilityScope.public,
            requires_manual_review=False,
            review_reasons=[],
        )

    return AgentRiskAssessment(
        risk_level=RiskLevel.medium,
        execution_mode=ExecutionMode.review_before_apply,
        status=RecordStatus.active,
        visibility_scope=VisibilityScope.public,
        requires_manual_review=False,
        review_reasons=[],
    )
