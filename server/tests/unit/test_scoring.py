"""Unit tests for scoring.py signal functions and composite scorer."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.models.common import EnvironmentFingerprint, ResultSummary, TargetRef, VersionInfo
from app.models.enums import (
    ExecutionMode,
    RecordStatus,
    RiskLevel,
    VerificationLevel,
    VisibilityScope,
)
from app.models.feedback import Feedback
from app.models.query import SearchQuery
from app.models.record import Record
from app.models.relation import RecordRelation
from app.models.enums import RelationType
from app.services.scoring import (
    RISK_PENALTY,
    VERIFICATION_SCORE,
    conflict_penalty,
    content_fts_score,
    environment_score,
    feedback_score,
    freshness_score,
    not_applicable_penalty,
    score_record,
    tag_fts_score,
    text_overlap_score,
    vector_score,
    version_score,
)
from app.services.embedding_service import cosine_similarity


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_record(**overrides) -> Record:
    defaults = dict(
        record_id="r-test",
        title="Fix API timeout by increasing client config",
        problem_family="timeout",
        summary="Setting timeout=30s resolved the issue",
        claim="For API timeouts, increase timeout to 30s",
        target=TargetRef(product="my-api"),
        result=ResultSummary(outcome="success", summary="Fixed"),
        created_at="2024-06-01T00:00:00+00:00",
        updated_at=datetime.now(timezone.utc).isoformat(),
        status=RecordStatus.active,
        verification_level=VerificationLevel.l1,
        visibility_scope=VisibilityScope.public,
        risk_level=RiskLevel.low,
        execution_mode=ExecutionMode.safe_to_apply,
        source_type="agent_ingest",
    )
    defaults.update(overrides)
    return Record(**defaults)


def _make_query(**overrides) -> SearchQuery:
    defaults = dict(
        problem="API call times out",
        query_intent="fix",
        task_type="troubleshooting",
        target=TargetRef(product="my-api"),
        goal="reduce timeout errors",
    )
    defaults.update(overrides)
    return SearchQuery(**defaults)


# ── text_overlap_score ────────────────────────────────────────────────────────

def test_text_overlap_exact_match():
    q = _make_query(problem="API timeout")
    r = _make_record(title="Fix API timeout", summary="API timeout fix", claim="API timeout claim")
    score, reasons = text_overlap_score(q, r)
    assert score == 2.0  # "api" and "timeout" both match
    assert any("timeout" in reason for reason in reasons)


def test_text_overlap_no_match():
    q = _make_query(problem="database connection")
    r = _make_record(title="Fix API timeout", summary="timeout", claim="timeout")
    score, _ = text_overlap_score(q, r)
    assert score == 0.0


def test_text_overlap_empty_problem():
    q = _make_query(problem="")
    r = _make_record()
    score, reasons = text_overlap_score(q, r)
    assert score == 0.0
    assert reasons == []


# ── environment_score ─────────────────────────────────────────────────────────

def test_environment_exact_match():
    env = EnvironmentFingerprint(os="linux", shell="bash", runtime="python3.11")
    q = _make_query(environment=env)
    r = _make_record(environment=env)
    score, reasons = environment_score(q, r)
    assert score == 3.0  # os + shell + runtime
    assert len(reasons) == 3


def test_environment_mismatch_penalty():
    q = _make_query(environment=EnvironmentFingerprint(os="linux"))
    r = _make_record(environment=EnvironmentFingerprint(os="windows"))
    score, _ = environment_score(q, r)
    assert score == -0.5


def test_environment_missing_is_neutral():
    q = _make_query(environment=None)
    r = _make_record(environment=None)
    score, reasons = environment_score(q, r)
    assert score == 0.0
    assert reasons == []


# ── version_score ─────────────────────────────────────────────────────────────

def test_version_exact_match():
    v = VersionInfo(agent="1.2.3", target="2.0.0")
    q = _make_query(versions=v)
    r = _make_record(versions=v)
    score, reasons = version_score(q, r)
    assert score == 2.0


def test_version_major_family_match():
    q = _make_query(versions=VersionInfo(agent="1.2.3"))
    r = _make_record(versions=VersionInfo(agent="1.9.0"))
    score, reasons = version_score(q, r)
    assert score == 0.5
    assert any("family" in r for r in reasons)


def test_version_no_match():
    q = _make_query(versions=VersionInfo(agent="1.0.0"))
    r = _make_record(versions=VersionInfo(agent="2.0.0"))
    score, _ = version_score(q, r)
    assert score == 0.0


# ── freshness_score ───────────────────────────────────────────────────────────

def test_freshness_very_fresh():
    r = _make_record(updated_at=datetime.now(timezone.utc).isoformat())
    assert freshness_score(r) == 1.0


def test_freshness_moderate():
    old = datetime.now(timezone.utc) - timedelta(days=90)
    r = _make_record(updated_at=old.isoformat())
    assert freshness_score(r) == 0.5


def test_freshness_old():
    old = datetime.now(timezone.utc) - timedelta(days=400)
    r = _make_record(updated_at=old.isoformat())
    assert freshness_score(r) == 0.0


# ── feedback_score ────────────────────────────────────────────────────────────

def _make_feedback(ft: str) -> Feedback:
    from app.core.ids import new_id
    from app.core.time import utc_now_iso
    from app.models.enums import FeedbackType

    return Feedback(
        feedback_id=new_id("fb"),
        record_id="r-test",
        feedback_type=FeedbackType(ft),
        summary="test feedback",
        result=ResultSummary(outcome="success", summary="applied the fix"),
        created_at=utc_now_iso(),
    )


def test_feedback_success_reuse():
    score = feedback_score([_make_feedback("success_reuse")])
    assert score == 0.5


def test_feedback_failure_reuse():
    score = feedback_score([_make_feedback("failure_reuse")])
    assert score == -0.4


def test_feedback_mixed():
    items = [_make_feedback("success_reuse"), _make_feedback("failure_reuse")]
    score = feedback_score(items)
    assert abs(score - 0.1) < 1e-9


# ── conflict_penalty ──────────────────────────────────────────────────────────

def test_conflict_penalty_counted():
    from app.core.ids import new_id
    from app.core.time import utc_now_iso

    rel = RecordRelation(
        relation_id=new_id("rel"),
        from_record_id="r1",
        to_record_id="r2",
        relation_type=RelationType.conflicts_with,
        summary="conflicts",
        created_at=utc_now_iso(),
    )
    assert conflict_penalty([rel]) == 1.0


def test_conflict_penalty_non_conflict_not_counted():
    from app.core.ids import new_id
    from app.core.time import utc_now_iso

    rel = RecordRelation(
        relation_id=new_id("rel"),
        from_record_id="r1",
        to_record_id="r2",
        relation_type=RelationType.derived_from,
        summary="derived",
        created_at=utc_now_iso(),
    )
    assert conflict_penalty([rel]) == 0.0


# ── not_applicable_penalty ────────────────────────────────────────────────────

def test_not_applicable_triggers():
    r = _make_record(not_applicable_if=["production environment only"])
    q = _make_query(problem="deploy to production environment")
    penalty, reasons = not_applicable_penalty(q, r)
    assert penalty > 0
    assert reasons


def test_not_applicable_no_overlap():
    r = _make_record(not_applicable_if=["production environment only"])
    q = _make_query(problem="local development test")
    penalty, _ = not_applicable_penalty(q, r)
    assert penalty == 0.0


def test_not_applicable_empty():
    r = _make_record(not_applicable_if=[])
    q = _make_query(problem="anything")
    penalty, _ = not_applicable_penalty(q, r)
    assert penalty == 0.0


# ── tag_fts_score ─────────────────────────────────────────────────────────────

def test_tag_fts_score_hit():
    scores, reasons = tag_fts_score("r1", {"r1": 2.5, "r2": 1.0})
    assert scores == 2.5
    assert "bm25=2.50" in reasons[0]


def test_tag_fts_score_miss():
    scores, reasons = tag_fts_score("r-missing", {"r1": 2.5})
    assert scores == 0.0
    assert reasons == []


# ── content_fts_score ─────────────────────────────────────────────────────────

def test_content_fts_score_hit():
    score, reasons = content_fts_score("r1", {"r1": 1.8})
    assert score == 1.8
    assert reasons


def test_content_fts_score_miss():
    score, reasons = content_fts_score("r-missing", {"r1": 1.8})
    assert score == 0.0
    assert reasons == []


# ── vector_score ──────────────────────────────────────────────────────────────

def test_vector_score_high_similarity():
    vec = np.ones(4, dtype=np.float32)
    vec /= np.linalg.norm(vec)
    score, reasons = vector_score("r1", vec, {"r1": vec})
    assert score > 0.9
    assert "semantic similarity" in reasons[0]


def test_vector_score_low_similarity_filtered():
    a = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)
    score, reasons = vector_score("r1", a, {"r1": b})
    # cosine = 0.0, below threshold 0.3
    assert score == 0.0
    assert reasons == []


def test_vector_score_no_query_embedding():
    vec = np.ones(4, dtype=np.float32) / 2
    score, reasons = vector_score("r1", None, {"r1": vec})
    assert score == 0.0


def test_vector_score_missing_record_embedding():
    vec = np.ones(4, dtype=np.float32) / 2
    score, reasons = vector_score("r-missing", vec, {"r1": vec})
    assert score == 0.0


# ── score_record integration ──────────────────────────────────────────────────

def test_score_record_basic():
    q = _make_query()
    r = _make_record()
    score, reasons = score_record(q, r, feedback_items=[], relations=[])
    assert isinstance(score, float)
    assert isinstance(reasons, list)


def test_score_record_tag_fts_boost():
    q = _make_query()
    r = _make_record()
    # With tag FTS score
    score_with, _ = score_record(
        q, r, feedback_items=[], relations=[],
        fts_tag_scores={r.record_id: 2.0},
    )
    score_without, _ = score_record(q, r, feedback_items=[], relations=[])
    # Tag score weight = 3, so diff should be ~6.0
    assert score_with - score_without == pytest.approx(6.0)


def test_score_record_risk_penalty():
    q = _make_query()
    r_low = _make_record(risk_level=RiskLevel.low)
    r_high = _make_record(risk_level=RiskLevel.high)
    score_low, _ = score_record(q, r_low, [], [])
    score_high, _ = score_record(q, r_high, [], [])
    # high risk costs 3.0 * 2 = 6.0 more than low risk (0.0 * 2)
    expected_diff = (RISK_PENALTY[RiskLevel.high] - RISK_PENALTY[RiskLevel.low]) * 2
    assert score_low - score_high == pytest.approx(expected_diff)


def test_score_record_failure_outcome_penalised():
    q = _make_query()
    r = _make_record(result=ResultSummary(outcome="failure", summary="failed"))
    score, _ = score_record(q, r, [], [])
    r_success = _make_record()
    score_success, _ = score_record(q, r_success, [], [])
    assert score_success > score  # failure should score lower


def test_score_record_all_signals():
    """Smoke test that all optional signal dicts can be provided without error."""
    q = _make_query()
    r = _make_record()
    vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    score, reasons = score_record(
        q, r, [],
        fts_tag_scores={"r-test": 1.0},
        fts_content_scores={"r-test": 0.5},
        query_embedding=vec,
        record_embeddings={"r-test": vec},
    )
    assert score > 0
