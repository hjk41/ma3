"""
Journey 2: Human curator adds Q&A knowledge → agent finds it after promotion.

Scenario:
  A human knowledge curator uses the /knowledge endpoint to record a policy or
  specification.  The record is created at L0 (excluded from search) until the
  curator bumps verification_level to L1 via PATCH.  After that, agents can find
  it via /search.
"""
from __future__ import annotations

import pytest
from tests.conftest import make_knowledge_payload, make_search_payload


# ── J2-A: POST /knowledge creates L0 record ───────────────────────────────────

def test_knowledge_creates_l0_active_record(authed_client):
    resp = authed_client.post(
        "/knowledge",
        json=make_knowledge_payload(),
    )
    assert resp.status_code == 200
    record = resp.json()
    assert record["verification_level"] == "L0"
    assert record["status"] == "active"
    assert "timeout" in record["tags"]


# ── J2-B: L0 record does NOT appear in search ─────────────────────────────────

def test_l0_knowledge_not_in_search(authed_client):
    resp = authed_client.post("/knowledge", json=make_knowledge_payload())
    record_id = resp.json()["record_id"]

    search_resp = authed_client.post(
        "/search",
        json=make_search_payload(problem="default API timeout"),
    )
    primary_ids = [m["record"]["record_id"] for m in search_resp.json()["primary_records"]]
    assert record_id not in primary_ids


# ── J2-C: After PATCH to L1, record appears in search ─────────────────────────

def test_knowledge_searchable_after_verification_bump(authed_client):
    # Create L0 knowledge record
    record_id = authed_client.post(
        "/knowledge",
        json=make_knowledge_payload(
            question="What is the API rate limit?",
            summary="The API rate limit is 100 requests per minute.",
            tags=["rate-limit", "api"],
        ),
    ).json()["record_id"]

    # Bump to L1
    patch_resp = authed_client.patch(
        f"/records/{record_id}",
        json={"verification_level": "L1"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["verification_level"] == "L1"

    # Now should appear in search
    search_resp = authed_client.post(
        "/search",
        json=make_search_payload(problem="API rate limit exceeded"),
    )
    primary_ids = [m["record"]["record_id"] for m in search_resp.json()["primary_records"]]
    assert record_id in primary_ids


# ── J2-D: Knowledge record stores question + knowledge_kind ───────────────────

def test_knowledge_stores_q_and_a_fields(authed_client):
    resp = authed_client.post(
        "/knowledge",
        json=make_knowledge_payload(
            question="How long does onboarding take?",
            summary="Onboarding takes 3 business days.",
            knowledge_kind="process_protocol",
        ),
    )
    record = resp.json()
    assert record["question"] == "How long does onboarding take?"
    assert record["knowledge_kind"] == "process_protocol"
    assert record["source_type"] == "authority_defined"


# ── J2-E: Knowledge record rejects invalid knowledge_kind ─────────────────────

def test_knowledge_rejects_invalid_kind(authed_client):
    payload = make_knowledge_payload()
    payload["knowledge_kind"] = "not_a_valid_kind"
    resp = authed_client.post("/knowledge", json=payload)
    assert resp.status_code == 422


# ── J2-F: PATCH record with admin key works, with correct token works ──────────

def test_knowledge_patch_with_library_token(authed_client, lib_with_token):
    lib_id, token = lib_with_token
    headers = {"X-API-Key": token}

    # Create in the library
    record_id = authed_client.post(
        "/knowledge",
        json=make_knowledge_payload(),
        headers=headers,
    ).json()["record_id"]

    # PATCH with same library token
    patch_resp = authed_client.patch(
        f"/records/{record_id}",
        json={"verification_level": "L2"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["verification_level"] == "L2"


# ── J2-G: Reject / invalidate a knowledge record ──────────────────────────────

def test_reject_removes_record_from_search(authed_client):
    record_id = authed_client.post("/knowledge", json=make_knowledge_payload()).json()["record_id"]
    # Bump to L1 so it would normally appear
    authed_client.patch(f"/records/{record_id}", json={"verification_level": "L1"})

    # Reject it
    reject_resp = authed_client.patch(
        f"/records/{record_id}/reject",
        json={"review_note": "outdated information"},
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "invalid"

    # Should not appear in search
    search_resp = authed_client.post(
        "/search",
        json=make_search_payload(problem="default API timeout"),
    )
    primary_ids = [m["record"]["record_id"] for m in search_resp.json()["primary_records"]]
    assert record_id not in primary_ids
