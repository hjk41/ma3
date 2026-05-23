from __future__ import annotations

from tests.conftest import ADMIN_KEY


def test_issue_xyz_keys_admin_only(client):
    resp = client.post("/v3/admin/issue_xyz_keys", json={"usernames": ["alice"]})
    assert resp.status_code in (401, 403), resp.text


def test_issue_xyz_keys_admin_bulk(client):
    headers = {"X-API-Key": ADMIN_KEY}
    created = client.post(
        "/v3/libraries",
        json={"name": "xyz-test", "description": "", "is_public": False},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    body = created.json()
    lib_id = body.get("library_id") or body["library"]["library_id"]

    resp = client.post(
        "/v3/admin/issue_xyz_keys",
        json={"usernames": ["alice", "bob"], "xyz_library_id": lib_id},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {row["username"] for row in body["issued"]} == {"alice", "bob"}
    for row in body["issued"]:
        assert row["raw"]
        assert row["key_id"].startswith("akey_")
    assert body["failed"] == []
