"""P2 Stripe webhook unit scenarios (design/27 §8.4, §10 P2, §12, §13).

Contract under test: ``app.services.stripe_billing_service.handle_webhook_event``
(payload: bytes, sig_header: str) — signature verification via the SDK's
``stripe.Webhook.construct_event`` (here substituted by a faithful fake with
the same v1 HMAC scheme and 300s tolerance), insert-first idempotency on
``billing_events(provider='stripe', provider_event_id)``, and the four state
handlers:

- checkout.session.completed  -> plan from metadata, status active, provider
  customer/subscription persisted (§10 P2 bullet 2: webhook is the sole writer)
- invoice.payment_failed      -> status past_due (P1 semantics take over)
- invoice.paid                -> status active
- customer.subscription.deleted -> plan free "at period end" (Stripe fires the
  event at period end), provider_subscription_id cleared so late out-of-order
  invoice events are no-ops (§12 compare-and-set)

Bad/missing signature or stale (>5 min) timestamp -> HTTPException(400) with
NO billing_events row and NO state change (§10 P2 bullet 3).

SKIPS until Composer lands ``app.services.stripe_billing_service``.
"""
from __future__ import annotations

import time

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.storage import db
from app.storage.db import initialize_database
from tests.helpers.billing_p2 import (
    FAKE_WEBHOOK_SECRET,
    ba_plan_status,
    checkout_completed_event,
    count_provider_events,
    enable_stripe_provider,
    event_payload,
    install_fake_stripe,
    invoice_event,
    link_provider_subscription,
    personal_ba_for,
    provider_link,
    stripe_sig_header,
    subscription_deleted_event,
)

stripe_billing_service = pytest.importorskip(
    "app.services.stripe_billing_service",
    reason="P2 not implemented yet: app.services.stripe_billing_service (design/27 §2 P2)",
)

pytestmark = pytest.mark.billing_p2


