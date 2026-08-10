"""Stripe Checkout / Portal / webhook handlers (lazy SDK import).

Only call into this module when ``settings.billing_provider == "stripe"``.
Importing this package must not import the ``stripe`` SDK — imports happen
inside functions so ``MA3_BILLING_PROVIDER=none`` stays stripe-free.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.core.config import settings
from app.services import billing_service
from app.storage import db

logger = logging.getLogger(__name__)

WEBHOOK_TOLERANCE_SECONDS = 300
WEBHOOK_MAX_BODY_BYTES = 1 * 1024 * 1024


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _require_stripe_provider() -> None:
    if settings.billing_provider != "stripe":
        raise HTTPException(status_code=404, detail="not found")


def _stripe():
    """Lazy import so provider=none paths never load the SDK."""
    import stripe  # noqa: WPS433 — intentional lazy import

    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="stripe not configured")
    stripe.api_key = settings.stripe_secret_key
    return stripe


def _price_for_plan(plan_code: str) -> str:
    if plan_code == "pro":
        price = settings.stripe_price_pro
    elif plan_code == "team":
        price = settings.stripe_price_team
    else:
        raise HTTPException(status_code=400, detail={"error": "unsupported_plan"})
    if not price:
        raise HTTPException(status_code=503, detail={"error": "stripe_price_missing"})
    return price


def _default_urls(base: str) -> tuple[str, str]:
    root = (base or settings.public_base_url or "").rstrip("/")
    return f"{root}/ui/billing/?checkout=success", f"{root}/ui/billing/?checkout=cancel"


def create_checkout_session(
    billing_account_id: str,
    *,
    plan_code: str,
    success_url: str | None = None,
    cancel_url: str | None = None,
) -> dict[str, Any]:
    _require_stripe_provider()
    account = billing_service.get_billing_account(billing_account_id)
    if not account:
        raise HTTPException(status_code=404, detail={"error": "billing_account_not_found"})
    price = _price_for_plan(plan_code)
    default_success, default_cancel = _default_urls(settings.public_base_url)
    stripe = _stripe()
    kwargs: dict[str, Any] = {
        "mode": "subscription",
        "client_reference_id": billing_account_id,
        "metadata": {
            "billing_account_id": billing_account_id,
            "plan_code": plan_code,
        },
        "line_items": [{"price": price, "quantity": 1}],
        "success_url": success_url or default_success,
        "cancel_url": cancel_url or default_cancel,
        "payment_method_types": ["card", "link"],
    }
    customer_id = account.get("provider_customer_id")
    if customer_id:
        kwargs["customer"] = str(customer_id)
    session = stripe.checkout.Session.create(**kwargs)
    return {"id": session["id"], "url": session["url"]}


def create_portal_session(
    billing_account_id: str,
    *,
    return_url: str | None = None,
) -> dict[str, Any]:
    _require_stripe_provider()
    account = billing_service.get_billing_account(billing_account_id)
    if not account:
        raise HTTPException(status_code=404, detail={"error": "billing_account_not_found"})
    customer_id = account.get("provider_customer_id")
    if not customer_id:
        raise HTTPException(status_code=400, detail={"error": "stripe_customer_missing"})
    stripe = _stripe()
    session = stripe.billing_portal.Session.create(
        customer=str(customer_id),
        return_url=return_url
        or f"{(settings.public_base_url or '').rstrip('/')}/ui/billing/",
    )
    return {"url": session["url"]}


def _insert_event_row(event_id: str, event_type: str, ba_id: str | None, payload: bytes) -> bool:
    """Insert-first idempotency. Returns False if the event was already recorded."""
    now = _now_iso()
    try:
        with db.connect() as conn:
            db._execute(
                conn,
                """
                INSERT INTO billing_events (
                  id, provider, provider_event_id, type, billing_account_id,
                  payload_json, processed_at, created_at
                ) VALUES (?, 'stripe', ?, ?, ?, ?, ?, ?)
                """,
                (
                    db.new_id("be"),
                    event_id,
                    event_type,
                    ba_id,
                    payload.decode("utf-8", errors="replace")[:200_000],
                    now,
                    now,
                ),
            )
        return True
    except Exception as exc:
        # SQLite IntegrityError / Postgres UniqueViolation → duplicate delivery.
        name = type(exc).__name__.lower()
        msg = str(exc).lower()
        if "unique" in name or "integrity" in name or "unique" in msg or "duplicate" in msg:
            return False
        cause = getattr(exc, "__cause__", None) or getattr(exc, "orig", None)
        if cause is not None:
            cmsg = str(cause).lower()
            cname = type(cause).__name__.lower()
            if "unique" in cname or "integrity" in cname or "unique" in cmsg or "duplicate" in cmsg:
                return False
        raise


def _ba_by_subscription(subscription_id: str) -> dict[str, Any] | None:
    if not subscription_id:
        return None
    with db.connect() as conn:
        row = db._fetchone(
            conn,
            "SELECT * FROM billing_accounts WHERE provider_subscription_id = ?",
            (subscription_id,),
        )
    return dict(row) if row else None


def _set_provider_link(
    ba_id: str,
    *,
    customer_id: str | None,
    subscription_id: str | None,
    provider: str | None = "stripe",
) -> None:
    with db.connect() as conn:
        db._execute(
            conn,
            """
            UPDATE billing_accounts
            SET provider = ?, provider_customer_id = ?, provider_subscription_id = ?
            WHERE id = ?
            """,
            (provider, customer_id, subscription_id, ba_id),
        )


def _handle_checkout_completed(obj: dict[str, Any]) -> str | None:
    metadata = obj.get("metadata") or {}
    ba_id = str(metadata.get("billing_account_id") or obj.get("client_reference_id") or "")
    plan_code = str(metadata.get("plan_code") or "")
    if not ba_id or plan_code not in {"pro", "team"}:
        logger.warning("checkout.session.completed missing ba/plan metadata: %s", metadata)
        return None
    billing_service.set_billing_account_plan(ba_id, plan_code=plan_code, status="active")
    _set_provider_link(
        ba_id,
        customer_id=str(obj.get("customer") or "") or None,
        subscription_id=str(obj.get("subscription") or "") or None,
    )
    return ba_id


def _handle_invoice(obj: dict[str, Any], *, status: str) -> str | None:
    subscription_id = str(obj.get("subscription") or "")
    account = _ba_by_subscription(subscription_id)
    if not account:
        return None
    ba_id = str(account["id"])
    billing_service.set_billing_account_plan(ba_id, status=status)
    return ba_id


def _handle_subscription_deleted(obj: dict[str, Any]) -> str | None:
    subscription_id = str(obj.get("id") or "")
    account = _ba_by_subscription(subscription_id)
    if not account:
        return None
    ba_id = str(account["id"])
    billing_service.set_billing_account_plan(ba_id, plan_code="free", status="active")
    _set_provider_link(
        ba_id,
        customer_id=str(account.get("provider_customer_id") or "") or None,
        subscription_id=None,
        provider="stripe",
    )
    return ba_id


def handle_webhook_event(payload: bytes, sig_header: str) -> dict[str, Any]:
    _require_stripe_provider()
    if len(payload) > WEBHOOK_MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="payload too large")
    stripe = _stripe()
    secret = settings.stripe_webhook_secret
    if not secret:
        raise HTTPException(status_code=503, detail="stripe webhook secret missing")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header or "", secret, tolerance=WEBHOOK_TOLERANCE_SECONDS
        )
    except Exception as exc:
        # SignatureVerificationError and ValueError both map to 400.
        raise HTTPException(status_code=400, detail="invalid stripe signature") from exc

    # Mapping-style access so tests can inject a plain dict.
    event_id = str(event["id"])
    event_type = str(event["type"])
    data_object = event["data"]["object"]

    ba_hint: str | None = None
    if event_type == "checkout.session.completed":
        meta = data_object.get("metadata") or {}
        ba_hint = str(meta.get("billing_account_id") or data_object.get("client_reference_id") or "") or None
    elif event_type in {"invoice.payment_failed", "invoice.paid"}:
        acc = _ba_by_subscription(str(data_object.get("subscription") or ""))
        ba_hint = str(acc["id"]) if acc else None
    elif event_type == "customer.subscription.deleted":
        acc = _ba_by_subscription(str(data_object.get("id") or ""))
        ba_hint = str(acc["id"]) if acc else None

    inserted = _insert_event_row(event_id, event_type, ba_hint, payload)
    if not inserted:
        return {"ok": True, "duplicate": True, "type": event_type}

    ba_id: str | None = None
    if event_type == "checkout.session.completed":
        ba_id = _handle_checkout_completed(data_object)
    elif event_type == "invoice.payment_failed":
        ba_id = _handle_invoice(data_object, status="past_due")
    elif event_type == "invoice.paid":
        ba_id = _handle_invoice(data_object, status="active")
    elif event_type == "customer.subscription.deleted":
        ba_id = _handle_subscription_deleted(data_object)
    # Unknown types: recorded, ignored.

    if ba_id and ba_hint != ba_id:
        with db.connect() as conn:
            db._execute(
                conn,
                "UPDATE billing_events SET billing_account_id = ? "
                "WHERE provider = 'stripe' AND provider_event_id = ?",
                (ba_id, event_id),
            )

    return {"ok": True, "duplicate": False, "type": event_type, "billing_account_id": ba_id}
