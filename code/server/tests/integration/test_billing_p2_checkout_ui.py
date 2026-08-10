"""P2 Stripe checkout/portal UI + webhook route scenarios
(design/27 §2 P2, §7, §8.3/8.4, §9 Decisions 1-2, §10 P2, §12).

Contract encoded here (provider=stripe with fixture credentials, network-free
fake stripe SDK from tests.helpers.billing_p2):

- /ui/billing/ for a FREE session user shows a real upgrade CTA: a form
  posting to /ui/billing/upgrade (the P1 "coming soon" copy is no longer the
  only path).
- POST /ui/billing/upgrade (session + same-origin) creates a hosted Checkout
  Session — mode=subscription, client_reference_id=<BA>, env price id
  (Decision 1), metadata {billing_account_id, plan_code} — and 30x-redirects
  to its url. Cross-origin POST is rejected (§12 CSRF).
- Visiting the success URL alone NEVER changes the plan ("pending" page; the
  webhook is the sole plan writer — §12 success-URL forgery, §10 P2 bullet 2).
- POST /webhooks/stripe (route-level): signed event activates the plan, 2xx;
  duplicate delivery 2xx + single billing_events row; oversized body rejected
  (§8.4 body-size cap).
- GET /ui/billing/portal 30x-redirects to a Customer Portal session for the
  BA's provider_customer_id; without a linked customer -> 4xx, no Stripe call.
- POST /ui/orgs/{org_id}/billing/upgrade: org ADMIN only (member 404), Team
  price on the ORG BA (§7 org upgrade path).
- Observatory reconciliation smoke (§2 P2 last row): the billing ops page
  surfaces the provider subscription id for a linked BA.

SKIPS until Composer lands ``app.services.stripe_billing_service``.
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
    FAKE_PRICE_PRO,
    FAKE_PRICE_TEAM,
    ba_plan_status,
    checkout_completed_event,
    count_provider_events,
    enable_stripe_provider,
    event_payload,
    fetch_billing_account_for_org,
    install_fake_stripe,
    link_provider_subscription,
    personal_ba_for,
    signed_webhook_headers,
)

pytest.importorskip(
    "app.services.stripe_billing_service",
    reason="P2 not implemented yet: app.services.stripe_billing_service (design/27 §2 P2)",
)

pytestmark = pytest.mark.billing_p2

_ORIGIN = {"Origin": "http://testserver"}
_REDIRECTS = (302, 303, 307)


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
def stripe_ui_env(isolated_client, monkeypatch):
    """provider=stripe + fake SDK; a free buyer, a Pro org owner, a member."""
    _enable_authing(monkeypatch)
    enable_stripe_provider(monkeypatch)
    fake = install_fake_stripe(monkeypatch)

    buyer = _session_user("p2-buyer")  # stays on the free plan
    owner = _session_user("p2-org-owner")
    member = _session_user("p2-org-member")
    monkeypatch.setattr(settings, "paid_principal_ids", (owner.principal_id,))
    org = create_team_org(name="P2 Checkout Team", owner_principal_id=owner.principal_id)
    org_id = str(org["id"])
    db.add_org_member(org_id=org_id, principal_id=member.principal_id, role="member")

    return {
        "client": isolated_client,
        "fake": fake,
        "buyer": buyer,
        "buyer_ba": personal_ba_for(buyer.principal_id, buyer.display_name),
        "owner": owner,
        "member": member,
        "org_id": org_id,
        "org_ba": str(fetch_billing_account_for_org(org_id)["id"]),
    }


# --- BP2-C1: upgrade CTA present when provider=stripe --------------------------------

def test_billing_page_shows_upgrade_form_for_free_user(stripe_ui_env, monkeypatch):
    env = stripe_ui_env
    _patch_session(monkeypatch, env["buyer"])
    page = env["client"].get("/ui/billing/")
    assert page.status_code == 200
    assert 'action="/ui/billing/upgrade"' in page.text, (
        "provider=stripe: the billing page must render a real upgrade form "
        "posting to /ui/billing/upgrade (§7: CTA visibility follows the "
        "provider flag; coming-soon copy is no longer the only path)"
    )


# --- BP2-C2: POST upgrade creates a Checkout Session ----------------------------------

def test_post_upgrade_creates_checkout_session_and_redirects(stripe_ui_env, monkeypatch):
    env = stripe_ui_env
    _patch_session(monkeypatch, env["buyer"])
    response = env["client"].post(
        "/ui/billing/upgrade", headers=_ORIGIN, follow_redirects=False
    )
    assert response.status_code in _REDIRECTS, (
        f"upgrade must redirect to hosted Checkout, got {response.status_code}: "
        f"{response.text[:300]}"
    )
    location = response.headers.get("location", "")
    assert location.startswith("https://checkout.stripe.com/"), location

    call = env["fake"].last_checkout
    assert call.get("mode") == "subscription"
    assert call.get("client_reference_id") == env["buyer_ba"], (
        "Checkout Session must carry the BA id as client_reference_id"
    )
    metadata = call.get("metadata") or {}
    assert metadata.get("billing_account_id") == env["buyer_ba"]
    assert metadata.get("plan_code") == "pro"
    assert env["fake"].checkout_price_ids(call) == [FAKE_PRICE_PRO], (
        "personal upgrade must use the env Pro price id (Decision 1: env "
        "Stripe Price IDs, never hardcoded amounts)"
    )


def test_cross_origin_upgrade_post_rejected(stripe_ui_env, monkeypatch):
    env = stripe_ui_env
    _patch_session(monkeypatch, env["buyer"])
    response = env["client"].post(
        "/ui/billing/upgrade",
        headers={"Origin": "https://evil.example"},
        follow_redirects=False,
    )
    assert response.status_code not in (200, *_REDIRECTS), (
        "§12 CSRF: cross-origin POST /ui/billing/upgrade must be rejected, "
        f"got {response.status_code}"
    )
    assert not env["fake"].checkout_calls, (
        "a rejected cross-origin POST must not create a Checkout Session"
    )


# --- BP2-C3: success URL alone changes nothing ----------------------------------------

def test_success_url_visit_does_not_change_plan(stripe_ui_env, monkeypatch):
    env = stripe_ui_env
    _patch_session(monkeypatch, env["buyer"])
    env["client"].post("/ui/billing/upgrade", headers=_ORIGIN, follow_redirects=False)

    success = env["client"].get("/ui/billing/?checkout=success")
    assert success.status_code == 200, "success return URL renders a pending page"
    assert ba_plan_status(env["buyer_ba"]) == ("free", "active"), (
        "visiting the success URL must NEVER activate the plan — the webhook "
        "is the sole plan writer (§12 success-URL forgery, §10 P2 bullet 2)"
    )


# --- BP2-C4: webhook route end-to-end + idempotent duplicate + body cap ----------------

def test_webhook_route_activates_plan_and_is_idempotent(stripe_ui_env):
    env = stripe_ui_env
    event = checkout_completed_event(
        env["buyer_ba"], plan_code="pro", subscription_id="sub_c4", event_id="evt_c4"
    )
    payload = event_payload(event)

    first = env["client"].post(
        "/webhooks/stripe", content=payload, headers=signed_webhook_headers(payload)
    )
    assert 200 <= first.status_code < 300, first.text
    assert ba_plan_status(env["buyer_ba"]) == ("pro", "active"), (
        "the signed checkout.session.completed webhook activates the plan"
    )

    duplicate = env["client"].post(
        "/webhooks/stripe", content=payload, headers=signed_webhook_headers(payload)
    )
    assert 200 <= duplicate.status_code < 300, (
        "duplicate delivery must be acknowledged 2xx so Stripe stops retrying"
    )
    assert count_provider_events("evt_c4") == 1, (
        "the same event delivered twice must leave exactly one billing_events row"
    )


def test_webhook_bad_signature_rejected_at_route(stripe_ui_env):
    env = stripe_ui_env
    event = checkout_completed_event(env["buyer_ba"], event_id="evt_c4_bad")
    payload = event_payload(event)
    response = env["client"].post(
        "/webhooks/stripe",
        content=payload,
        headers=signed_webhook_headers(payload, secret="whsec_wrong_secret"),
    )
    assert response.status_code == 400, (
        f"bad signature must be a 400 at the route (§10 P2 b3), got {response.status_code}"
    )
    assert count_provider_events("evt_c4_bad") == 0
    assert ba_plan_status(env["buyer_ba"]) == ("free", "active")


def test_webhook_oversized_body_rejected(stripe_ui_env):
    env = stripe_ui_env
    event = checkout_completed_event(env["buyer_ba"], event_id="evt_c4_big")
    event["data"]["object"]["padding"] = "x" * (2 * 1024 * 1024)
    payload = event_payload(event)
    response = env["client"].post(
        "/webhooks/stripe", content=payload, headers=signed_webhook_headers(payload)
    )
    assert response.status_code in (400, 413), (
        "§8.4: webhook body size is capped — a 2 MiB payload must be "
        f"rejected, got {response.status_code}"
    )
    assert count_provider_events("evt_c4_big") == 0
    assert ba_plan_status(env["buyer_ba"]) == ("free", "active")


# --- BP2-C5: Customer Portal redirect ----------------------------------------------

def test_portal_requires_linked_customer_then_redirects(stripe_ui_env, monkeypatch):
    env = stripe_ui_env
    _patch_session(monkeypatch, env["buyer"])

    unlinked = env["client"].get("/ui/billing/portal", follow_redirects=False)
    assert 400 <= unlinked.status_code < 500, (
        "portal without a provider_customer_id must be a 4xx, "
        f"got {unlinked.status_code}"
    )
    assert not env["fake"].portal_calls, "no Stripe call for an unlinked BA"

    link_provider_subscription(
        env["buyer_ba"], subscription_id="sub_c5", customer_id="cus_c5"
    )
    linked = env["client"].get("/ui/billing/portal", follow_redirects=False)
    assert linked.status_code in _REDIRECTS, (
        f"portal must redirect to the Customer Portal session, got {linked.status_code}"
    )
    assert linked.headers.get("location", "").startswith("https://billing.stripe.com/")
    assert env["fake"].last_portal.get("customer") == "cus_c5", (
        "portal session must be created for the BA's provider_customer_id"
    )


# --- BP2-C6: org upgrade (Team price, org BA, admin-only) ------------------------------

def test_org_upgrade_uses_team_price_on_org_ba(stripe_ui_env, monkeypatch):
    env = stripe_ui_env
    url = f"/ui/orgs/{env['org_id']}/billing/upgrade"

    _patch_session(monkeypatch, env["owner"])
    response = env["client"].post(url, headers=_ORIGIN, follow_redirects=False)
    assert response.status_code in _REDIRECTS, (
        f"org admin upgrade must redirect to Checkout, got {response.status_code}: "
        f"{response.text[:300]}"
    )
    call = env["fake"].last_checkout
    assert call.get("client_reference_id") == env["org_ba"], (
        "org upgrade must bill the ORG billing account (§7: same BA)"
    )
    assert (call.get("metadata") or {}).get("plan_code") == "team"
    assert env["fake"].checkout_price_ids(call) == [FAKE_PRICE_TEAM], (
        "org upgrade must use the env Team price id (Decision 1)"
    )


def test_org_upgrade_member_gets_404(stripe_ui_env, monkeypatch):
    env = stripe_ui_env
    _patch_session(monkeypatch, env["member"])
    response = env["client"].post(
        f"/ui/orgs/{env['org_id']}/billing/upgrade", headers=_ORIGIN, follow_redirects=False
    )
    assert response.status_code == 404, (
        "org upgrade is org-admin only; non-admin member must get 404 "
        f"(existing org-page convention), got {response.status_code}"
    )
    assert not env["fake"].checkout_calls


# --- BP2-C7: Observatory reconciliation smoke ------------------------------------------

def test_observatory_billing_page_surfaces_subscription_id(stripe_ui_env, monkeypatch):
    env = stripe_ui_env
    admin = _session_user("portal-admin", is_admin=True)
    _patch_session(monkeypatch, admin)
    link_provider_subscription(
        env["buyer_ba"], subscription_id="sub_reconcile_1", customer_id="cus_reconcile_1"
    )
    page = env["client"].get("/ui/observatory/billing/")
    assert page.status_code == 200, page.text[:300]
    assert "sub_reconcile_1" in page.text, (
        "§2 P2: the Observatory reconciliation view must show the Stripe "
        "subscription id <-> billing account mapping when provider=stripe"
    )
