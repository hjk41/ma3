from __future__ import annotations

from app.core.auth import VerifyResult
from app.storage.repositories import PrincipalRepository


def test_v3_library_acl_requires_admin(client, monkeypatch):
    monkeypatch.setattr("app.core.auth.verify_sso_cookie", lambda jwt: VerifyResult(user="owner", display_name="Owner"))
    owner_cookie = {"gateway_token": "owner-cookie"}
    lib = client.post("/v3/libraries", json={"name": "owned", "is_public": False}, cookies=owner_cookie).json()["library"]
    PrincipalRepository().upsert_user("reader", "Reader")
    assert client.put(
        f"/v3/libraries/{lib['library_id']}/acl/user:reader",
        json={"role": "reader"},
        cookies=owner_cookie,
    ).status_code == 200

    monkeypatch.setattr("app.core.auth.verify_sso_cookie", lambda jwt: VerifyResult(user="reader", display_name="Reader"))
    reader_cookie = {"gateway_token": "reader-cookie"}
    denied = client.put(
        f"/v3/libraries/{lib['library_id']}/acl/user:owner",
        json={"role": "reader"},
        cookies=reader_cookie,
    )
    assert denied.status_code == 403


def test_cannot_remove_last_admin(client, monkeypatch):
    monkeypatch.setattr("app.core.auth.verify_sso_cookie", lambda jwt: VerifyResult(user="owner", display_name="Owner"))
    cookies = {"gateway_token": "owner-cookie"}
    lib = client.post("/v3/libraries", json={"name": "owned", "is_public": False}, cookies=cookies).json()["library"]
    resp = client.delete(f"/v3/libraries/{lib['library_id']}/acl/user:owner", cookies=cookies)
    assert resp.status_code == 409
