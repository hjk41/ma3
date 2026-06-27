from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.models.enums import RecordStatus, RiskLevel, VerificationLevel
from app.models.feedback import Feedback
from app.models.query import SearchQuery
from app.models.record import Record
from app.models.relation import RecordRelation
from app.models.enums import RelationType

if TYPE_CHECKING:
    import numpy as np


VERIFICATION_SCORE = {
    VerificationLevel.l0: 0.0,
    VerificationLevel.l1: 1.0,
    VerificationLevel.l2: 2.0,
    VerificationLevel.l3: 3.0,
    VerificationLevel.l4: 4.0,
}

RISK_PENALTY = {
    RiskLevel.low: 0.0,
    RiskLevel.medium: 1.0,
    RiskLevel.high: 3.0,
    RiskLevel.critical: 10.0,
}


# Soft search decay for lifecycle states. ``active`` ranks normally; ``stale``
# and ``superseded`` records remain discoverable (so they can serve as a
# fallback and stay auditable) but are pushed down the ranking. Statuses that
# must never surface (draft/invalid/archived/quarantine) are filtered earlier
# in ``search_service`` and are intentionally absent from this map.
STATUS_DECAY = {
    RecordStatus.active: 0.0,
    RecordStatus.stale: 4.0,
    RecordStatus.superseded: 8.0,
}


_STOP_WORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "do", "for",
    "from", "how", "i", "if", "in", "is", "it", "not", "of", "on", "or",
    "that", "the", "their", "there", "they", "this", "to", "up", "was",
    "what", "when", "which", "who", "will", "with",
})


def text_overlap_score(query: SearchQuery, record: Record) -> tuple[float, list[str]]:
    haystack = " ".join(
        [
            record.title.lower(),
            record.problem_family.lower(),
            record.summary.lower(),
            record.claim.lower(),
        ]
    )
    terms = {
        part for part in query.problem.lower().split()
        if part and len(part) > 2 and part not in _STOP_WORDS
    }
    if not terms:
        return 0.0, []
    hits = sorted(term for term in terms if term in haystack)
    reasons = [f"text match: {term}" for term in hits[:4]]
    return float(len(hits)), reasons


def environment_score(query: SearchQuery, record: Record) -> tuple[float, list[str]]:
    if query.environment is None or record.environment is None:
        return 0.0, []
    reasons: list[str] = []
    score = 0.0
    fields = [
        ("os", query.environment.os, record.environment.os),
        ("shell", query.environment.shell, record.environment.shell),
        ("runtime", query.environment.runtime, record.environment.runtime),
        ("sandbox", query.environment.sandbox, record.environment.sandbox),
        (
            "workspace_boundary",
            query.environment.workspace_boundary,
            record.environment.workspace_boundary,
        ),
        (
            "network_profile",
            query.environment.network_profile,
            record.environment.network_profile,
        ),
    ]
    for field_name, left, right in fields:
        if not left or not right:
            continue
        if left == right:
            score += 1.0
            reasons.append(f"{field_name} matched")
        else:
            score -= 0.5
    return score, reasons


def version_score(query: SearchQuery, record: Record) -> tuple[float, list[str]]:
    if query.versions is None or record.versions is None:
        return 0.0, []
    reasons: list[str] = []
    score = 0.0
    for field_name in ("agent", "target"):
        qv = getattr(query.versions, field_name)
        rv = getattr(record.versions, field_name)
        if not qv or not rv:
            continue
        if qv == rv:
            score += 1.0
            reasons.append(f"{field_name} version exact")
            continue
        if qv.split(".")[0] == rv.split(".")[0]:
            score += 0.5
            reasons.append(f"{field_name} version family match")
    return score, reasons


def freshness_score(record: Record) -> float:
    try:
        updated_at = datetime.fromisoformat(record.updated_at)
    except ValueError:
        return 0.0
    now = datetime.now(timezone.utc)
    age_days = (now - updated_at).days
    if age_days <= 30:
        return 1.0
    if age_days <= 180:
        return 0.5
    if age_days <= 365:
        return 0.2
    return 0.0


def feedback_score(feedback_items: list[Feedback]) -> float:
    score = 0.0
    for item in feedback_items:
        if item.feedback_type == "success_reuse":
            score += 0.5
        elif item.feedback_type == "conditional_success":
            score += 0.2
        elif item.feedback_type == "failure_reuse":
            score -= 0.4
    return score


def conflict_penalty(relations: list[RecordRelation]) -> float:
    """Penalise records that have explicit conflicts_with relationships."""
    return float(
        sum(1 for r in relations if r.relation_type == RelationType.conflicts_with)
    )


def status_decay_penalty(record: Record) -> tuple[float, list[str]]:
    """Soft-decay penalty for lifecycle status (stale/superseded).

    Returns a positive penalty to subtract from the record's score plus an
    explanation string. ``active`` records (and any status not in
    ``STATUS_DECAY``) incur no penalty.
    """
    penalty = STATUS_DECAY.get(record.status, 0.0)
    if penalty <= 0:
        return 0.0, []
    status_label = record.status.value if hasattr(record.status, "value") else str(record.status)
    return penalty, [f"status decay: {status_label} (-{penalty:.1f})"]


