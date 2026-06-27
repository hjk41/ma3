"""Unit tests for the knowledge-staleness curation lifecycle.

Covers:
  - scoring.status_decay_penalty + score_record soft-decay ordering
  - record_service transitions (mark_stale / supersede / restore) incl. guards
"""
from __future__ import annotations

import pytest

from app.core.time import utc_now_iso
from app.models.common import ResultSummary, TargetRef
from app.models.enums import RecordStatus, RelationType
from app.models.query import SearchQuery
from app.models.record import Record
from app.services import scoring
from app.services.record_service import (
    create_record,
    mark_record_stale,
    restore_record,
    supersede_record,
)
from app.storage.repositories import RecordRepository, RelationRepository


def _make_record(status: RecordStatus, record_id: str = "vk_test") -> Record:
    now = utc_now_iso()
    return Record(
        record_id=record_id,
        title="Increase HTTP client timeout",
        problem_family="api timeout",
        summary="Raising the timeout removed the recurring API timeout errors.",
        claim="Set timeout to 30s to stop API timeouts.",
        target=TargetRef(product="my-api", component="http-client"),
        result=ResultSummary(outcome="success", summary="errors stopped"),
        status=status,
        created_at=now,
        updated_at=now,
    )


# ── scoring.status_decay_penalty ──────────────────────────────────────────────

def test_status_decay_penalty_values():
    assert scoring.status_decay_penalty(_make_record(RecordStatus.active)) == (0.0, [])
    stale_penalty, stale_reasons = scoring.status_decay_penalty(_make_record(RecordStatus.stale))
    assert stale_penalty == 4.0
    assert stale_reasons and "stale" in stale_reasons[0]
    sup_penalty, sup_reasons = scoring.status_decay_penalty(_make_record(RecordStatus.superseded))
    assert sup_penalty == 8.0
    assert sup_reasons and "superseded" in sup_reasons[0]


def test_score_record_soft_decay_ordering():
    """Identical records must rank active > stale > superseded."""
    query = SearchQuery(
        problem="API timeout errors",
        query_intent="fix",
        task_type="troubleshooting",
        target=TargetRef(product="my-api"),
        goal="stop timeouts",
    )
    active_score, _ = scoring.score_record(query, _make_record(RecordStatus.active), [])
    stale_score, stale_reasons = scoring.score_record(query, _make_record(RecordStatus.stale), [])
    sup_score, _ = scoring.score_record(query, _make_record(RecordStatus.superseded), [])

    assert active_score > stale_score > sup_score
    assert active_score - stale_score == pytest.approx(4.0)
    assert active_score - sup_score == pytest.approx(8.0)
    assert any("status decay" in r for r in stale_reasons)


# ── record_service transitions ────────────────────────────────────────────────

def _insert_active(tag: str = "curation") -> Record:
    from app.models.record import RecordCreate

    rc = RecordCreate(
        title="timeout fix",
        problem_family="api timeout",
        summary="raise timeout",
        claim="set timeout 30s",
        target=TargetRef(product="my-api", component="http-client"),
        result=ResultSummary(outcome="success", summary="ok"),
        tags=[tag],
    )
    return create_record(rc)


def test_mark_stale_then_restore_roundtrip():
    rec = _insert_active()
    assert rec.status == RecordStatus.active

    staled = mark_record_stale(rec, review_note="outdated runtime")
    assert staled.status == RecordStatus.stale
    assert RecordRepository().get(rec.record_id).status == RecordStatus.stale

    restored = restore_record(staled, review_note="still valid")
    assert restored.status == RecordStatus.active
    assert RecordRepository().get(rec.record_id).status == RecordStatus.active


def test_supersede_creates_relation_and_decays_old():
    old = _insert_active("old")
    new = _insert_active("new")

    updated, relation = supersede_record(old, superseded_by=new.record_id, review_note="replaced")
    assert updated.status == RecordStatus.superseded
    assert relation.relation_type == RelationType.supersedes
    assert relation.from_record_id == new.record_id
    assert relation.to_record_id == old.record_id

    # Relation is persisted and discoverable from the old record.
    rels = RelationRepository().list_by_record(old.record_id)
    assert any(r.relation_id == relation.relation_id for r in rels)


def test_supersede_self_is_rejected():
    rec = _insert_active()
    with pytest.raises(ValueError):
        supersede_record(rec, superseded_by=rec.record_id)


def test_supersede_unknown_target_is_rejected():
    rec = _insert_active()
    with pytest.raises(ValueError):
        supersede_record(rec, superseded_by="vk_does_not_exist")


def test_invalid_transitions_are_rejected():
    rec = _insert_active()
    # Cannot restore an active record.
    with pytest.raises(ValueError):
        restore_record(rec)
    # Cannot supersede an already-superseded record.
    other = _insert_active("other")
    superseded, _ = supersede_record(rec, superseded_by=other.record_id)
    with pytest.raises(ValueError):
        supersede_record(superseded, superseded_by=other.record_id)
    # But a superseded record can be marked stale, then restored.
    staled = mark_record_stale(superseded)
    assert staled.status == RecordStatus.stale
