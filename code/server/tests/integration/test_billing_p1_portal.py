"""P1 billing portal scenarios (design/27 §7 UX, §8.2/8.3, §9 Decision 7,
§10 P1 acceptance bullet 6, §13 `test_billing_portal.py`).

Contract encoded here:
- ``GET /ui/billing/`` — personal billing page (session), zh/en via the
  shipped i18n machinery; anonymous access does not render the page.
- ``GET /ui/orgs/{org_id}/billing/`` — org ADMIN only; non-admin member and
  outsider both get 404 (existing convention: unauthorized org pages 404).
- ``GET /api/me/billing`` / ``GET /api/orgs/{org_id}/billing`` — JSON
  summaries; meters accurate against usage_monthly; member → 404 on org.
- i18n: zh-CN and en-US catalogs carry the SAME non-empty ``billing.*`` set.
- Decision 7: no Checkout on SaaS in P1 — ``POST /ui/billing/upgrade`` does
  not exist (404) and the page links to no Stripe URL; a disabled
  "coming soon" CTA / self-host admin-contact copy is allowed.
- past_due: banner marker ``id="past-due-banner"`` on the billing page for
  the duration of grace (Decision 8-A).
"""
from __future__ import annotations

import pytest

from app.auth.session import SessionUser
from app.core.config import settings
from app.services.onboarding_service import ensure_personal_org, personal_org_id
from app.services.org_service import create_team_org
from app.services.principal_service import complete_display_name_setup
from app.storage import db
from tests.helpers.billing_p1 import (
    billing_i18n_keys,
    fetch_billing_account_for_org,
    org_ba_id,
    set_ba_status,
)

pytestmark = pytest.mark.billing_p1

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


def _session_user(sub: str, *, is_admin: bool = False) -> SessionUser:
    user = SessionUser(
        principal_id=f"user:{sub}",
        sub=sub,
        display_name=sub,
        email=None,
        phone=None,
        is_admin=is_admin,
    )
    db.upsert_user_principal(sso_user=sub, display_name=sub)
    complete_display_name_setup(user.principal_id, user.display_name)
    ensure_personal_org(user.principal_id, user.display_name)
    return user


@pytest.fixture()
def billing_portal_env(isolated_client, monkeypatch):
    """Org admin (Pro creator of a team_stub org), plain member, outsider."""
    _enable_authing(monkeypatch)
    owner = _session_user("bill-owner")
    member = _session_user("bill-member")
    outsider = _session_user("bill-outsider")
    monkeypatch.setattr(settings, "paid_principal_ids", (owner.principal_id,))
    org = create_team_org(name="Billing Portal Team", owner_principal_id=owner.principal_id)
    org_id = str(org["id"])
    db.add_org_member(org_id=org_id, principal_id=member.principal_id, role="member")
    return {
        "client": isolated_client,
        "owner": owner,
        "member": member,
        "outsider": outsider,
        "org_id": org_id,
    }


# --- BP1-P1: personal billing page renders zh/en -------------------------------

def test_personal_billing_page_renders_both_locales(billing_portal_env, monkeypatch):
    env = billing_portal_env
    _patch_session(monkeypatch, env["owner"])
    zh = env["client"].get("/ui/billing/")
    assert zh.status_code == 200, (
        f"/ui/billing/ must exist in P1 (§7): {zh.status_code}"
    )
    assert '<html lang="zh-CN">' in zh.text

    en = env["client"].get("/ui/billing/?lang=en-US")
    assert en.status_code == 200
    assert '<html lang="en-US">' in en.text


def test_personal_billing_page_requires_session(billing_portal_env):
    env = billing_portal_env
    # Guard against a spurious pass pre-P1 (missing route also non-200):
    # first prove the page exists for a session user, then drop the session.
    with pytest.MonkeyPatch.context() as session_patch:
        _patch_session(session_patch, env["owner"])
        assert env["client"].get("/ui/billing/").status_code == 200, (
            "/ui/billing/ must exist in P1 (§7)"
        )
    response = env["client"].get("/ui/billing/", follow_redirects=False)
    assert response.status_code != 200, (
        "anonymous /ui/billing/ must not render (redirect to login or 404)"
    )


# --- BP1-P2: /api/me/billing summary + meter accuracy ---------------------------

