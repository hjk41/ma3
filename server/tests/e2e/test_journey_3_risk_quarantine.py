"""
Journey 3: High-risk / critical content remains immediately written but still
requires manual review and is filtered appropriately from search.
"""
from __future__ import annotations

import pytest
from tests.conftest import make_ingest_payload, make_search_payload


# ── J3-A: Critical pattern → active + manual review ──────────────────────────

def test_critical_content_requires_manual_review_but_is_active(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}

    resp = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(
            problem="Needed to rm -rf the build artifacts to fix the pipeline",
            task_type="CI",
            actions=[{"action": "ran rm -rf build/", "note": "cleared stale cache"}],
        ),
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["requires_manual_review"] is True
    assert body["record"]["status"] == "active"
    assert body["record"]["risk_level"] == "critical"
    assert len(body["review_reasons"]) > 0


# ── J3-B: Critical record does NOT appear in search ───────────────────────────

def test_critical_record_absent_from_search(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}

    record_id = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(
            problem="used rm -rf to clean workspace",
            task_type="cleanup",
        ),
        headers=headers,
    ).json()["record"]["record_id"]

    search_resp = authed_client.post(
        "/search",
        json=make_search_payload(problem="clean workspace"),
        headers=headers,
    )
    all_ids = [
        m["record"]["record_id"]
        for m in search_resp.json()["primary_records"] + search_resp.json()["contrasting_records"]
    ]
    assert record_id not in all_ids


# ── J3-C: High-risk content (secrets) → active, manual_only ──────────────────

def test_high_risk_secrets_quarantined(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}

    resp = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(
            problem="Found the api_key exposed in logs",
            task_type="security",
        ),
        headers=headers,
    )
    body = resp.json()
    assert body["record"]["risk_level"] == "high"
    assert body["record"]["status"] == "active"
    assert body["requires_manual_review"] is True


# ── J3-D: Admin can view drafts via /libraries/{id}/drafts ────────────────────

def test_admin_can_view_draft_records(authed_client, lib_with_token):
    lib_id, token = lib_with_token
    headers = {"X-API-Key": token}

    # Create a critical record (now active but still marked critical/private)
    authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(problem="need to sudo run the deploy script"),
        headers=headers,
    )

    drafts_resp = authed_client.get(f"/libraries/{lib_id}/drafts", headers=headers)
    assert drafts_resp.status_code == 200
    drafts = drafts_resp.json()
    assert drafts == []


# ── J3-E: New writes are active immediately ───────────────────────────────────

def test_new_write_is_active_without_promotion(authed_client, lib_with_token):
    lib_id, token = lib_with_token
    headers = {"X-API-Key": token}

    resp = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(draft_only=True, tags=["promote-test"]),
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["record"]["status"] == "active"


# ── J3-F: Promoted critical record still excluded (risk_level=critical filter) ─

def test_critical_record_excluded_from_search_even_after_promotion(authed_client, lib_with_token):
    """Search explicitly filters risk_level=critical even if status is active."""
    _, token = lib_with_token
    headers = {"X-API-Key": token}

    record_id = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(
            problem="rm -rf build/",
            tags=["critical-search-test"],
        ),
        headers=headers,
    ).json()["record"]["record_id"]

    # Still should NOT appear in search (critical risk filter in search_service)
    search_resp = authed_client.post(
        "/search",
        json=make_search_payload(problem="build cleanup", tags=["critical-search-test"]),
        headers=headers,
    )
    all_ids = [
        m["record"]["record_id"]
        for m in search_resp.json()["primary_records"] + search_resp.json()["contrasting_records"]
    ]
    assert record_id not in all_ids
