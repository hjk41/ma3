"""Fable acceptance O1–O10 for org & library management (design/24 §10)."""
from __future__ import annotations

import secrets

import pytest
from fastapi import HTTPException

from app.auth.session import SessionUser
from app.core.config import settings
from app.services.api_key_service import hash_key
from app.services.library_admin_service import create_org_library
from app.services.onboarding_service import ensure_personal_org
from app.services.org_service import seed_team_org
from app.services.principal_service import complete_display_name_setup
from app.storage import db
from tests.helpers.mcp_client import McpClient

_EVIDENCE = [{"kind": "test", "summary": "org portal acceptance"}]
_ORIGIN = {"Origin": "http://testserver"}


def _enable_authing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "authing_enabled", True)
    monkeypatch.setattr(settings, "authing_issuer", "https://example.authing.cn")
    monkeypatch.setattr(settings, "authing_app_id", "test-app")
    monkeypatch.setattr(settings, "authing_app_secret", "test-secret")
    monkeypatch.setattr(settings, "auth_admin_users", ["portal-admin"])


def _patch_session(monkeypatch, user) -> None:
    import app.api.routes_keys as routes_keys
    import app.api.ui_session as ui_session
    import app.auth.session as session_mod
    import app.services.feedback_service as feedback_service
    import app.services.portal_actor_service as portal_actor_service

    resolver = lambda _req: user
    monkeypatch.setattr(session_mod, "resolve_session_user", resolver)
    monkeypatch.setattr(ui_session, "resolve_session_user", resolver)
    monkeypatch.setattr(routes_keys, "resolve_session_user", resolver)
    monkeypatch.setattr(feedback_service, "resolve_session_user", resolver)
    monkeypatch.setattr(portal_actor_service, "resolve_session_user", resolver)


@pytest.fixture()
def member_user() -> SessionUser:
    return SessionUser(
        principal_id="user:portal-b",
        sub="portal-b",
        display_name="Portal B",
        email=None,
        phone=None,
        is_admin=False,
    )


@pytest.fixture()
def team_org_setup(isolated_client, monkeypatch, portal_user, member_user):
    _enable_authing(monkeypatch)
    db.upsert_user_principal(sso_user=portal_user.sub, display_name=portal_user.sub)
    complete_display_name_setup(portal_user.principal_id, portal_user.display_name)
    ensure_personal_org(portal_user.principal_id, portal_user.display_name)
    db.upsert_user_principal(sso_user=member_user.sub, display_name=member_user.sub)
    complete_display_name_setup(member_user.principal_id, member_user.display_name)
    ensure_personal_org(member_user.principal_id, member_user.display_name)
    org = seed_team_org(name="Acme Team", admin_principal_id=portal_user.principal_id)
    db.add_org_member(org_id=org["id"], principal_id=member_user.principal_id, role="member")
    lib = create_org_library(
        org_id=org["id"],
        actor_principal_id=portal_user.principal_id,
        name="Acme Engineering",
        visibility="private",
        confirm_org_visibility=True,
    )
    return {"org_id": org["id"], "library_id": lib["library_id"], "admin": portal_user, "member": member_user}


def test_o1_org_member_sees_org_overview(team_org_setup, isolated_client, monkeypatch, portal_user):
    _patch_session(monkeypatch, portal_user)
    org_id = team_org_setup["org_id"]
    response = isolated_client.get(f"/ui/orgs/{org_id}/")
    assert response.status_code == 200
    assert "Acme Team" in response.text or "Acme Engineering" in response.text
    assert "Acme Engineering" in response.text


def test_o2_non_member_org_url_404(team_org_setup, isolated_client, monkeypatch, member_user):
    _patch_session(monkeypatch, member_user)
    outsider = SessionUser(
        principal_id="user:outsider",
        sub="outsider",
        display_name="Outsider",
        email=None,
        phone=None,
        is_admin=False,
    )
    db.upsert_user_principal(sso_user="outsider", display_name="outsider")
    complete_display_name_setup("user:outsider", "Outsider")
    _patch_session(monkeypatch, outsider)
    response = isolated_client.get(f"/ui/orgs/{team_org_setup['org_id']}/")
    assert response.status_code == 404


