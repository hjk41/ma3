from __future__ import annotations

from app.core.auth import VerifyResult
from app.storage.repositories import PrincipalRepository


def test_v3_whoami_anonymous(client):
    resp = client.get("/v3/auth/whoami")
    assert resp.status_code == 200
    body = resp.json()
    assert body["via"] == "anonymous"
    assert body["principal"]["kind"] == "anonymous"


def test_v3_whoami_admin(authed_client):
    resp = authed_client.get("/v3/auth/whoami")
    assert resp.status_code == 200
    body = resp.json()
    assert body["via"] == "admin_key"
    assert body["admin_bypass"] is True


def test_issue_and_use_scoped_key_with_sso_cookie(client, monkeypatch):
    monkeypatch.setattr(
        "app.core.auth.verify_sso_cookie",
        lambda jwt: VerifyResult(user="alice", display_name="Alice"),
    )
    cookies = {"gateway_token": "cookie"}
    created = client.post("/v3/libraries", json={"name": "alice", "is_public": False}, cookies=cookies)
    assert created.status_code == 200
    lib_id = created.json()["library"]["library_id"]
    issued = client.post(
        "/v3/auth/keys",
        json={"label": "agent", "scope_libraries": [lib_id]},
        cookies=cookies,
    )
    assert issued.status_code == 200
    raw = issued.json()["raw"]
    who = client.get("/v3/auth/whoami", headers={"X-API-Key": raw}).json()
    assert who["principal"]["principal_id"] == "user:alice"
    assert [item["library_id"] for item in who["libraries"]] == [lib_id]


def test_grant_and_revoke_acl_changes_whoami(client, monkeypatch):
    monkeypatch.setattr(
        "app.core.auth.verify_sso_cookie",
        lambda jwt: VerifyResult(user="alice", display_name="Alice"),
    )
    cookies = {"gateway_token": "cookie"}
    lib = client.post("/v3/libraries", json={"name": "team", "is_public": False}, cookies=cookies).json()["library"]
    PrincipalRepository().upsert_user("bob", "Bob")
    grant = client.put(
        f"/v3/libraries/{lib['library_id']}/acl/user:bob",
        json={"role": "reader"},
        cookies=cookies,
    )
    assert grant.status_code == 200
    assert grant.json()["role"] == "reader"
    acl = client.get(f"/v3/libraries/{lib['library_id']}/acl", cookies=cookies).json()
    assert any(item["principal_id"] == "user:bob" for item in acl)
    delete = client.delete(f"/v3/libraries/{lib['library_id']}/acl/user:bob", cookies=cookies)
    assert delete.status_code == 204