@pytest.fixture()
def p2_db(tmp_path, monkeypatch):
    db_path = tmp_path / "billing-p2-webhook.db"
    monkeypatch.setenv("MA3_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    initialize_database()


@pytest.fixture(autouse=True)
def stripe_env(p2_db, monkeypatch):
    """provider=stripe + fixture credentials + network-free fake stripe SDK."""
    enable_stripe_provider(monkeypatch)
    return install_fake_stripe(monkeypatch)


@pytest.fixture()
def ba_id() -> str:
    db.upsert_user_principal(sso_user="p2-webhook", display_name="p2-webhook")
    return personal_ba_for("user:p2-webhook", "p2-webhook")


def deliver(event: dict, *, secret: str = FAKE_WEBHOOK_SECRET, timestamp: int | None = None):
    payload = event_payload(event)
    return stripe_billing_service.handle_webhook_event(
        payload, stripe_sig_header(payload, secret=secret, timestamp=timestamp)
    )


def assert_rejected_without_side_effects(event: dict, ba_id: str, **sign_kwargs) -> None:
    plan_before = ba_plan_status(ba_id)
    with pytest.raises(HTTPException) as exc_info:
        deliver(event, **sign_kwargs)
    assert exc_info.value.status_code == 400, (
        "verification failure must map to HTTP 400 (§10 P2 bullet 3), "
        f"got {exc_info.value.status_code}"
    )
    assert count_provider_events(event["id"]) == 0, (
        "a rejected webhook must not leave a billing_events row (§10 P2 bullet 3)"
    )
    assert ba_plan_status(ba_id) == plan_before, "rejected webhook changed BA state"


# --- BP2-W1/W2/W3: signature and staleness gates ---------------------------------

def test_bad_signature_rejected(ba_id):
    event = checkout_completed_event(ba_id)
    assert_rejected_without_side_effects(event, ba_id, secret="whsec_wrong_secret")


def test_missing_or_garbage_signature_rejected(ba_id):
    event = checkout_completed_event(ba_id)
    payload = event_payload(event)
    for sig_header in ("", "t=abc,v1=deadbeef", "v1=deadbeef"):
        with pytest.raises(HTTPException) as exc_info:
            stripe_billing_service.handle_webhook_event(payload, sig_header)
        assert exc_info.value.status_code == 400, f"sig_header={sig_header!r}"
    assert count_provider_events(event["id"]) == 0
    assert ba_plan_status(ba_id) == ("free", "active")


def test_stale_timestamp_rejected(ba_id):
    """Valid HMAC but t older than the 5-minute tolerance -> 400 (§12)."""
    event = checkout_completed_event(ba_id)
    assert_rejected_without_side_effects(
        event, ba_id, timestamp=int(time.time()) - 360
    )


# --- BP2-W4/W5: checkout.session.completed activates via webhook only -------------

def test_checkout_completed_activates_pro_plan(ba_id):
    assert ba_plan_status(ba_id) == ("free", "active")
    event = checkout_completed_event(
        ba_id, plan_code="pro", subscription_id="sub_w4", customer_id="cus_w4"
    )
    deliver(event)

    assert ba_plan_status(ba_id) == ("pro", "active"), (
        "checkout.session.completed must activate the plan from metadata.plan_code"
    )
    link = provider_link(ba_id)
    assert link["provider"] == "stripe"
    assert link["provider_customer_id"] == "cus_w4"
    assert link["provider_subscription_id"] == "sub_w4"
    assert count_provider_events(event["id"]) == 1, (
        "processed event must be recorded in billing_events with its "
        "provider_event_id (§8.4 idempotency)"
    )


def test_checkout_completed_activates_team_plan_on_org_ba(monkeypatch):
    from app.services.org_service import create_team_org
    from tests.helpers.billing_p2 import fetch_billing_account_for_org

    owner_pid = "user:p2-team-owner"
    db.upsert_user_principal(sso_user="p2-team-owner", display_name="p2-team-owner")
    personal_ba_for(owner_pid, "p2-team-owner")
    monkeypatch.setattr(settings, "paid_principal_ids", (owner_pid,))
    org = create_team_org(name="P2 Webhook Team", owner_principal_id=owner_pid)
    org_ba = str(fetch_billing_account_for_org(str(org["id"]))["id"])

    deliver(
        checkout_completed_event(
            org_ba, plan_code="team", subscription_id="sub_team_1", customer_id="cus_team_1"
        )
    )
    assert ba_plan_status(org_ba) == ("team", "active"), (
        "Team checkout must upgrade the org BA to the full team plan (§7 org upgrade path)"
    )


def test_replay_same_event_id_mutates_state_once(ba_id):
    from app.services import billing_service

    event = checkout_completed_event(ba_id, event_id="evt_replay_1")
    deliver(event)
    assert ba_plan_status(ba_id)[0] == "pro"

    # Force a divergent state, then replay the identical delivery: a true
    # idempotent handler must NOT re-apply the activation (§10 P2 bullet 2).
    billing_service.set_billing_account_plan(ba_id, plan_code="free")
    deliver(event)
    assert ba_plan_status(ba_id)[0] == "free", (
        "same provider_event_id delivered twice must mutate state once"
    )
    assert count_provider_events("evt_replay_1") == 1, (
        "billing_events must hold exactly one row per provider_event_id "
        "(partial UNIQUE index, insert-first)"
    )


# --- BP2-W6/W7: invoice lifecycle -------------------------------------------------

def test_invoice_payment_failed_sets_past_due(ba_id):
    link_provider_subscription(ba_id, subscription_id="sub_w6", customer_id="cus_w6")
    deliver(invoice_event("payment_failed", subscription_id="sub_w6"))
    assert ba_plan_status(ba_id)[1] == "past_due", (
        "invoice.payment_failed must flip the linked BA to past_due (§10 P2 bullet 4)"
    )


def test_invoice_paid_restores_active(ba_id):
    link_provider_subscription(ba_id, subscription_id="sub_w7", customer_id="cus_w7")
    deliver(invoice_event("payment_failed", subscription_id="sub_w7"))
    assert ba_plan_status(ba_id)[1] == "past_due"

    deliver(invoice_event("paid", subscription_id="sub_w7"))
    assert ba_plan_status(ba_id)[1] == "active", (
        "invoice.paid must restore the BA to active (§10 P2 bullet 4)"
    )


# --- BP2-W8/W9: subscription deletion + out-of-order guard -------------------------

def test_subscription_deleted_reverts_to_free_and_clears_link(ba_id):
    deliver(checkout_completed_event(ba_id, plan_code="pro", subscription_id="sub_w8"))
    assert ba_plan_status(ba_id)[0] == "pro"

    deliver(subscription_deleted_event(subscription_id="sub_w8"))
    plan, status = ba_plan_status(ba_id)
    assert plan == "free", (
        "customer.subscription.deleted arrives at period end -> plan reverts to "
        "free (§10 P2 bullet 4); records are never touched (ADR-012/013)"
    )
    assert status != "past_due"
    assert not provider_link(ba_id)["provider_subscription_id"], (
        "the dead subscription link must be cleared so late events can't match it"
    )


def test_out_of_order_invoice_after_deletion_is_noop(ba_id):
    deliver(checkout_completed_event(ba_id, plan_code="pro", subscription_id="sub_w9"))
    deliver(subscription_deleted_event(subscription_id="sub_w9"))
    assert ba_plan_status(ba_id)[0] == "free"

    # A late invoice.paid for the dead subscription (fresh event id, so
    # idempotency alone cannot save us) must not resurrect the paid plan.
    deliver(invoice_event("paid", subscription_id="sub_w9"))
    assert ba_plan_status(ba_id) == ("free", "active"), (
        "out-of-order events must be compare-and-set against subscription "
        "state, never applied in arrival order (§12)"
    )


# --- BP2-W10: unknown event types are safe -----------------------------------------

def test_unknown_event_type_is_ignored_without_error(ba_id):
    from tests.helpers.billing_p2 import stripe_event

    before = ba_plan_status(ba_id)
    event = stripe_event(
        "charge.succeeded", {"id": "ch_test_1", "object": "charge", "amount": 900}
    )
    deliver(event)  # must not raise
    assert ba_plan_status(ba_id) == before, "unhandled event types must not change state"
