"""P2 self-host parity: MA3_BILLING_PROVIDER=none (design/27 §10 P2 bullet 1).

These tests PASS before Composer lands P2 (the routes simply do not exist yet)
and stay as the standing self-host guard afterwards: with provider=none the
checkout/portal/webhook routes answer 404, the billing page keeps its P1
"coming soon" shape with no upgrade form, and — critically — nothing imports
the stripe SDK (§2 P2 / §14 self-host drift risk: no Stripe code on shared
paths; per-request gating, no app rebuild needed).
"""
from __future__ import annotations

import pytest

from app.auth.session import SessionUser
from app.core.config import settings
from app.services.onboarding_service import ensure_personal_org
from app.services.org_service import create_team_org
from app.services.principal_service import complete_display_name_setup
from app.storage import db
from tests.helpers.billing_p2 import (
    checkout_completed_event,
    count_provider_events,
    event_payload,
    personal_ba_for,
    signed_webhook_headers,
    purge_stripe_modules,
    stripe_module_names,
)

pytestmark = pytest.mark.billing_p2

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


def _session_user(sub: str) -> SessionUser:
    user = SessionUser(
        principal_id=f"user:{sub}",
        sub=sub,
        display_name=sub,
        email=None,
        phone=None,
        is_admin=False,
    )
    db.upsert_user_principal(sso_user=sub, display_name=sub)
    complete_display_name_setup(user.principal_id, user.display_name)
    ensure_personal_org(user.principal_id, user.display_name)
    return user


@pytest.fixture()
def provider_none_env(isolated_client, monkeypatch):
    """Session user + team org, with the provider explicitly pinned to none."""
    _enable_authing(monkeypatch)
    monkeypatch.setattr(settings, "billing_provider", "none")
    owner = _session_user("p2-none-owner")
    monkeypatch.setattr(settings, "paid_principal_ids", (owner.principal_id,))
    org = create_team_org(name="P2 None Team", owner_principal_id=owner.principal_id)
    _patch_session(monkeypatch, owner)
    return {
        "client": isolated_client,
        "owner": owner,
        "owner_ba": personal_ba_for(owner.principal_id, owner.display_name),
        "org_id": str(org["id"]),
    }


# --- BP2-N1: checkout/portal routes 404 -------------------------------------------

def test_upgrade_and_portal_routes_404(provider_none_env):
    client = provider_none_env["client"]
    org_id = provider_none_env["org_id"]

    upgrade = client.post("/ui/billing/upgrade", headers=_ORIGIN)
    assert upgrade.status_code == 404, (
        "provider=none: POST /ui/billing/upgrade must 404 (§10 P2 bullet 1), "
        f"got {upgrade.status_code}"
    )

    portal = client.get("/ui/billing/portal", follow_redirects=False)
    assert portal.status_code == 404, (
        f"provider=none: GET /ui/billing/portal must 404, got {portal.status_code}"
    )

    org_upgrade = client.post(f"/ui/orgs/{org_id}/billing/upgrade", headers=_ORIGIN)
    assert org_upgrade.status_code == 404, (
        "provider=none: org upgrade route must 404 even for the org admin, "
        f"got {org_upgrade.status_code}"
    )


# --- BP2-N2: webhook 404 with no side effects ---------------------------------------

def test_webhook_route_404_and_leaves_no_trace(provider_none_env):
    client = provider_none_env["client"]
    event = checkout_completed_event(provider_none_env["owner_ba"], event_id="evt_none_1")
    payload = event_payload(event)

    response = client.post(
        "/webhooks/stripe", content=payload, headers=signed_webhook_headers(payload)
    )
    assert response.status_code == 404, (
        "provider=none: /webhooks/stripe must be unmounted/404 even for a "
        f"correctly signed event (§8.4), got {response.status_code}"
    )
    assert count_provider_events("evt_none_1") == 0, (
        "a 404'd webhook must not write billing_events"
    )
    from tests.helpers.billing_p2 import ba_plan_status

    assert ba_plan_status(provider_none_env["owner_ba"]) == ("free", "active"), (
        "provider=none webhook delivery must never change plan state"
    )


# --- BP2-N3: no stripe SDK import on the none path -----------------------------------

def test_no_stripe_import_on_provider_none_path(provider_none_env, monkeypatch):
    client = provider_none_env["client"]
    purge_stripe_modules(monkeypatch)

    assert client.get("/ui/billing/").status_code == 200
    client.post("/ui/billing/upgrade", headers=_ORIGIN)
    client.get("/ui/billing/portal", follow_redirects=False)
    payload = event_payload(checkout_completed_event(provider_none_env["owner_ba"]))
    client.post("/webhooks/stripe", content=payload, headers=signed_webhook_headers(payload))

    assert not stripe_module_names(), (
        "provider=none must never import the stripe SDK "
        f"(§10 P2 bullet 1); found {stripe_module_names()}"
    )


# --- BP2-N4: billing page keeps its P1 shape (BP1-P6 regression) -----------------------

def test_billing_page_keeps_coming_soon_without_upgrade_form(provider_none_env):
    from app.api.ui_i18n import catalog

    client = provider_none_env["client"]
    page = client.get("/ui/billing/")
    assert page.status_code == 200
    lowered = page.text.lower()
    assert "stripe.com" not in lowered, "provider=none page must not link to Stripe"
    assert 'action="/ui/billing/upgrade"' not in lowered, (
        "provider=none must not render the checkout upgrade form (§7: CTA "
        "visibility follows the provider flag)"
    )
    coming_soon = str(catalog("zh-CN").get("billing", {}).get("coming_soon") or "")
    if not coming_soon:  # catalog may be flat-keyed
        coming_soon = str(catalog("zh-CN").get("billing.coming_soon") or "")
    assert coming_soon and coming_soon in page.text, (
        "provider=none keeps the P1 coming-soon copy on the billing page"
    )
