"""Unit tests for the FTS helper functions in fts.py.

These tests use the real SQLite FTS5 engine via the temp DB created by
the _isolated_settings autouse fixture.
"""
from __future__ import annotations

import pytest

from app.models.common import ResultSummary, TargetRef
from app.models.enums import ExecutionMode, RecordStatus, RiskLevel, VerificationLevel, VisibilityScope
from app.models.record import Record
from app.storage.fts import fts_content_search, fts_tag_search, fts_upsert
from app.storage.repositories import RecordRepository
from app.storage.db import get_connection
from app.core.time import utc_now_iso


# ── Helpers ───────────────────────────────────────────────────────────────────

def _store_record(
    record_id: str = "r1",
    title: str = "Fix API timeout",
    summary: str = "Increase timeout to 30 seconds",
    claim: str = "Timeout of 30s resolves dropped connections",
    tags: list[str] | None = None,
    library_id: str | None = None,
    status: RecordStatus = RecordStatus.active,
) -> Record:
    record = Record(
        record_id=record_id,
        library_id=library_id,
        title=title,
        problem_family="timeout",
        summary=summary,
        claim=claim,
        tags=tags or ["timeout", "http"],
        target=TargetRef(product="api"),
        result=ResultSummary(outcome="success", summary="fixed"),
        status=status,
        verification_level=VerificationLevel.l1,
        visibility_scope=VisibilityScope.public,
        risk_level=RiskLevel.low,
        execution_mode=ExecutionMode.safe_to_apply,
        source_type="agent_ingest",
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    RecordRepository().insert(record)
    return record


# ── fts_upsert ────────────────────────────────────────────────────────────────

def test_fts_upsert_writes_tag_index():
    record = _store_record(tags=["timeout", "retry"])
    with get_connection() as conn:
        row = conn.execute(
            "SELECT tags FROM records_fts_tags WHERE record_id = ?",
            (record.record_id,),
        ).fetchone()
    assert row is not None
    assert "timeout" in row[0]
    assert "retry" in row[0]


def test_fts_upsert_writes_content_index():
    record = _store_record(title="Unique fts upsert title xyz123")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT title FROM records_fts_content WHERE record_id = ?",
            (record.record_id,),
        ).fetchone()
    assert row is not None
    assert "xyz123" in row[0]


def test_fts_upsert_idempotent():
    record = _store_record(record_id="r-idem", tags=["alpha"])
    # Insert again (simulate update)
    with get_connection() as conn:
        fts_upsert(conn, record)
    with get_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM records_fts_tags WHERE record_id = ?",
            (record.record_id,),
        ).fetchone()[0]
    assert count == 1  # no duplicates


# ── fts_tag_search ────────────────────────────────────────────────────────────

def test_fts_tag_search_finds_matching_record():
    _store_record(record_id="r-tag", tags=["timeout", "http"])
    results = fts_tag_search("timeout", set())
    ids = [r for r, _ in results]
    assert "r-tag" in ids


def test_fts_tag_search_no_match():
    _store_record(record_id="r-nomatch", tags=["database", "pool"])
    results = fts_tag_search("timeout", set())
    ids = [r for r, _ in results]
    assert "r-nomatch" not in ids


def test_fts_tag_search_returns_positive_scores():
    _store_record(record_id="r-pos", tags=["timeout"])
    results = fts_tag_search("timeout", set())
    for _, score in results:
        assert score > 0


def test_fts_tag_search_library_filter():
    """Records in inaccessible libraries should not appear."""
    _store_record(record_id="r-lib-a", tags=["secret"], library_id="lib-a")
    # No accessible libraries → only NULL-library records match
    results = fts_tag_search("secret", set())
    ids = [r for r, _ in results]
    assert "r-lib-a" not in ids


def test_fts_tag_search_library_filter_accessible():
    """Records in accessible libraries should appear."""
    _store_record(record_id="r-lib-b", tags=["topsecret"], library_id="lib-b")
    results = fts_tag_search("topsecret", {"lib-b"})
    ids = [r for r, _ in results]
    assert "r-lib-b" in ids


def test_fts_tag_search_special_chars_returns_empty():
    """FTS5 special characters in query should not raise, just return empty."""
    results = fts_tag_search("(weird OR)", set())
    assert results == []


def test_fts_tag_search_draft_excluded_by_default():
    """Drafts should not appear in active-only search."""
    _store_record(record_id="r-draft", tags=["draftonly"], status=RecordStatus.draft)
    results = fts_tag_search("draftonly", set())
    ids = [r for r, _ in results]
    assert "r-draft" not in ids


def test_fts_tag_search_draft_included_when_requested():
    _store_record(record_id="r-draft2", tags=["draftmatch"], status=RecordStatus.draft)
    results = fts_tag_search("draftmatch", set(), status_filter="draft")
    ids = [r for r, _ in results]
    assert "r-draft2" in ids


# ── fts_content_search ────────────────────────────────────────────────────────

def test_fts_content_search_finds_in_title():
    _store_record(
        record_id="r-ct",
        title="Zebra timeout workaround for slow connections",
    )
    results = fts_content_search("Zebra", set())
    ids = [r for r, _ in results]
    assert "r-ct" in ids


def test_fts_content_search_finds_in_summary():
    _store_record(
        record_id="r-cs",
        summary="Unique phrase xqzmaster in summary only",
    )
    results = fts_content_search("xqzmaster", set())
    ids = [r for r, _ in results]
    assert "r-cs" in ids


def test_fts_content_search_empty_query():
    _store_record(record_id="r-empty")
    results = fts_content_search("", set())
    assert results == []


def test_fts_tag_search_results_ordered_by_score():
    """Record with more/better tag match should rank first."""
    _store_record(record_id="r-low", tags=["timeout"])
    # Record with repeated tag mention ranks higher in BM25
    _store_record(record_id="r-high", tags=["timeout", "timeout", "timeout"])
    results = fts_tag_search("timeout", set())
    if len(results) >= 2:
        # First result should have higher score
        assert results[0][1] >= results[-1][1]
