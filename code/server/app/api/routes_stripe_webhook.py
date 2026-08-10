"""Stripe webhook endpoint (signature-only auth; gated by billing_provider)."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.config import settings

router = APIRouter(tags=["billing-webhooks"])


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> JSONResponse:
    if settings.billing_provider != "stripe":
        raise HTTPException(status_code=404, detail="not found")
    body = await request.body()
    from app.services import stripe_billing_service

    result = stripe_billing_service.handle_webhook_event(body, stripe_signature or "")
    return JSONResponse(result)
