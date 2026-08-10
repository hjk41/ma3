"""Shared helpers for org+billing P2 (Stripe) acceptance tests (tests-first).

Encodes the public contract Composer implements against
(design/27 `27-org-billing-implementation-fable.md` §2 P2, §8.3/8.4,
§9 Decisions 1-2, §10 P2, §12 threat table, §13 `test_stripe_webhook.py`):

Expected NEW symbols (P2)
=========================

``app.services.stripe_billing_service`` (§2 P2 rows 2-4):
    create_checkout_session(billing_account_id: str, *, plan_code: str,
                            success_url: str | None = None,
                            cancel_url: str | None = None) -> dict
        # Returns at least {"id", "url"} of a hosted Checkout Session.
        # MUST call stripe.checkout.Session.create with:
        #   mode="subscription"
        #   client_reference_id=billing_account_id
        #   metadata containing {"billing_account_id", "plan_code"}
        #   line item price = settings.stripe_price_pro  for plan_code="pro"
        #                     settings.stripe_price_team for plan_code="team"
        #     (Decision 1: prices are Stripe Price IDs from env, NEVER
        #      hardcoded amounts.)
        # Default success_url = {public_base_url}/ui/billing/?checkout=success
        #         cancel_url  = {public_base_url}/ui/billing/?checkout=cancel
    create_portal_session(billing_account_id: str, *,
                          return_url: str | None = None) -> dict
        # Returns at least {"url"} via stripe.billing_portal.Session.create(
        #   customer=<billing_accounts.provider_customer_id>, ...).
        # BA without provider_customer_id -> HTTPException 4xx (no Stripe call).
    handle_webhook_event(payload: bytes, sig_header: str) -> dict
        # 1. Verify with stripe.Webhook.construct_event(payload, sig_header,
        #    settings.stripe_webhook_secret) — official SDK, default 300s
        #    timestamp tolerance (§12: reject stale >5 min). Verification
        #    failure (bad/missing sig, stale t) -> fastapi HTTPException(400)
        #    with NO billing_events row and NO state change.
        # 2. Idempotency: INSERT-FIRST into billing_events on
        #    (provider='stripe', provider_event_id=event["id"]) using the
        #    existing partial-unique index; duplicate event id -> return
        #    WITHOUT re-running the handler (same event twice mutates once,
        #    §10 P2 bullet 2).
        # 3. Handlers (event MUST be read with mapping-style access —
        #    event["type"], event["data"]["object"] — so tests can substitute
        #    a plain-dict-returning construct_event):
        #    - checkout.session.completed: resolve BA from
        #      data.object.metadata["billing_account_id"] (mirrored in
        #      client_reference_id); set plan from metadata["plan_code"],
        #      status='active'; persist provider='stripe',
        #      provider_customer_id=data.object.customer,
        #      provider_subscription_id=data.object.subscription.
        #    - invoice.payment_failed: resolve BA via data.object.subscription
        #      == billing_accounts.provider_subscription_id -> status='past_due'
        #      (P1 semantics + grace job take over).
        #    - invoice.paid: same resolution -> status='active'.
        #    - customer.subscription.deleted: resolve via data.object.id ==
        #      provider_subscription_id -> plan_code='free', status='active',
        #      provider_subscription_id CLEARED (Stripe fires this at period
        #      end, so flipping now IS "free at period end"; records untouched,
        #      ADR-012/013). Clearing the link makes late out-of-order
        #      invoice events for the dead subscription no-ops (§12
        #      compare-and-set, never apply-in-arrival-order).
        #    - Unknown/unhandled event types: no exception, no plan/status
        #      change (record-and-ignore is fine).
        # stripe SDK import MUST be lazy (inside functions): with
        # MA3_BILLING_PROVIDER=none nothing may import stripe (§10 P2 b1).

New Settings fields (env-driven; fake values below are the test fixtures —
NEVER real secrets in the repo):
    settings.stripe_secret_key      MA3_STRIPE_SECRET_KEY      default ""
    settings.stripe_webhook_secret  MA3_STRIPE_WEBHOOK_SECRET  default ""
    settings.stripe_price_pro       MA3_STRIPE_PRICE_PRO       default ""
    settings.stripe_price_team      MA3_STRIPE_PRICE_TEAM      default ""

New/changed routes (§8.3/8.4) — gating MUST be evaluated PER REQUEST against
``settings.billing_provider`` (tests monkeypatch the live app; "mounted only
when provider=stripe" must be observable as 404, not require an app rebuild):
    POST /ui/billing/upgrade                  # session + same-origin (§12 CSRF);
                                              # 30x redirect to Checkout url
    POST /ui/orgs/{org_id}/billing/upgrade    # org ADMIN only (member/outsider
                                              # 404); Team price, org BA
    GET  /ui/billing/portal                   # 30x redirect to Customer Portal
    POST /webhooks/stripe                     # NO session/key auth — only the
                                              # Stripe-Signature header; body
                                              # size capped (payloads >1 MiB
                                              # -> 400/413 before verification
                                              # work); 200 on success AND on
                                              # duplicate delivery; 400 on bad
                                              # signature
    provider != "stripe"  ->  ALL FOUR routes return 404 and the stripe SDK
    is never imported (sys.modules stays stripe-free).

UI contract (kept minimal, like P1):
    - provider=stripe: /ui/billing/ contains a real upgrade CTA — a form with
      ``action="/ui/billing/upgrade"`` (the P1 "coming soon" copy must no
      longer be the only path).
    - provider=none: unchanged P1 page — coming_soon copy, NO upgrade form,
      no stripe.com links (BP1-P6 regression).
    - Success URL renders "pending" only; visiting it NEVER changes the plan —
      the webhook is the sole plan writer (§12 success-URL forgery, §10 P2 b2).
    - Observatory reconciliation (§2 P2 last row): /ui/observatory/billing/
      shows provider_subscription_id <-> BA mapping when provider=stripe.

Existing schema reused (P0, no new tables):
    billing_accounts.provider / provider_customer_id / provider_subscription_id
    billing_events(provider, provider_event_id) + partial UNIQUE index
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
import types
from typing import Any

from app.core.config import settings
from app.storage import db

# Re-exported P0/P1 helpers so P2 tests import from one place.
from tests.helpers.billing_p0 import (  # noqa: F401
    auth_headers,
    enable_local_auth,
    error_code,
    fetch_billing_account,
    fetch_billing_account_for_org,
    register_user,
)
from tests.helpers.billing_p1 import set_ba_status  # noqa: F401

# --- Fixture credentials (Decision 1: env-driven price ids; NEVER real) -------

FAKE_SECRET_KEY = "sk_test_fake"
FAKE_WEBHOOK_SECRET = "whsec_test_fake"
FAKE_PRICE_PRO = "price_test_pro"
FAKE_PRICE_TEAM = "price_test_team"

WEBHOOK_TOLERANCE_SECONDS = 300  # §12: reject stale >5 min

P2_SETTINGS = (
    "stripe_secret_key",
    "stripe_webhook_secret",
    "stripe_price_pro",
    "stripe_price_team",
)

_ORIGIN = {"Origin": "http://testserver"}


def require_p2_settings() -> None:
    """Fail with a clear pre-implementation message when P2 config is missing."""
    for name in P2_SETTINGS:
        assert hasattr(settings, name), (
            f"P2 not implemented yet: Settings.{name} "
            "(design/27 §2 P2 config row / §9 Decision 1 env price ids)"
        )


def enable_stripe_provider(monkeypatch) -> None:
    """provider=stripe with fixture credentials (no network, no real secrets)."""
    require_p2_settings()
    monkeypatch.setattr(settings, "billing_provider", "stripe")
    monkeypatch.setattr(settings, "stripe_secret_key", FAKE_SECRET_KEY)
    monkeypatch.setattr(settings, "stripe_webhook_secret", FAKE_WEBHOOK_SECRET)
    monkeypatch.setattr(settings, "stripe_price_pro", FAKE_PRICE_PRO)
    monkeypatch.setattr(settings, "stripe_price_team", FAKE_PRICE_TEAM)


def disable_billing_provider(monkeypatch) -> None:
    monkeypatch.setattr(settings, "billing_provider", "none")


# --- Stripe-Signature scheme (t=<unix>,v1=HMAC_SHA256(secret, f"{t}.{body}")) --

def stripe_sig_header(
    payload: bytes, *, secret: str = FAKE_WEBHOOK_SECRET, timestamp: int | None = None
) -> str:
    ts = int(time.time()) if timestamp is None else int(timestamp)
    signed = f"{ts}.".encode() + payload
    v1 = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={v1}"


def signed_webhook_headers(
    payload: bytes, *, secret: str = FAKE_WEBHOOK_SECRET, timestamp: int | None = None
) -> dict[str, str]:
    return {
        "Stripe-Signature": stripe_sig_header(payload, secret=secret, timestamp=timestamp),
        "Content-Type": "application/json",
    }


# --- Event fixture builders ----------------------------------------------------

_event_seq = 0


def _next_event_id() -> str:
    global _event_seq
    _event_seq += 1
    return f"evt_test_{_event_seq:06d}"


def stripe_event(
    event_type: str,
    data_object: dict[str, Any],
    *,
    event_id: str | None = None,
    created: int | None = None,
) -> dict[str, Any]:
    return {
        "id": event_id or _next_event_id(),
        "object": "event",
        "api_version": "2024-06-20",
        "created": int(time.time()) if created is None else int(created),
        "livemode": False,
        "type": event_type,
        "data": {"object": data_object},
    }


def event_payload(event: dict[str, Any]) -> bytes:
    return json.dumps(event, separators=(",", ":")).encode()


def checkout_completed_event(
    billing_account_id: str,
    *,
    plan_code: str = "pro",
    subscription_id: str = "sub_test_1",
    customer_id: str = "cus_test_1",
    event_id: str | None = None,
) -> dict[str, Any]:
    return stripe_event(
        "checkout.session.completed",
        {
            "id": "cs_test_evtsrc_1",
            "object": "checkout.session",
            "mode": "subscription",
            "status": "complete",
            "payment_status": "paid",
            "client_reference_id": billing_account_id,
            "customer": customer_id,
            "subscription": subscription_id,
            "metadata": {
                "billing_account_id": billing_account_id,
                "plan_code": plan_code,
            },
        },
        event_id=event_id,
    )


def invoice_event(
    kind: str,  # "paid" | "payment_failed"
    *,
    subscription_id: str = "sub_test_1",
    customer_id: str = "cus_test_1",
    event_id: str | None = None,
) -> dict[str, Any]:
    assert kind in ("paid", "payment_failed")
    return stripe_event(
        f"invoice.{kind}",
        {
            "id": "in_test_1",
            "object": "invoice",
            "customer": customer_id,
            "subscription": subscription_id,
            "status": "paid" if kind == "paid" else "open",
            "billing_reason": "subscription_cycle",
        },
        event_id=event_id,
    )


def subscription_deleted_event(
    *,
    subscription_id: str = "sub_test_1",
    customer_id: str = "cus_test_1",
    event_id: str | None = None,
) -> dict[str, Any]:
    return stripe_event(
        "customer.subscription.deleted",
        {
            "id": subscription_id,
            "object": "subscription",
            "customer": customer_id,
            "status": "canceled",
            "cancel_at_period_end": False,
            "current_period_end": int(time.time()),
        },
        event_id=event_id,
    )


# --- Fake stripe SDK (mocked construct_event + Checkout/Portal API, §13:
#     "Stripe tests use a fixture signing secret, no network") ------------------

class FakeSignatureVerificationError(Exception):
    """Mirrors stripe.error.SignatureVerificationError's constructor shape."""

    def __init__(self, message: str = "signature verification failed",
                 sig_header: str | None = None, http_body: Any = None) -> None:
        super().__init__(message)
        self.sig_header = sig_header
        self.http_body = http_body


