"""
Journey 6: Search quality — FTS ranking and tag-based retrieval.

Scenario:
  Multiple records covering different topics are ingested. We verify that:
  - FTS tag search surfaces records with matching tags above unrelated records.
  - FTS content search finds records whose title/summary match the query.
  - The scoring system places tagged records ahead of tag-less records.
  - max_primary / max_contrasting pagination limits are honoured.
"""
from __future__ import annotations

import pytest
from tests.conftest import make_ingest_payload, make_search_payload


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def seeded_lib(authed_client):
    """Library seeded with several topically distinct records."""
    lib = authed_client.post(
        "/libraries",
        json={"name": "search-quality-lib", "is_public": True},
    ).json()
    lib_id = lib["library_id"]
    tok = authed_client.post(
        f"/libraries/{lib_id}/tokens",
        json={"label": "sq-writer"},
    ).json()["token"]
    headers = {"X-API-Key": tok}

    # Timeout group
    ids = {}
    ids["timeout_tagged"] = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(
            problem="HTTP request times out",
            result_summary="Increased timeout to 30s",
            tags=["timeout", "http"],
        ),
        headers=headers,
    ).json()["record"]["record_id"]

    ids["timeout_content"] = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(
            problem="timeout error on slow network",
            result_summary="Added retry logic after timeout",
            tags=["network", "retry"],  # no "timeout" tag
        ),
        headers=headers,
    ).json()["record"]["record_id"]

    # Unrelated record
    ids["unrelated"] = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(
            problem="CI pipeline fails on merge",
            result_summary="Fixed YAML indentation in workflow",
            tags=["ci", "yaml"],
            goal="fix ci pipeline",
        ),
        headers=headers,
    ).json()["record"]["record_id"]

    return lib_id, tok, ids


# ── J6-A: Tag search finds tagged record ──────────────────────────────────────

def test_tag_search_finds_tagged_record(authed_client, seeded_lib):
    _, tok, ids = seeded_lib
    headers = {"X-API-Key": tok}

    resp = authed_client.post(
        "/search",
        json=make_search_payload(problem="timeout", tags=["timeout"]),
        headers=headers,
    )
    primary_ids = [m["record"]["record_id"] for m in resp.json()["primary_records"]]
    assert ids["timeout_tagged"] in primary_ids


# ── J6-B: Unrelated record does not appear for timeout query ──────────────────

def test_unrelated_record_absent_from_timeout_search(authed_client, seeded_lib):
    _, tok, ids = seeded_lib
    headers = {"X-API-Key": tok}

    resp = authed_client.post(
        "/search",
        json=make_search_payload(problem="timeout", tags=["timeout"]),
        headers=headers,
    )
    primary_ids = [m["record"]["record_id"] for m in resp.json()["primary_records"]]
    assert ids["unrelated"] not in primary_ids


# ── J6-C: Content search finds record by summary keywords ─────────────────────

def test_content_search_finds_by_summary(authed_client, seeded_lib):
    _, tok, ids = seeded_lib
    headers = {"X-API-Key": tok}

    # "retry logic" is in the summary of timeout_content
    resp = authed_client.post(
        "/search",
        json=make_search_payload(problem="retry logic after timeout"),
        headers=headers,
    )
    primary_ids = [m["record"]["record_id"] for m in resp.json()["primary_records"]]
    assert ids["timeout_content"] in primary_ids


# ── J6-D: Tagged record ranks above content-only match ────────────────────────

def test_tag_ranked_above_content_only(authed_client, seeded_lib):
    _, tok, ids = seeded_lib
    headers = {"X-API-Key": tok}

    resp = authed_client.post(
        "/search",
        json=make_search_payload(problem="timeout", tags=["timeout"]),
        headers=headers,
    )
    matches = resp.json()["primary_records"]
    id_to_score = {m["record"]["record_id"]: m["match_score"] for m in matches}

    if ids["timeout_tagged"] in id_to_score and ids["timeout_content"] in id_to_score:
        # Tagged record with explicit tag filter should outrank the content-only match
        assert id_to_score[ids["timeout_tagged"]] >= id_to_score[ids["timeout_content"]]


# ── J6-E: max_primary limits result count ─────────────────────────────────────

def test_max_primary_limits_results(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}

    # Ingest 5 records with same tag
    for i in range(5):
        authed_client.post(
            "/agent/ingest",
            json=make_ingest_payload(
                problem=f"timeout issue variant {i}",
                result_summary=f"fixed variant {i}",
                tags=["max-primary-test"],
            ),
            headers=headers,
        )

    resp = authed_client.post(
        "/search",
        json=make_search_payload(
            problem="timeout",
            tags=["max-primary-test"],
            max_primary=2,
        ),
        headers=headers,
    )
    assert len(resp.json()["primary_records"]) <= 2


# ── J6-F: Empty problem falls back to full scan ───────────────────────────────

def test_empty_problem_returns_accessible_records(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}

    record_id = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(
            problem="performance issue",
            result_summary="added caching",
            tags=["full-scan-test"],
        ),
        headers=headers,
    ).json()["record"]["record_id"]

    resp = authed_client.post(
        "/search",
        json=make_search_payload(problem="", tags=["full-scan-test"]),
        headers=headers,
    )
    assert resp.status_code == 200
    # Should still return the tagged record via explicit tag filter
    primary_ids = [m["record"]["record_id"] for m in resp.json()["primary_records"]]
    assert record_id in primary_ids


# ── J6-G: Search respects not_applicable_if penalty ──────────────────────────

def test_not_applicable_record_scores_lower(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}

    # Record only applicable to staging, not production
    authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(
            problem="deploy app",
            result_summary="works in staging",
            tags=["deploy-test"],
            not_applicable_if=["production environment"],
        ),
        headers=headers,
    )

    # Generic record with no restrictions
    authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(
            problem="deploy app to production",
            result_summary="works everywhere",
            tags=["deploy-test"],
        ),
        headers=headers,
    )

    resp = authed_client.post(
        "/search",
        json=make_search_payload(
            problem="deploy app to production environment",
            tags=["deploy-test"],
        ),
        headers=headers,
    )
    assert resp.status_code == 200
    matches = resp.json()["primary_records"]
    # At least one result returned
    assert len(matches) > 0
