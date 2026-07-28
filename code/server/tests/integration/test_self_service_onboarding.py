from __future__ import annotations

import pytest

from app.auth.session import SessionUser
from app.core.config import settings
from app.services import api_key_service
from app.services.onboarding_service import ensure_personal_library
from app.services.principal_service import complete_display_name_setup, ensure_user_principal
from app.storage import db
from tests.helpers.mcp_client import McpClient

_EVIDENCE = [{"kind": "test", "summary": "self-service onboarding"}]
_ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture()
def session_user() -> SessionUser:
    return SessionUser(
        principal_id="user:onboard-a",
        sub="onboard-a",
        display_name="Onboard A",
        email=None,
        phone=None,
        is_admin=False,
    )


@pytest.fixture()
def authing_client(isolated_client, monkeypatch, session_user):
    monkeypatch.setattr(settings, "authing_enabled", True)
    monkeypatch.setattr(settings, "authing_issuer", "https://example.authing.cn")
    monkeypatch.setattr(settings, "authing_app_id", "test-app")
    monkeypatch.setattr(settings, "authing_app_secret", "test-secret")
    monkeypatch.setattr(settings, "max_keys_per_principal", 10)

    import app.api.routes_keys as routes_keys
    import app.auth.session as session_mod
    import app.services.portal_actor_service as portal_actor_service

    resolver = lambda _req: session_user
    monkeypatch.setattr(session_mod, "resolve_session_user", resolver)
    monkeypatch.setattr(routes_keys, "resolve_session_user", resolver)
    monkeypatch.setattr(portal_actor_service, "resolve_session_user", resolver)
    db.upsert_user_principal(sso_user=session_user.sub, display_name=session_user.sub)
    complete_display_name_setup(session_user.principal_id, session_user.display_name)
    ensure_personal_library(session_user.principal_id, session_user.display_name)
    return isolated_client


def test_callback_hook_provisions_personal_library(isolated_client, monkeypatch):
    from app.auth.authing_client import AuthingUser

    user = AuthingUser(
        sub="hook-user",
        display_name="Hook User",
        email=None,
        phone=None,
        username="hook-user",
        photo=None,
        is_admin=False,
    )
    principal = ensure_user_principal(user)
    ensure_personal_library(principal["principal_id"], user.display_name)
    lib = db.find_personal_library(principal["principal_id"])
    assert lib is not None
    assert lib["kind"] == "personal"


def test_api_keys_require_session(isolated_client, monkeypatch):
    monkeypatch.setattr(settings, "authing_enabled", True)
    monkeypatch.setattr(settings, "authing_issuer", "https://example.authing.cn")
    monkeypatch.setattr(settings, "authing_app_id", "test-app")
    monkeypatch.setattr(settings, "authing_app_secret", "test-secret")
    assert isolated_client.get("/api/keys").status_code == 401
    ui = isolated_client.get("/ui/keys/", follow_redirects=False)
    assert ui.status_code == 302


def test_authing_disabled_returns_503(isolated_client, monkeypatch):
    monkeypatch.setattr(settings, "authing_enabled", False)
    monkeypatch.setattr(settings, "local_auth", False)
    resp = isolated_client.get("/api/keys")
    assert resp.status_code == 503


def test_create_key_plaintext_listable(authing_client, session_user):
    client = authing_client
    created = client.post("/api/keys", json={"label": "laptop"}, headers=_ORIGIN)
    assert created.status_code == 200
    body = created.json()
    assert body["plaintext_key"].startswith("ma3k_")
    assert body["key_prefix"] == body["plaintext_key"][:12]

    listed = client.get("/api/keys")
    assert listed.status_code == 200
    keys = listed.json()["keys"]
    match = next(k for k in keys if k["key_id"] == body["key_id"])
    assert match["plaintext_key"] == body["plaintext_key"]
    assert "key_hash" not in body
    assert "key_ciphertext" not in match


