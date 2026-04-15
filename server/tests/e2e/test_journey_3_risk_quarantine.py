"""
Journey 3: High-risk / critical content is quarantined to draft.

Scenario:
  An agent submits a report that contains critical patterns (rm -rf, sudo).
  The system automatically quarantines it as a draft, flags it for manual review,
  and ensures it does NOT appear in search.  An admin can see it in drafts and
  can promote or reject it.
"""
from __future__ import annotations

import pytest
from tests.conftest import make_ingest_payload, make_search_payload


# ── J3-A: Critical pattern → draft, requires_manual_review ───────────────────

def test_critical_content_quarantined_as_draft(authed_client, lib_with_token):
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
    assert body["record"]["status"] == "draft"
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


# ── J3-C: High-risk content (secrets) → draft, manual_only ───────────────────

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
    assert body["record"]["status"] == "draft"
    assert body["requires_manual_review"] is True


# ── J3-D: Admin can view drafts via /libraries/{id}/drafts ────────────────────

def test_admin_can_view_draft_records(authed_client, lib_with_token):
    lib_id, token = lib_with_token
    headers = {"X-API-Key": token}

    # Create a critical record (goes to draft)
    authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(problem="need to sudo run the deploy script"),
        headers=headers,
    )

    drafts_resp = authed_client.get(f"/libraries/{lib_id}/drafts", headers=headers)
    assert drafts_resp.status_code == 200
    drafts = drafts_resp.json()
    assert any(d["status"] == "draft" for d in drafts)


# ── J3-E: Admin promotes draft → record becomes active ────────────────────────

def test_admin_promotes_draft_to_active(authed_client, lib_with_token):
    lib_id, token = lib_with_token
    headers = {"X-API-Key": token}

    record_id = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(draft_only=True, tags=["promote-test"]),
        headers=headers,
    ).json()["record"]["record_id"]

    # Promote (using admin key — library admin)
    promote_resp = authed_client.patch(
        f"/records/{record_id}/promote",
        json={"review_note": "looks good, approved"},
    )
    assert promote_resp.status_code == 200
    assert promote_resp.json()["status"] == "active"


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

    # Force promote to active
    authed_client.patch(f"/records/{record_id}/promote")

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