def _fake_construct_event(
    payload: bytes | str,
    sig_header: str,
    secret: str,
    tolerance: int = WEBHOOK_TOLERANCE_SECONDS,
) -> dict[str, Any]:
    """Faithful re-implementation of stripe.Webhook.construct_event semantics:
    v1 = HMAC-SHA256(secret, f"{t}.{payload}"), abs(now - t) <= tolerance."""
    body = payload.encode() if isinstance(payload, str) else payload
    if not sig_header:
        raise FakeSignatureVerificationError("missing Stripe-Signature", sig_header)
    parts: dict[str, list[str]] = {}
    for chunk in sig_header.split(","):
        key, _, value = chunk.strip().partition("=")
        parts.setdefault(key, []).append(value)
    try:
        ts = int(parts["t"][0])
    except (KeyError, ValueError, IndexError):
        raise FakeSignatureVerificationError("unparseable header", sig_header) from None
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    candidates = parts.get("v1") or []
    if not any(hmac.compare_digest(expected, c) for c in candidates):
        raise FakeSignatureVerificationError("no matching v1 signature", sig_header)
    if tolerance and abs(time.time() - ts) > tolerance:
        raise FakeSignatureVerificationError("timestamp outside tolerance", sig_header)
    return json.loads(body.decode())


class FakeStripe:
    """Handle returned by install_fake_stripe: recorded API calls + the module."""

    def __init__(self) -> None:
        self.checkout_calls: list[dict[str, Any]] = []
        self.portal_calls: list[dict[str, Any]] = []
        self.module = self._build_module()

    def _build_module(self) -> types.ModuleType:
        fake = self

        stripe_mod = types.ModuleType("stripe")
        error_mod = types.ModuleType("stripe.error")
        checkout_mod = types.ModuleType("stripe.checkout")
        portal_mod = types.ModuleType("stripe.billing_portal")

        error_mod.SignatureVerificationError = FakeSignatureVerificationError

        class Webhook:
            construct_event = staticmethod(_fake_construct_event)

        class CheckoutSession:
            @classmethod
            def create(cls, **kwargs: Any) -> dict[str, Any]:
                fake.checkout_calls.append(kwargs)
                session_id = f"cs_test_fake_{len(fake.checkout_calls)}"
                return {
                    "id": session_id,
                    "object": "checkout.session",
                    "url": f"https://checkout.stripe.com/c/pay/{session_id}",
                }

        class PortalSession:
            @classmethod
            def create(cls, **kwargs: Any) -> dict[str, Any]:
                fake.portal_calls.append(kwargs)
                session_id = f"bps_test_fake_{len(fake.portal_calls)}"
                return {
                    "id": session_id,
                    "object": "billing_portal.session",
                    "url": f"https://billing.stripe.com/p/session/{session_id}",
                }

        checkout_mod.Session = CheckoutSession
        portal_mod.Session = PortalSession

        stripe_mod.api_key = None
        stripe_mod.Webhook = Webhook
        stripe_mod.error = error_mod
        stripe_mod.SignatureVerificationError = FakeSignatureVerificationError
        stripe_mod.checkout = checkout_mod
        stripe_mod.billing_portal = portal_mod
        return stripe_mod

    @property
    def last_checkout(self) -> dict[str, Any]:
        assert self.checkout_calls, "stripe.checkout.Session.create was never called"
        return self.checkout_calls[-1]

    @property
    def last_portal(self) -> dict[str, Any]:
        assert self.portal_calls, "stripe.billing_portal.Session.create was never called"
        return self.portal_calls[-1]

    def checkout_price_ids(self, call: dict[str, Any] | None = None) -> list[str]:
        """Price ids from a recorded checkout call's line_items (shape-tolerant)."""
        kwargs = call or self.last_checkout
        items = kwargs.get("line_items") or []
        return [str(item.get("price")) for item in items if isinstance(item, dict)]


