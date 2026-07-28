"""Observatory billing ops: list paid users/orgs and set plan_code."""
from __future__ import annotations

from app.core.config import settings
from app.services.onboarding_service import (
    ensure_personal_org,
    is_paid_principal,
    personal_org_id,
    set_user_paid,
)
from app.storage import db

_ORIGIN = {"Origin": "http://testserver"}


def test_set_user_paid_persists_plan_and_is_paid(isolated_client, monkeypatch):
    monkeypatch.setattr(settings, "paid_principal_ids", ())
    db.upsert_user_principal(sso_user="ops-paid", display_name="Ops Paid")
    pid = "user:ops-paid"
    ensure_personal_org(pid, "Ops Paid")
    assert is_paid_principal(pid) is False

    result = set_user_paid(principal_id=pid, paid=True)
    assert result["plan_code"] == "pro"
    assert result["effective_paid"] is True
    assert db.get_principal_plan_code(pid) == "pro"
    assert is_paid_principal(pid) is True

    org = db.get_organization(personal_org_id(pid))
    assert org is not None
    assert org.get("billing_account_id") == "plan:pro"

    set_user_paid(principal_id=pid, paid=False)
    assert db.get_principal_plan_code(pid) == "free"
    assert is_paid_principal(pid) is False


def test_env_whitelist_still_overrides_free_db(isolated_client, monkeypatch):
    monkeypatch.setattr(settings, "paid_principal_ids", ("user:env-paid",))
    db.upsert_user_principal(sso_user="env-paid", display_name="Env Paid")
    assert is_paid_principal("user:env-paid") is True
    set_user_paid(principal_id="user:env-paid", paid=False)
    assert db.get_principal_plan_code("user:env-paid") == "free"
    assert is_paid_principal("user:env-paid") is True  # env still wins


def test_observatory_billing_pages_admin(authing_admin_client):
    for path in ("/ui/observatory/billing/", "/ui/observatory/users/", "/ui/observatory/orgs/"):
        response = authing_admin_client.get(path)
        assert response.status_code == 200, path
        assert "付费" in response.text or "组织" in response.text


def test_observatory_users_non_admin_403(authing_portal_client):
    response = authing_portal_client.get("/ui/observatory/users/", follow_redirects=False)
    assert response.status_code == 403


def test_observatory_set_user_plan_post(authing_admin_client, admin_user, monkeypatch):
    monkeypatch.setattr(settings, "paid_principal_ids", ())
    pid = admin_user.principal_id
    db.set_principal_plan_code(pid, "free")
    assert is_paid_principal(pid) is False

    response = authing_admin_client.post(
        "/ui/observatory/users/plan",
        data={"principal_id": pid, "plan_code": "pro", "q": "", "paid_only": "0"},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "/ui/observatory/users/" in response.headers["location"]
    assert db.get_principal_plan_code(pid) == "pro"
    assert is_paid_principal(pid) is True

    response = authing_admin_client.get("/ui/observatory/users/?paid_only=1")
    assert response.status_code == 200
    assert pid in response.text