def test_mcp_roundtrip_with_created_key(authing_client, session_user):
    client = authing_client
    created = client.post("/api/keys", json={"label": "agent"}, headers=_ORIGIN).json()
    plaintext = created["plaintext_key"]
    mcp = McpClient(client, api_key=plaintext)

    who = mcp.structured("ma3_whoami")
    assert settings.default_library_id in who["readable_library_ids"]
    personal = db.find_personal_library(session_user.principal_id)
    assert personal is not None
    assert personal["library_id"] in who["writable_library_ids"]

    report = mcp.structured(
        "ma3_report",
        {
            "problem": "personal default write",
            "outcome": "resolved",
            "result_summary": "implicit personal",
            "report_kind": "new",
            "based_on_record_ids": [],
            "evidence": _EVIDENCE,
        },
    )
    assert report["library_id"] == personal["library_id"]
    assert report["confirmation"] == "agent_judged"
    assert report["library_selection_reason"] == "default_owned_personal_library"

    public = mcp.structured(
        "ma3_report",
        {
            "problem": "explicit public write",
            "outcome": "resolved",
            "result_summary": "community",
            "library_id": settings.default_library_id,
            "based_on_record_ids": [],
            "evidence": _EVIDENCE,
        },
    )
    assert public["library_id"] == settings.default_library_id
    assert public["library_selection_reason"] == "explicit_library_id"


def test_delete_key_blocks_mcp(authing_client, session_user):
    client = authing_client
    created = client.post("/api/keys", json={"label": "delete-me"}, headers=_ORIGIN).json()
    key_id = created["key_id"]
    plaintext = created["plaintext_key"]
    deleted = client.delete(f"/api/keys/{key_id}", headers=_ORIGIN)
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert api_key_service.resolve_api_key(plaintext) is None
    assert db.get_api_key_for_principal(key_id, principal_id=session_user.principal_id) is None

    err = McpClient(client, api_key=plaintext).rpc(
        "tools/call",
        {"name": "ma3_whoami", "arguments": {}},
        expect_error=True,
    )
    assert err["code"] == -32001


def test_delete_key_hard_deletes_grants(authing_client, session_user):
    client = authing_client
    created = client.post("/api/keys", json={"label": "grants-gone"}, headers=_ORIGIN).json()
    key_id = created["key_id"]
    assert db.get_api_key_grants(key_id)
    client.delete(f"/api/keys/{key_id}", headers=_ORIGIN)
    assert db.get_api_key_grants(key_id) == []


def test_update_key_label(authing_client, session_user):
    client = authing_client
    created = client.post("/api/keys", json={"label": "old-label"}, headers=_ORIGIN).json()
    key_id = created["key_id"]
    updated = client.patch(f"/api/keys/{key_id}", json={"label": "new-label"}, headers=_ORIGIN)
    assert updated.status_code == 200
    assert updated.json()["label"] == "new-label"
    assert api_key_service.resolve_api_key(created["plaintext_key"]) is not None


def test_delete_key_owner_only(authing_client, session_user, monkeypatch):
    client = authing_client
    created = client.post("/api/keys", json={"label": "owner-only"}, headers=_ORIGIN).json()
    key_id = created["key_id"]

    other = SessionUser(
        principal_id="user:onboard-b",
        sub="onboard-b",
        display_name="Onboard B",
        email=None,
        phone=None,
        is_admin=False,
    )
    db.upsert_user_principal(sso_user=other.sub, display_name=other.sub)
    complete_display_name_setup(other.principal_id, other.display_name)
    import app.api.routes_keys as routes_keys
    import app.services.portal_actor_service as portal_actor_service

    monkeypatch.setattr(routes_keys, "resolve_session_user", lambda _req: other)
    monkeypatch.setattr(portal_actor_service, "resolve_session_user", lambda _req: other)
    denied = client.delete(f"/api/keys/{key_id}", headers=_ORIGIN)
    assert denied.status_code == 404


def test_quota_frees_after_delete(authing_client, session_user, monkeypatch):
    monkeypatch.setattr(settings, "max_keys_per_principal", 1)
    client = authing_client
    created = client.post("/api/keys", json={"label": "quota-one"}, headers=_ORIGIN)
    assert created.status_code == 200
    blocked = client.post("/api/keys", json={"label": "quota-two"}, headers=_ORIGIN)
    assert blocked.status_code == 400
    key_id = created.json()["key_id"]
    client.delete(f"/api/keys/{key_id}", headers=_ORIGIN)
    again = client.post("/api/keys", json={"label": "quota-after-delete"}, headers=_ORIGIN)
    assert again.status_code == 200