def not_applicable_penalty(query: SearchQuery, record: Record) -> tuple[float, list[str]]:
    """
    Heavy penalty when the query context matches one of the record's not_applicable_if conditions.

    Strategy: build a term set from the query (problem, goal, task_type, environment fields),
    then for each not_applicable_if entry check keyword overlap.  A single-word entry that
    appears verbatim, or a multi-word entry with ≥2 overlapping terms, triggers a penalty.
    """
    if not record.not_applicable_if:
        return 0.0, []

    context_parts: list[str] = [query.problem, query.goal, query.task_type]
    if query.environment:
        env = query.environment
        context_parts.extend(
            v for v in (env.os, env.shell, env.runtime, env.sandbox,
                        env.workspace_boundary, env.network_profile)
            if v
        )
    query_terms = {
        word
        for phrase in context_parts
        if phrase
        for word in phrase.lower().split()
    }

    penalty = 0.0
    reasons: list[str] = []
    for condition in record.not_applicable_if:
        cond_terms = {word for word in condition.lower().split() if len(word) > 1}
        if not cond_terms:
            continue
        overlap = query_terms & cond_terms
        if len(overlap) >= min(2, len(cond_terms)):
            penalty += 3.0
            reasons.append(f"not applicable: {condition[:60]}")
    return penalty, reasons


# ── New search signal functions ───────────────────────────────────────────────


def tag_fts_score(
    record_id: str,
    fts_tag_scores: dict[str, float],
) -> tuple[float, list[str]]:
    """Score from tag-index BM25 match (precise)."""
    score = fts_tag_scores.get(record_id, 0.0)
    reasons = [f"tag match (bm25={score:.2f})"] if score > 0 else []
    return score, reasons


def content_fts_score(
    record_id: str,
    fts_content_scores: dict[str, float],
) -> tuple[float, list[str]]:
    """Score from content-index BM25 match (broad)."""
    score = fts_content_scores.get(record_id, 0.0)
    reasons = [f"content match (bm25={score:.2f})"] if score > 0 else []
    return score, reasons


def vector_score(
    record_id: str,
    query_embedding: "np.ndarray | None",
    record_embeddings: "dict[str, np.ndarray]",
) -> tuple[float, list[str]]:
    """Cosine similarity between query and record embeddings."""
    if query_embedding is None or record_id not in record_embeddings:
        return 0.0, []
    from app.services.embedding_service import cosine_similarity
    sim = cosine_similarity(query_embedding, record_embeddings[record_id])
    if sim < 0.3:
        return 0.0, []
    reasons = [f"semantic similarity {sim:.2f}"]
    return sim, reasons


# ── Composite scorer ──────────────────────────────────────────────────────────


def score_record(
    query: SearchQuery,
    record: Record,
    feedback_items: list[Feedback],
    relations: list[RecordRelation] | None = None,
    fts_tag_scores: dict[str, float] | None = None,
    fts_content_scores: dict[str, float] | None = None,
    query_embedding: "np.ndarray | None" = None,
    record_embeddings: "dict[str, np.ndarray] | None" = None,
) -> tuple[float, list[str]]:
    reasons: list[str] = []

    text_s, text_r = text_overlap_score(query, record)
    env_s, env_r = environment_score(query, record)
    ver_s, ver_r = version_score(query, record)
    tag_s, tag_r = tag_fts_score(record.record_id, fts_tag_scores or {})
    con_s, con_r = content_fts_score(record.record_id, fts_content_scores or {})
    vec_s, vec_r = vector_score(record.record_id, query_embedding, record_embeddings or {})

    reasons.extend(text_r)
    reasons.extend(env_r)
    reasons.extend(ver_r)
    reasons.extend(tag_r)
    reasons.extend(con_r)
    reasons.extend(vec_r)

    total = 0.0
    total += text_s
    total += env_s * 4
    total += ver_s * 3
    total += tag_s * 3        # tag FTS: precise — high weight
    total += con_s * 1        # content FTS: broad — lower weight
    total += vec_s * 2        # semantic similarity
    total += VERIFICATION_SCORE[record.verification_level] * 2
    total += freshness_score(record)
    total += feedback_score(feedback_items)
    total -= RISK_PENALTY[record.risk_level] * 2
    total -= conflict_penalty(relations or []) * 2

    status_penalty, status_reasons = status_decay_penalty(record)
    total -= status_penalty
    reasons.extend(status_reasons)

    na_penalty, na_reasons = not_applicable_penalty(query, record)
    total -= na_penalty
    reasons.extend(na_reasons)

    if record.result.outcome.lower() in {"failure", "invalid"}:
        total -= 2.0

    return total, reasons
