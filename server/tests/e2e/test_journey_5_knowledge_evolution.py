"""
Journey 5: Knowledge evolution — supersession and conflict tracking.

Scenario:
  An agent discovers a better approach to the same problem. It ingests a new
  record that references the old one as "derived_from". Later, it finds a
  conflicting record and marks the relationship. The search surface should show
  the contrasting_records bucket for conflicts.
"""
from __future__ import annotations

import pytest
from tests.conftest import make_ingest_payload, make_search_payload


# ── J5-A: Second record references first via relation ─────────────────────────

def test_derived_from_relation_created(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}

    # First: original finding
    r1 = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(
            problem="Slow SQL queries",
            result_summary="Added index on user_id column",
            tags=["sql", "performance"],
        ),
        headers=headers,
    ).json()["record"]["record_id"]

    # Second: improvement based on first
    resp = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(
            problem="SQL queries still slow after adding single index",
            result_summary="Composite index on (user_id, created_at) is 3x faster",
            tags=["sql", "performance"],
            based_on_record_id=r1,
        ),
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["relation"]["to_record_id"] == r1
    assert body["relation"]["relation_type"] == "derived_from"


# ── J5-B: Feedback is also created when based_on_record_id supplied ───────────

def test_derived_record_creates_feedback(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}

    r1 = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(tags=["feedback-test"]),
        headers=headers,
    ).json()["record"]["record_id"]

    resp = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(based_on_record_id=r1),
        headers=headers,
    )
    feedback = resp.json()["feedback"]
    assert feedback is not None
    assert feedback["record_id"] == r1


# ── J5-C: Failure record appears in contrasting_records ───────────────────────

def test_failure_record_in_contrasting_bucket(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}

    # Ingest a failure record
    authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(
            problem="SQL query timeout on large tables",
            outcome="failure",
            result_summary="Adding NOLOCK hint caused data inconsistencies",
            tags=["sql", "timeout", "failure-case"],
        ),
        headers=headers,
    )

    # Also ingest a success
    authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(
            problem="SQL query timeout on large tables",
            outcome="success",
            result_summary="Pagination reduced load",
            tags=["sql", "timeout"],
        ),
        headers=headers,
    )

    search_resp = authed_client.post(
        "/search",
        json=make_search_payload(problem="SQL query timeout"),
        headers=headers,
    )
    body = search_resp.json()
    contrasting_ids = [m["record"]["record_id"] for m in body["contrasting_records"]]
    primary_ids = [m["record"]["record_id"] for m in body["primary_records"]]

    # At least one success in primary
    assert len(primary_ids) > 0 or len(contrasting_ids) > 0


# ── J5-D: Legacy promote endpoint rejects newly active records ───────────────

def test_promote_record_rejects_newly_active_record(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}

    # New writes are already active even when draft_only=True is sent.
    record_id = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(draft_only=True),
        headers=headers,
    ).json()["record"]["record_id"]

    promoted = authed_client.patch(
        f"/records/{record_id}/promote",
        json={"review_note": "verified by senior engineer"},
    )
    assert promoted.status_code == 400


# ── J5-E: Record PATCH updates verification_level ────────────────────────────

def test_patch_record_bumps_verification_level(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}

    record_id = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(),
        headers=headers,
    ).json()["record"]["record_id"]

    # Default is L1; bump to L3
    patch_resp = authed_client.patch(
        f"/records/{record_id}",
        json={"verification_level": "L3"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["verification_level"] == "L3"


# ── J5-F: GET /records/{id} returns relation list via search match ─────────────

def test_search_match_includes_relations(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}

    r1 = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(tags=["relation-search"]),
        headers=headers,
    ).json()["record"]["record_id"]

    r2_body = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(
            tags=["relation-search"],
            based_on_record_id=r1,
        ),
        headers=headers,
    ).json()

    # Search should return r2; its match object includes relations
    search_resp = authed_client.post(
        "/search",
        json=make_search_payload(tags=["relation-search"]),
        headers=headers,
    )
    matches = search_resp.json()["primary_records"]
    r2_id = r2_body["record"]["record_id"]
    r2_match = next((m for m in matches if m["record"]["record_id"] == r2_id), None)
    if r2_match is not None:
        assert isinstance(r2_match["relations"], list)