def test_ui_delete_key_form_post(authing_client, session_user):
    client = authing_client
    created = client.post("/api/keys", json={"label": "ui-delete"}, headers=_ORIGIN).json()
    key_id = created["key_id"]
    resp = client.post(
        f"/ui/keys/{key_id}/delete",
        headers={"Referer": f"http://testserver/ui/keys/{key_id}"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert client.get("/ui/keys/").text.count("ui-delete") == 0
    assert client.get(f"/ui/keys/{key_id}").status_code == 404


def test_ui_rename_key_form_post(authing_client, session_user):
    client = authing_client
    created = client.post("/api/keys", json={"label": "before-rename"}, headers=_ORIGIN).json()
    key_id = created["key_id"]
    resp = client.post(
        f"/ui/keys/{key_id}/edit",
        data={"label": "after-rename", "grant_personal": "writer", "grant_community": "writer"},
        headers={"Referer": f"http://testserver/ui/keys/{key_id}"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    page = client.get(f"/ui/keys/{key_id}")
    assert "after-rename" in page.text
    assert "保存权限" not in page.text
    assert ">保存</button>" in page.text


def test_create_key_with_custom_grants(authing_client, session_user):
    client = authing_client
    personal = ensure_personal_library(session_user.principal_id, session_user.display_name)
    created = client.post(
        "/api/keys",
        json={
            "label": "read-only-public",
            "grants": [
                {"library_id": personal["library_id"], "role": "writer"},
                {"library_id": settings.default_library_id, "role": "reader"},
            ],
        },
        headers=_ORIGIN,
    )
    assert created.status_code == 400
    assert "free tier" in created.json()["detail"].lower()


def test_ui_create_key_form_post(authing_client, session_user):
    client = authing_client
    label = "ui-form-key"
    resp = client.post(
        "/ui/keys/create",
        data={
            "label": label,
            "grant_personal": "writer",
            "grant_community": "writer",
        },
        headers={"Referer": "http://testserver/ui/keys/"},
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text[:500]
    assert "/ui/keys/key_" in resp.headers["location"]

    page = client.get(resp.headers["location"])
    assert page.status_code == 200
    assert label in page.text
    assert "ma3k_" in page.text
    assert "ma3CopyFrom" in page.text

    listed = client.get("/api/keys").json()["keys"]
    match = next(k for k in listed if k.get("label") == label)
    assert match["plaintext_key"].startswith("ma3k_")


def test_update_key_grants(authing_client, session_user):
    client = authing_client
    personal = ensure_personal_library(session_user.principal_id, session_user.display_name)
    created = client.post("/api/keys", json={"label": "grant-edit"}, headers=_ORIGIN).json()
    key_id = created["key_id"]
    updated = client.patch(
        f"/api/keys/{key_id}",
        json={
            "grants": [
                {"library_id": personal["library_id"], "role": "reader"},
                {"library_id": settings.default_library_id, "role": "writer"},
            ],
        },
        headers=_ORIGIN,
    )
    assert updated.status_code == 200
    grants = {g["library_id"]: g["role"] for g in updated.json()["grants"]}
    assert grants[personal["library_id"]] == "reader"
    assert grants[settings.default_library_id] == "writer"


def test_ui_update_grants_form_post(authing_client, session_user):
    client = authing_client
    created = client.post("/api/keys", json={"label": "ui-grants"}, headers=_ORIGIN).json()
    key_id = created["key_id"]
    resp = client.post(
        f"/ui/keys/{key_id}/edit",
        data={"label": "ui-grants", "grant_personal": "reader", "grant_community": "writer"},
        headers={"Referer": f"http://testserver/ui/keys/{key_id}"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    detail = client.get(f"/ui/keys/{key_id}")
    assert detail.status_code == 200
    row = db.get_api_key_for_principal(key_id, principal_id=session_user.principal_id)
    assert row is not None
    roles = {g["library_id"]: g["role"] for g in row["grants"]}
    personal = ensure_personal_library(session_user.principal_id, session_user.display_name)
    assert roles[personal["library_id"]] == "reader"


def test_ui_list_shows_copy_and_delete(authing_client, session_user):
    client = authing_client
    client.post("/api/keys", json={"label": "list-actions"}, headers=_ORIGIN)
    page = client.get("/ui/keys/")
    assert "cell-actions" in page.text
    assert "ma3CopyFrom" in page.text
    assert page.text.count("复制") >= 1
    assert page.text.count("删除") >= 1


def test_paid_user_can_create_reader_community_key(authing_client, session_user, monkeypatch):
    monkeypatch.setattr(settings, "paid_principal_ids", (session_user.principal_id,))
    client = authing_client
    personal = ensure_personal_library(session_user.principal_id, session_user.display_name)
    created = client.post(
        "/api/keys",
        json={
            "label": "read-only-public",
            "grants": [
                {"library_id": personal["library_id"], "role": "writer"},
                {"library_id": settings.default_library_id, "role": "reader"},
            ],
        },
        headers=_ORIGIN,
    )
    assert created.status_code == 200
    body = created.json()
    assert any(g["role"] == "reader" and g["library_id"] == settings.default_library_id for g in body["grants"])