def test_me_billing_summary_shape_and_meter_accuracy(billing_portal_env, monkeypatch):
    usage_service = pytest.importorskip(
        "app.services.usage_service",
        reason="P1 not implemented yet: app.services.usage_service",
    )
    env = billing_portal_env
    owner = env["owner"]
    _patch_session(monkeypatch, owner)
    ba = fetch_billing_account_for_org(personal_org_id(owner.principal_id))
    for _ in range(4):
        usage_service.record_read_usage(
            str(ba["id"]), tool_name="ma3_context", records_returned=1, status_code=200
        )

    response = env["client"].get("/api/me/billing")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan_code"] == "pro"  # env-allowlisted owner
    assert body["status"] == "active"
    read_units = body["read_units"]
    assert int(read_units["used"]) == 4, (
        "the /api/me/billing reads meter must match usage_monthly (§10 P1 bullet 6)"
    )
    assert int(read_units["limit"]) > 0
    for block in ("storage", "seats"):
        assert block in body, f"/api/me/billing must include a {block} meter (§8.2)"


# --- BP1-P3/P4: org billing gating (admin-only, member/outsider → 404) -----------

def test_org_billing_page_admin_only(billing_portal_env, monkeypatch):
    env = billing_portal_env
    url = f"/ui/orgs/{env['org_id']}/billing/"

    _patch_session(monkeypatch, env["owner"])
    admin_page = env["client"].get(url)
    assert admin_page.status_code == 200, (
        f"org admin must see {url} (§7): {admin_page.status_code}"
    )

    _patch_session(monkeypatch, env["member"])
    member_page = env["client"].get(url)
    assert member_page.status_code == 404, (
        "non-admin org member must get 404 on org billing (§10 P1 bullet 6, "
        f"got {member_page.status_code})"
    )

    _patch_session(monkeypatch, env["outsider"])
    assert env["client"].get(url).status_code == 404


def test_org_billing_api_admin_only(billing_portal_env, monkeypatch):
    env = billing_portal_env
    url = f"/api/orgs/{env['org_id']}/billing"

    _patch_session(monkeypatch, env["owner"])
    response = env["client"].get(url)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan_code"] == "team_stub"  # Decision 5a=A
    assert "seats" in body and "storage" in body and "read_units" in body

    _patch_session(monkeypatch, env["member"])
    assert env["client"].get(url).status_code == 404, (
        "org billing summary is org-admin only; member → 404 (§8.2)"
    )


# --- BP1-P5: i18n completeness ----------------------------------------------------

def test_billing_i18n_keys_complete_in_zh_and_en():
    zh_keys = billing_i18n_keys("zh-CN")
    en_keys = billing_i18n_keys("en-US")
    assert zh_keys, (
        "P1 must add billing.* keys to the zh-CN catalog (§7 i18n zh/en complete)"
    )
    assert zh_keys == en_keys, (
        f"zh/en billing catalogs diverge: only-zh={sorted(zh_keys - en_keys)} "
        f"only-en={sorted(en_keys - zh_keys)}"
    )


# --- BP1-P6: Checkout CTA hidden/disabled until P2 (Decision 7) --------------------

def test_no_checkout_path_in_p1(billing_portal_env, monkeypatch):
    env = billing_portal_env
    _patch_session(monkeypatch, env["owner"])
    page = env["client"].get("/ui/billing/")
    assert page.status_code == 200
    lowered = page.text.lower()
    assert "stripe.com" not in lowered, "no Stripe link before Checkout ships (P2)"
    assert 'action="/ui/billing/upgrade"' not in lowered and \
        "href=\"/ui/billing/upgrade\"" not in lowered, (
        "SaaS upgrade CTA must be hidden/disabled ('coming soon') until P2"
    )

    upgrade = env["client"].post("/ui/billing/upgrade", headers=_ORIGIN)
    assert upgrade.status_code == 404, (
        "POST /ui/billing/upgrade is a P2 route; it must not exist in P1 "
        f"(got {upgrade.status_code})"
    )


# --- BP1-P7: past_due banner during grace (Decision 8-A) -----------------------------

def test_past_due_banner_on_billing_pages(billing_portal_env, monkeypatch):
    env = billing_portal_env
    owner = env["owner"]
    _patch_session(monkeypatch, owner)

    personal_ba = fetch_billing_account_for_org(personal_org_id(owner.principal_id))
    set_ba_status(str(personal_ba["id"]), "past_due")
    page = env["client"].get("/ui/billing/")
    assert page.status_code == 200
    assert 'id="past-due-banner"' in page.text, (
        "billing page must show the grace banner while status='past_due' "
        "(Decision 8-A banner+email)"
    )

    set_ba_status(org_ba_id(env["org_id"]), "past_due")
    org_page = env["client"].get(f"/ui/orgs/{env['org_id']}/billing/")
    assert org_page.status_code == 200
    assert 'id="past-due-banner"' in org_page.text