def install_fake_stripe(monkeypatch) -> FakeStripe:
    """Put a network-free stripe module into sys.modules (reverted per test).

    The implementation must import stripe LAZILY, so this substitution is what
    its ``import stripe`` resolves to. construct_event reproduces the official
    verification exactly (same v1 HMAC scheme, same 300s tolerance).
    """
    fake = FakeStripe()
    monkeypatch.setitem(sys.modules, "stripe", fake.module)
    monkeypatch.setitem(sys.modules, "stripe.error", fake.module.error)
    monkeypatch.setitem(sys.modules, "stripe.checkout", fake.module.checkout)
    monkeypatch.setitem(sys.modules, "stripe.billing_portal", fake.module.billing_portal)
    return fake


def purge_stripe_modules(monkeypatch) -> None:
    """Remove stripe from sys.modules so a provider=none run proves no import."""
    for name in [m for m in list(sys.modules) if m == "stripe" or m.startswith("stripe.")]:
        monkeypatch.delitem(sys.modules, name)


def stripe_module_names() -> list[str]:
    return sorted(m for m in sys.modules if m == "stripe" or m.startswith("stripe."))


# --- DB inspection / seeding ----------------------------------------------------

def count_provider_events(provider_event_id: str, *, provider: str = "stripe") -> int:
    with db.connect() as conn:
        row = db._fetchone(
            conn,
            "SELECT COUNT(*) AS c FROM billing_events "
            "WHERE provider = ? AND provider_event_id = ?",
            (provider, provider_event_id),
        )
    return int(row["c"]) if row else 0


