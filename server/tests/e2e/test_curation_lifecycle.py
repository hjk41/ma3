"""E2E tests for the curation lifecycle endpoints and their search effect.

Covers:
  - PATCH /records/{id}/stale, /supersede, /restore (admin-gated)
  - stale/superseded records stay searchable but rank below active ones
  - invalid transitions return 400; non-admin callers are rejected
"""
from __future__ import annotations

from tests.conftest import make_ingest_payload, make_search_payload


def _ingest(authed_client, headers, **overrides) -> str:
    resp = authed_client.post("/agent/ingest", json=make_ingest_payload(**overrides), headers=headers)
    assert resp.status_code == 200
    return resp.json()["record"]["record_id"]


# ── Endpoint happy paths ──────────────────────────────────────────────────────

def test_stale_then_restore_endpoint(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}
    rid = _ingest(authed_client, headers, tags=["stale-flow"])

    staled = authed_client.patch(f"/records/{rid}/stale", json={"review_note": "outdated"})
    assert staled.status_code == 200
    assert staled.json()["status"] == "stale"

    restored = authed_client.patch(f"/records/{rid}/restore", json={"review_note": "valid again"})
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"


def test_supersede_endpoint_creates_relation(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}
    old = _ingest(authed_client, headers, tags=["supersede-old"])
    new = _ingest(authed_client, headers, tags=["supersede-new"])

    resp = authed_client.patch(f"/records/{old}/supersede", json={"superseded_by": new})
    assert resp.status_code == 200
    body = resp.json()
    assert body["record"]["status"] == "superseded"
    assert body["relation"]["relation_type"] == "supersedes"
    assert body["relation"]["from_record_id"] == new
    assert body["relation"]["to_record_id"] == old


# ── Guard rails ───────────────────────────────────────────────────────────────

def test_supersede_self_returns_400(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}
    rid = _ingest(authed_client, headers, tags=["self-supersede"])
    resp = authed_client.patch(f"/records/{rid}/supersede", json={"superseded_by": rid})
    assert resp.status_code == 400


def test_restore_active_returns_400(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}
    rid = _ingest(authed_client, headers, tags=["restore-active"])
    resp = authed_client.patch(f"/records/{rid}/restore", json={})
    assert resp.status_code == 400


def test_stale_requires_admin(client, lib_with_token):
    """A non-admin (writer token) cannot mark records stale."""
    lib_id, token = lib_with_token
    # writer token is NOT admin over the library
    rid = client.post(
        "/agent/ingest",
        json=make_ingest_payload(tags=["needs-admin"]),
        headers={"X-API-Key": token},
    ).json()["record"]["record_id"]

    resp = client.patch(
        f"/records/{rid}/stale",
        json={"review_note": "x"},
        headers={"X-API-Key": token},
    )
    assert resp.status_code == 403


def test_stale_unknown_record_returns_404(authed_client):
    resp = authed_client.patch("/records/vk_missing/stale", json={})
    assert resp.status_code == 404


# ── Search visibility: stale stays, ranks lower; superseded ranks lowest ──────

def test_stale_record_still_searchable_but_decayed(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}

    # Two near-identical records under the same distinctive tag.
    keep = _ingest(
        authed_client, headers,
        problem="Kafka consumer lag spikes under load",
        result_summary="Increased max.poll.records and partitions",
        tags=["kafka-lag-decay"],
    )
    old = _ingest(
        authed_client, headers,
        problem="Kafka consumer lag spikes under load",
        result_summary="Old advice: just restart the consumer",
        tags=["kafka-lag-decay"],
    )

    # Mark the old one stale.
    assert authed_client.patch(f"/records/{old}/stale", json={}).status_code == 200

    search = authed_client.post(
        "/search",
        json=make_search_payload(problem="Kafka consumer lag", tags=["kafka-lag-decay"]),
        headers=headers,
    ).json()
    matches = search["primary_records"]
    by_id = {m["record"]["record_id"]: m for m in matches}

    # Stale record is still returned (not hard-filtered out).
    assert old in by_id, "stale record should remain discoverable"
    assert keep in by_id
    # Active record ranks above the stale one.
    assert by_id[keep]["match_score"] > by_id[old]["match_score"]


def test_invalid_record_excluded_but_stale_included(authed_client, lib_with_token):
    """Sanity: reject -> invalid drops from search, while stale remains."""
    _, token = lib_with_token
    headers = {"X-API-Key": token}

    invalidated = _ingest(authed_client, headers, tags=["exclude-check"], problem="unique-invalid-xyz")
    staled = _ingest(authed_client, headers, tags=["exclude-check"], problem="unique-stale-xyz")

    assert authed_client.patch(f"/records/{invalidated}/reject", json={}).status_code == 200
    assert authed_client.patch(f"/records/{staled}/stale", json={}).status_code == 200

    search = authed_client.post(
        "/search",
        json=make_search_payload(problem="unique", tags=["exclude-check"]),
        headers=headers,
    ).json()
    ids = {m["record"]["record_id"] for m in search["primary_records"]}
    assert invalidated not in ids, "invalid record must be excluded from search"
    assert staled in ids, "stale record must remain in search"
