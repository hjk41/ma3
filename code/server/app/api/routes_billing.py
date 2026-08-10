"""Billing summaries, portal pages, and Stripe upgrade/portal routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app.api import ui_session
from app.api.ui_i18n import html_response, ui_locale
from app.api.ui_theme import esc, render_page
from app.core.config import settings
from app.core.security import assert_same_origin
from app.services import billing_service, usage_service
from app.services.onboarding_service import ensure_personal_org, personal_org_id
from app.services.org_service import assert_org_admin
from app.services.portal_actor_service import PortalActor, require_portal_actor
from app.storage import db

router = APIRouter(tags=["billing"])


def _stripe_enabled() -> bool:
    return settings.billing_provider == "stripe"


def _require_stripe_routes() -> None:
    if not _stripe_enabled():
        raise HTTPException(status_code=404, detail="not found")


def billing_summary_for_ba(ba_id: str) -> dict:
    account = billing_service.get_billing_account(ba_id)
    if not account:
        raise HTTPException(status_code=404, detail="billing account not found")
    reads = usage_service.read_quota_state(ba_id)
    org = db.get_organization(str(account["owner_id"])) if account["owner_type"] == "org" else None
    storage_used = db.sum_org_storage_bytes(str(org["id"])) if org else 0
    seats = billing_service.seat_usage(str(org["id"])) if org else {"used": 0, "included_seats": 0}
    plan_code = str(account["plan_code"])
    if org and org.get("kind") == "personal" and org.get("owner_principal_id") in settings.paid_principal_ids:
        plan_code = "pro"
    return {
        "plan_code": plan_code,
        "status": account["status"],
        "read_units": {"used": reads["used"], "limit": reads["limit"]},
        "storage": {
            "used": storage_used,
            "limit": billing_service.effective_quota(ba_id, "storage_bytes_total"),
        },
        "seats": {"used": seats["used"], "limit": seats["included_seats"]},
        "keys": {
            "used": 0,
            "limit": billing_service.effective_quota(ba_id, "max_keys"),
        },
        "provider_customer_id": account.get("provider_customer_id"),
        "provider_subscription_id": account.get("provider_subscription_id"),
    }


def _personal_ba(principal_id: str, display_name: str) -> str:
    ensure_personal_org(principal_id, display_name)
    account = billing_service.get_billing_account_for_org(personal_org_id(principal_id))
    if not account:
        raise HTTPException(status_code=404, detail="billing account not found")
    return str(account["id"])


@router.get("/api/me/billing")
def api_me_billing(actor: PortalActor = Depends(require_portal_actor)) -> JSONResponse:
    return JSONResponse(billing_summary_for_ba(_personal_ba(actor.principal_id, actor.display_name)))


@router.get("/api/orgs/{org_id}/billing")
def api_org_billing(org_id: str, actor: PortalActor = Depends(require_portal_actor)) -> JSONResponse:
    assert_org_admin(org_id, actor.principal_id)
    account = billing_service.get_billing_account_for_org(org_id)
    if not account:
        raise HTTPException(status_code=404, detail="organization not found")
    return JSONResponse(billing_summary_for_ba(str(account["id"])))


def _cta_block(
    *,
    t,
    summary: dict,
    upgrade_action: str,
    show_portal: bool,
    checkout: str | None,
) -> str:
    parts: list[str] = []
    if checkout == "success":
        parts.append(f'<div class="alert info" id="checkout-pending">{esc(t("billing.checkout_pending"))}</div>')
    elif checkout == "cancel":
        parts.append(f'<div class="alert warning">{esc(t("billing.checkout_cancel"))}</div>')

    if _stripe_enabled():
        plan = str(summary.get("plan_code") or "")
        is_org_upgrade = "/ui/orgs/" in upgrade_action
        show_upgrade = (not is_org_upgrade and plan == "free") or (
            is_org_upgrade and plan in {"team_stub", "free"}
        )
        if show_upgrade:
            parts.append(
                f'<form method="post" action="{esc(upgrade_action)}" style="margin-top:12px;">'
                f'<button type="submit" class="btn primary">{esc(t("billing.upgrade"))}</button>'
                f"</form>"
            )
        if show_portal and summary.get("provider_customer_id"):
            parts.append(
                f'<p style="margin-top:12px;"><a class="btn" href="/ui/billing/portal">'
                f'{esc(t("billing.manage_subscription"))}</a></p>'
            )
    else:
        parts.append(f"<p>{esc(t('billing.coming_soon'))}</p>")
    return "\n".join(parts)


def _render(
    request: Request,
    *,
    user,
    summary: dict,
    upgrade_action: str = "/ui/billing/upgrade",
    show_portal: bool = True,
) -> HTMLResponse:
    locale, t = ui_locale(request)
    title = t("nav.billing")
    checkout = request.query_params.get("checkout")
    banner = (
        f'<div id="past-due-banner" class="alert warning">{esc(t("billing.past_due"))}</div>'
        if summary["status"] == "past_due"
        else ""
    )
    cta = _cta_block(
        t=t,
        summary=summary,
        upgrade_action=upgrade_action,
        show_portal=show_portal,
        checkout=checkout,
    )
    body = f"""
      {banner}
      <div class="card"><div class="card-header"><h2>{esc(title)}</h2></div>
      <div class="card-body">
        <p>{esc(t("billing.plan"))}: {esc(summary["plan_code"])}</p>
        <p>{esc(t("billing.reads"))}: {summary["read_units"]["used"]} / {summary["read_units"]["limit"]}</p>
        <p>{esc(t("billing.storage"))}: {summary["storage"]["used"]} / {summary["storage"]["limit"]}</p>
        {cta}
      </div></div>"""
    return html_response(
        request,
        render_page(
            title=title,
            base=str(request.base_url).rstrip("/"),
            active_nav="billing",
            subtitle=t("billing.subtitle"),
            user_line=user.display_name,
            show_logout=True,
            is_admin=user.is_admin,
            body=body,
            locale=locale,
            request=request,
        ),
    )


@router.get("/ui/billing/", response_class=HTMLResponse)
def ui_billing(request: Request) -> Response:
    user = ui_session.resolve_session_user(request)
    if user is None:
        return RedirectResponse(f"/auth/login?next={request.url.path}", status_code=302)
    return _render(
        request,
        user=user,
        summary=billing_summary_for_ba(_personal_ba(user.principal_id, user.display_name)),
    )


@router.get("/ui/orgs/{org_id}/billing/", response_class=HTMLResponse)
def ui_org_billing(request: Request, org_id: str) -> Response:
    user = ui_session.resolve_session_user(request)
    if user is None:
        return RedirectResponse(f"/auth/login?next={request.url.path}", status_code=302)
    assert_org_admin(org_id, user.principal_id)
    account = billing_service.get_billing_account_for_org(org_id)
    if not account:
        raise HTTPException(status_code=404, detail="organization not found")
    return _render(
        request,
        user=user,
        summary=billing_summary_for_ba(str(account["id"])),
        upgrade_action=f"/ui/orgs/{org_id}/billing/upgrade",
        show_portal=False,
    )


@router.post("/ui/billing/upgrade")
def ui_billing_upgrade(request: Request) -> Response:
    _require_stripe_routes()
    assert_same_origin(request)
    user = ui_session.resolve_session_user(request)
    if user is None:
        return RedirectResponse(f"/auth/login?next={request.url.path}", status_code=302)
    from app.services import stripe_billing_service

    ba_id = _personal_ba(user.principal_id, user.display_name)
    base = str(request.base_url).rstrip("/")
    session = stripe_billing_service.create_checkout_session(
        ba_id,
        plan_code="pro",
        success_url=f"{base}/ui/billing/?checkout=success",
        cancel_url=f"{base}/ui/billing/?checkout=cancel",
    )
    return RedirectResponse(session["url"], status_code=303)


@router.post("/ui/orgs/{org_id}/billing/upgrade")
def ui_org_billing_upgrade(request: Request, org_id: str) -> Response:
    _require_stripe_routes()
    assert_same_origin(request)
    user = ui_session.resolve_session_user(request)
    if user is None:
        return RedirectResponse(f"/auth/login?next={request.url.path}", status_code=302)
    assert_org_admin(org_id, user.principal_id)
    account = billing_service.get_billing_account_for_org(org_id)
    if not account:
        raise HTTPException(status_code=404, detail="organization not found")
    from app.services import stripe_billing_service

    base = str(request.base_url).rstrip("/")
    session = stripe_billing_service.create_checkout_session(
        str(account["id"]),
        plan_code="team",
        success_url=f"{base}/ui/orgs/{org_id}/billing/?checkout=success",
        cancel_url=f"{base}/ui/orgs/{org_id}/billing/?checkout=cancel",
    )
    return RedirectResponse(session["url"], status_code=303)


@router.get("/ui/billing/portal")
def ui_billing_portal(request: Request) -> Response:
    _require_stripe_routes()
    user = ui_session.resolve_session_user(request)
    if user is None:
        return RedirectResponse(f"/auth/login?next={request.url.path}", status_code=302)
    from app.services import stripe_billing_service

    ba_id = _personal_ba(user.principal_id, user.display_name)
    base = str(request.base_url).rstrip("/")
    session = stripe_billing_service.create_portal_session(
        ba_id, return_url=f"{base}/ui/billing/"
    )
    return RedirectResponse(session["url"], status_code=303)