def ba_plan_status(ba_id: str) -> tuple[str, str]:
    account = fetch_billing_account(ba_id)
    assert account is not None, f"billing account not found: {ba_id}"
    return str(account["plan_code"]), str(account["status"])


def provider_link(ba_id: str) -> dict[str, Any]:
    with db.connect() as conn:
        row = db._fetchone(
            conn,
            "SELECT provider, provider_customer_id, provider_subscription_id "
            "FROM billing_accounts WHERE id = ?",
            (ba_id,),
        )
    assert row is not None, f"billing account not found: {ba_id}"
    return dict(row)


def link_provider_subscription(
    ba_id: str,
    *,
    subscription_id: str | None,
    customer_id: str | None = None,
    provider: str = "stripe",
) -> None:
    """Seed the provider linkage a completed checkout would have persisted."""
    with db.connect() as conn:
        db._execute(
            conn,
            "UPDATE billing_accounts SET provider = ?, provider_customer_id = ?, "
            "provider_subscription_id = ? WHERE id = ?",
            (provider, customer_id, subscription_id, ba_id),
        )
        conn.commit()


def personal_ba_for(principal_id: str, display_name: str) -> str:
    """Personal-org BA id, bootstrapping the personal org when needed."""
    from app.services.onboarding_service import ensure_personal_org, personal_org_id

    ensure_personal_org(principal_id, display_name)
    account = fetch_billing_account_for_org(personal_org_id(principal_id))
    assert account is not None
    return str(account["id"])
