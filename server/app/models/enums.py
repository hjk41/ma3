from enum import Enum


class RecordStatus(str, Enum):
    draft = "draft"
    active = "active"
    stale = "stale"
    superseded = "superseded"
    invalid = "invalid"
    archived = "archived"
    quarantine = "quarantine"


class VerificationLevel(str, Enum):
    l0 = "L0"
    l1 = "L1"
    l2 = "L2"
    l3 = "L3"
    l4 = "L4"


class VisibilityScope(str, Enum):
    public = "public"
    tenant = "tenant"
    group = "group"
    private = "private"


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ExecutionMode(str, Enum):
    safe_to_apply = "safe_to_apply"
    review_before_apply = "review_before_apply"
    manual_only = "manual_only"
    never_auto_apply = "never_auto_apply"


class FeedbackType(str, Enum):
    success_reuse = "success_reuse"
    failure_reuse = "failure_reuse"
    conditional_success = "conditional_success"
    derived_record = "derived_record"


class RelationType(str, Enum):
    conflicts_with = "conflicts_with"
    supersedes = "supersedes"
    derived_from = "derived_from"
    same_problem_family = "same_problem_family"
    invalid_under = "invalid_under"


class SourceType(str, Enum):
    agent_verified = "agent_verified"
    authority_defined = "authority_defined"
    measured = "measured"
    derived = "derived"
    referenced = "referenced"


class KnowledgeKind(str, Enum):
    experience = "experience"
    measurement = "measurement"
    specification = "specification"
    research_finding = "research_finding"
    state_snapshot = "state_snapshot"
    decision_rationale = "decision_rationale"
    comparative_analysis = "comparative_analysis"
    process_protocol = "process_protocol"
    terminology = "terminology"
    resource_map = "resource_map"
    calibration = "calibration"
    deliberate_exclusion = "deliberate_exclusion"
