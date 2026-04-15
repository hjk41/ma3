"""
Journey 1: Agent experience ingest → second agent reuses via search.

Scenario:
  An agent encounters a timeout issue, solves it, and ingests the experience
  with tags.  A second agent with the same problem searches and finds it.
  The second agent then builds on the first record (based_on_record_id).
"""
from __future__ import annotations

import pytest
from tests.conftest import make_ingest_payload, make_search_payload

HEADERS_WRITER = {}  # set per test from lib_with_token


# ── J1-A: Ingest creates record with tags ─────────────────────────────────────

def test_ingest_creates_record_with_tags(authed_client, lib_with_token):
    lib_id, token = lib_with_token
    headers = {"X-API-Key": token}

    resp = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(tags=["timeout", "http-client"]),
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["persisted"] is True
    assert body["requires_manual_review"] is False
    record = body["record"]
    assert "timeout" in record["tags"]
    assert "http-client" in record["tags"]
    assert record["library_id"] == lib_id


# ── J1-B: Ingested record appears in search ────────────────────────────────────

def test_ingested_record_found_in_search(authed_client, lib_with_token):
    lib_id, token = lib_with_token
    headers = {"X-API-Key": token}

    # Ingest
    ingest_resp = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(tags=["timeout", "http-client"]),
        headers=headers,
    )
    record_id = ingest_resp.json()["record"]["record_id"]

    # Search
    search_resp = authed_client.post(
        "/search",
        json=make_search_payload(problem="API call times out"),
        headers=headers,
    )
    assert search_resp.status_code == 200
    primary_ids = [m["record"]["record_id"] for m in search_resp.json()["primary_records"]]
    assert record_id in primary_ids


# ── J1-C: Search with explicit tag filter finds the record ────────────────────

def test_explicit_tag_filter_finds_record(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}

    authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(tags=["uniquetag-abc123"]),
        headers=headers,
    )

    search_resp = authed_client.post(
        "/search",
        json=make_search_payload(problem="any problem", tags=["uniquetag-abc123"]),
        headers=headers,
    )
    primary_ids_with_tags = [
        m["record"]["record_id"]
        for m in search_resp.json()["primary_records"]
    ]
    assert len(primary_ids_with_tags) > 0


# ── J1-D: Second agent ingests a follow-up referencing the first record ────────

def test_based_on_record_creates_feedback_and_relation(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}

    # First ingest
    first = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(),
        headers=headers,
    ).json()["record"]["record_id"]

    # Second ingest referencing first
    second_resp = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(
            problem="API still times out on long requests",
            result_summary="Used streaming instead of full response, problem solved",
            based_on_record_id=first,
        ),
        headers=headers,
    )
    assert second_resp.status_code == 200
    body = second_resp.json()
    assert body["feedback"] is not None
    assert body["relation"] is not None
    assert body["relation"]["from_record_id"] == body["record"]["record_id"]
    assert body["relation"]["to_record_id"] == first


# ── J1-E: dry_run does not persist ────────────────────────────────────────────

def test_dry_run_does_not_persist(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}

    resp = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(dry_run=True),
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["persisted"] is False
    assert body["dry_run"] is True

    # Confirm it's not in the DB
    record_id = body["record"]["record_id"]
    get_resp = authed_client.get(f"/records/{record_id}", headers=headers)
    assert get_resp.status_code == 404


# ── J1-F: draft_only flag sets status to draft ────────────────────────────────

def test_draft_only_creates_draft_record(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}

    resp = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(draft_only=True),
        headers=headers,
    )
    assert resp.status_code == 200
    record = resp.json()["record"]
    assert record["status"] == "draft"

    # Draft should not appear in search
    search_resp = authed_client.post(
        "/search",
        json=make_search_payload(),
        headers=headers,
    )
    primary_ids = [m["record"]["record_id"] for m in search_resp.json()["primary_records"]]
    assert record["record_id"] not in primary_ids
