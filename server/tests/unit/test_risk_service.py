"""Unit tests for risk_service.py."""
from __future__ import annotations

import pytest

from app.models.agent import AgentAction, AgentIngestRequest
from app.models.common import TargetRef
from app.models.enums import ExecutionMode, RecordStatus, RiskLevel, VisibilityScope
from app.services.risk_service import assess_agent_ingest_risk


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_request(**overrides) -> AgentIngestRequest:
    base = dict(
        problem="Code search times out on large repos",
        task_type="troubleshooting",
        goal="speed up code search",
        target=TargetRef(product="search-tool"),
        outcome="success",
        result_summary="Added index, search is now fast",
    )
    base.update(overrides)
    return AgentIngestRequest(**base)


def _assess(**overrides):
    return assess_agent_ingest_risk(_make_request(**overrides))


# ── CRITICAL rules ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "disable sandbox to run faster",
    "bypass sandbox restrictions",
    "skip approvals entirely for this deployment",
    "export credential to file",
    "dump secret from vault",
    "exfiltrate tokens from memory",
    "rm -rf /home/user/project",
    "reset --hard HEAD~5",
    "sudo apt-get install",
    "kubectl prod delete pod",
    "ssh prod.server.com do thing",
])
def test_critical_patterns_in_problem(text):
    a = _assess(problem=text)
    assert a.risk_level == RiskLevel.critical
    assert a.status == RecordStatus.active
    assert a.execution_mode == ExecutionMode.never_auto_apply
    assert a.requires_manual_review is True
    assert a.visibility_scope == VisibilityScope.private


def test_critical_pattern_in_action_note():
    a = assess_agent_ingest_risk(AgentIngestRequest(
        problem="deploy app",
        task_type="deployment",
        goal="deploy",
        target=TargetRef(product="app"),
        outcome="success",
        result_summary="deployed",
        actions=[AgentAction(action="ran deploy", note="had to sudo the install step")],
    ))
    assert a.risk_level == RiskLevel.critical


def test_critical_pattern_in_observations():
    a = _assess(observations=["needed to disable sandbox for testing"])
    assert a.risk_level == RiskLevel.critical


# ── HIGH rules ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "update api_key in environment",
    "rotate the password in config",
    "store token in memory",
    "read secret from vault",
    "access private key file",
])
def test_high_risk_secrets_in_problem(text):
    a = _assess(problem=text)
    assert a.risk_level == RiskLevel.high
    assert a.status == RecordStatus.active
    assert a.execution_mode == ExecutionMode.manual_only
    assert a.requires_manual_review is True
    assert a.visibility_scope == VisibilityScope.tenant


def test_high_risk_registry_in_result_summary():
    a = _assess(result_summary="updated registry key for service account")
    assert a.risk_level == RiskLevel.high


# ── LOW-RISK task types ───────────────────────────────────────────────────────

@pytest.mark.parametrize("task_type", [
    "documentation",
    "summarization",
    "indexing",
    "triage",
    "read_only_search",
    "Documentation",      # case-insensitive
    "Read Only Search",   # spaces normalised to underscores
])
def test_low_risk_task_types(task_type):
    a = _assess(task_type=task_type)
    assert a.risk_level == RiskLevel.low
    assert a.status == RecordStatus.active
    assert a.execution_mode == ExecutionMode.safe_to_apply
    assert a.requires_manual_review is False
    assert a.visibility_scope == VisibilityScope.public


# ── Default: MEDIUM ───────────────────────────────────────────────────────────

def test_default_medium_risk():
    a = _assess(task_type="troubleshooting")
    assert a.risk_level == RiskLevel.medium
    assert a.status == RecordStatus.active
    assert a.execution_mode == ExecutionMode.review_before_apply
    assert a.requires_manual_review is False


def test_critical_overrides_high():
    """Critical patterns take precedence over high patterns."""
    a = _assess(
        problem="sudo export credential to production",
    )
    assert a.risk_level == RiskLevel.critical


def test_high_overrides_low_task_type():
    """High-risk content overrides low-risk task type."""
    a = _assess(
        task_type="documentation",
        problem="document the api_key rotation process",
    )
    assert a.risk_level == RiskLevel.high


# ── review_reasons populated ──────────────────────────────────────────────────

def test_review_reasons_populated_for_critical():
    a = _assess(problem="disable sandbox")
    assert len(a.review_reasons) > 0
    assert any("sandbox" in reason.lower() for reason in a.review_reasons)


def test_review_reasons_empty_for_medium():
    a = _assess()
    assert a.review_reasons == []