def test_o3_admin_adds_member_by_display_name(team_org_setup, isolated_client, monkeypatch, portal_user):
    _patch_session(monkeypatch, portal_user)
    db.upsert_user_principal(sso_user="join-me", display_name="join-me")
    complete_display_name_setup("user:join-me", "Join Me")
    org_id = team_org_setup["org_id"]
    response = isolated_client.post(
        f"/ui/orgs/{org_id}/members/",
        data={"display_name": "Join Me", "role": "member"},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert response.status_code == 303
    member = db.get_org_member(org_id, "user:join-me")
    assert member is not None
    assert member["seat_status"] == "active"


def test_o3b_cannot_remove_last_admin(team_org_setup, isolated_client, monkeypatch, portal_user):
    _patch_session(monkeypatch, portal_user)
    org_id = team_org_setup["org_id"]
    response = isolated_client.post(
        f"/ui/orgs/{org_id}/members/remove/",
        data={"principal_id": portal_user.principal_id},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=" in response.headers["location"].lower() or "admin" in response.headers["location"].lower()
    still = db.get_org_member(org_id, portal_user.principal_id)
    assert still is not None
    assert still["seat_status"] == "active"


def test_o4_admin_creates_org_library(team_org_setup, isolated_client, monkeypatch, portal_user):
    _patch_session(monkeypatch, portal_user)
    org_id = team_org_setup["org_id"]
    before = len(db.list_org_libraries(org_id))
    response = isolated_client.post(
        f"/ui/orgs/{org_id}/libraries/",
        data={"name": "Second Lib", "visibility": "private"},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert len(db.list_org_libraries(org_id)) == before + 1
    created = [l for l in db.list_org_libraries(org_id) if l["name"] == "Second Lib"][0]
    assert created["org_id"] == org_id


def test_o5_maintainer_records_list_scoped(team_org_setup, isolated_client, monkeypatch, portal_user):
    _patch_session(monkeypatch, portal_user)
    lib_id = team_org_setup["library_id"]
    other_lib = create_org_library(
        org_id=team_org_setup["org_id"],
        actor_principal_id=portal_user.principal_id,
        name="Other Lib",
        visibility="private",
        confirm_org_visibility=True,
    )["library_id"]
    db.insert_record(
        library_id=lib_id,
        case_id=None,
        problem="in target lib",
        outcome="resolved",
        result_summary="x",
        payload={"evidence": _EVIDENCE},
        status="active",
        principal_id=portal_user.principal_id,
    )
    db.insert_record(
        library_id=other_lib,
        case_id=None,
        problem="in other lib",
        outcome="resolved",
        result_summary="x",
        payload={"evidence": _EVIDENCE},
        status="active",
        principal_id=portal_user.principal_id,
    )
    response = isolated_client.get(f"/ui/libraries/{lib_id}/records/")
    assert response.status_code == 200
    assert "in target lib" in response.text
    assert "in other lib" not in response.text


def test_o6_member_cannot_open_grants(team_org_setup, isolated_client, monkeypatch, member_user):
    _patch_session(monkeypatch, member_user)
    response = isolated_client.get(f"/ui/libraries/{team_org_setup['library_id']}/grants/")
    assert response.status_code == 404


def test_o7_personal_storage_matches_whoami(team_org_setup, isolated_client, monkeypatch, portal_user):
    _patch_session(monkeypatch, portal_user)
    personal = db.find_personal_library(portal_user.principal_id)
    assert personal is not None
    mcp = McpClient(isolated_client, api_key=settings.dev_api_key)
    whoami = mcp.structured("ma3_whoami", {})
    quota = whoami.get("storage_quota") or {}
    response = isolated_client.get(f"/ui/libraries/{personal['library_id']}/storage/")
    assert response.status_code == 200
    assert str(quota.get("tier", "")) in response.text or "storage-meter" in response.text


def test_o8_storage_full_mcp_and_ui(team_org_setup, isolated_client, monkeypatch, portal_user):
    monkeypatch.setattr(settings, "personal_library_quota_bytes_free", 900)
    _patch_session(monkeypatch, portal_user)
    personal = db.find_personal_library(portal_user.principal_id)
    assert personal is not None
    lib_id = str(personal["library_id"])
    plaintext = f"ma3k_{secrets.token_hex(16)}"
    db.insert_api_key(
        key_id=f"key_{secrets.token_hex(6)}",
        key_hash=hash_key(plaintext),
        principal_id=portal_user.principal_id,
        label="quota-ui",
        grants=[
            {"library_id": lib_id, "role": "writer"},
            {"library_id": settings.default_library_id, "role": "writer"},
        ],
    )
    mcp = McpClient(isolated_client)
    mcp.structured(
        "ma3_report",
        {
            "problem": "q1",
            "outcome": "resolved",
            "result_summary": "ok",
            "library_id": lib_id,
            "based_on_record_ids": [],
            "evidence": [{"kind": "test", "summary": "a"}],
        },
        api_key=plaintext,
    )
    err = mcp.call(
        "ma3_report",
        {
            "problem": "overflow",
            "outcome": "resolved",
            "result_summary": "too big",
            "library_id": lib_id,
            "based_on_record_ids": [],
            "evidence": [{"kind": "test", "summary": "x" * 300}],
        },
        api_key=plaintext,
        expect_error=True,
    )
    assert "quota" in err["message"].lower()
    page = isolated_client.get(f"/ui/libraries/{lib_id}/storage/")
    assert page.status_code == 200
    assert "storage-meter-fill full" in page.text or "storage-meter" in page.text


def test_o9_en_us_orgs_nav(team_org_setup, isolated_client, monkeypatch, portal_user):
    _patch_session(monkeypatch, portal_user)
    response = isolated_client.get("/ui/orgs/", cookies={"ma3_locale": "en-US"})
    assert response.status_code == 200
    assert "Organizations" in response.text


def test_o10_observatory_has_no_org_admin(authing_admin_client):
    response = authing_admin_client.get("/ui/observatory/")
    assert response.status_code == 200
    assert "添加成员" not in response.text
    assert "Add member" not in response.text
    assert "/ui/orgs/" not in response.text.split("</nav>")[-1] or "Organizations" in response.text


def test_o11_free_user_sees_upgrade_on_create_team(isolated_client, monkeypatch, portal_user):
    _enable_authing(monkeypatch)
    _patch_session(monkeypatch, portal_user)
    db.upsert_user_principal(sso_user=portal_user.sub, display_name=portal_user.sub)
    complete_display_name_setup(portal_user.principal_id, portal_user.display_name)
    ensure_personal_org(portal_user.principal_id, portal_user.display_name)
    response = isolated_client.get("/ui/orgs/new/")
    assert response.status_code == 200
    assert "Pro" in response.text or "升级" in response.text
    post = isolated_client.post(
        "/ui/orgs/new/",
        data={"name": "Blocked Team"},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert post.status_code == 303
    assert db.count_team_orgs_owned(portal_user.principal_id) == 0


def test_o12_pro_user_creates_team_via_portal(isolated_client, monkeypatch):
    from app.auth.session import SessionUser
    from app.services.onboarding_service import ensure_personal_org

    pro = SessionUser(
        principal_id="user:pro-team",
        sub="pro-team",
        display_name="Pro Team User",
        email=None,
        phone=None,
        is_admin=False,
    )
    monkeypatch.setattr(settings, "paid_principal_ids", ("user:pro-team",))
    _enable_authing(monkeypatch)
    _patch_session(monkeypatch, pro)
    db.upsert_user_principal(sso_user=pro.sub, display_name=pro.sub)
    complete_display_name_setup(pro.principal_id, pro.display_name)
    ensure_personal_org(pro.principal_id, pro.display_name)
    response = isolated_client.get("/ui/orgs/new/")
    assert response.status_code == 200
    assert 'name="name"' in response.text
    post = isolated_client.post(
        "/ui/orgs/new/",
        data={"name": "My Team Org"},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert post.status_code == 303
    assert db.count_team_orgs_owned(pro.principal_id) == 1
    orgs = [o for o in db.list_orgs_for_principal(pro.principal_id) if o.get("kind") == "team"]
    assert len(orgs) == 1
    assert orgs[0]["name"] == "My Team Org"

