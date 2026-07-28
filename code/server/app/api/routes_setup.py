"""Self-host first-run setup wizard (/ui/setup/)."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.api.ui_i18n import html_response, tr, ui_locale
from app.api.ui_session import resolve_ui_user, ui_user_line
from app.api.ui_theme import esc, render_page, render_password_input
from app.core.config import settings
from app.core.security import assert_same_origin as _assert_same_origin
from app.services import setup_service

router = APIRouter(tags=["setup"])


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _done(label: str) -> str:
    return f'<span style="color:var(--ok,#1a7f37);">☑ {esc(label)}</span>'


def _todo(label: str) -> str:
    return f'<span>☐ {esc(label)}</span>'


def _soft(label: str) -> str:
    return f'<span class="card-muted">○ {esc(label)}</span>'


def _setup_page_kwargs(request: Request, *, locale: str, user) -> dict:
    """Header: hide login on empty instance; show session when logged in."""
    if user is not None:
        return {
            "show_minimal_header": True,
            "show_login": False,
            "show_logout": True,
            "user_line": ui_user_line(user),
            "is_admin": bool(user.is_admin),
            "locale": locale,
            "request": request,
        }
    return {
        "show_minimal_header": True,
        "show_login": False,  # avoid login→setup bounce before owner exists / during ramp anon
        "locale": locale,
        "request": request,
    }


def _render_needs_owner(request: Request, *, error: str = "") -> HTMLResponse:
    locale, t = ui_locale(request)
    base = _base(request)
    err = f'<div class="alert error">{esc(error)}</div>' if error else ""
    show = t("auth.local.show_password")
    hide = t("auth.local.hide_password")
    pw_fields = render_password_input(
        name="password",
        label=t("auth.local.password"),
        autocomplete="new-password",
        show_label=show,
        hide_label=hide,
    ) + render_password_input(
        name="password_confirm",
        label=t("auth.local.password_confirm"),
        autocomplete="new-password",
        show_label=show,
        hide_label=hide,
    )
    mismatch = esc(t("auth.local.password_mismatch"))
    body = f"""
  <div class="card" style="margin-top:24px;max-width:520px;">
    <div class="card-header"><h1 style="margin:0;font-size:20px;">{esc(t("setup.admin_title"))}</h1></div>
    <div class="card-body">
      <p class="card-muted">{esc(t("setup.admin_lead"))}</p>
      {err}
      <form method="post" action="{esc(base)}/auth/register"
            onsubmit="return ma3CheckPasswordConfirm(this)"
            data-password-mismatch="{mismatch}">
        <input type="hidden" name="next" value="{esc(base)}/ui/setup/" />
        <label style="display:block;margin:12px 0 4px;">{esc(t("auth.local.username"))}</label>
        <input name="username" type="text" required autocomplete="username" style="width:100%;max-width:360px;" />
        {pw_fields}
        <label style="display:block;margin:12px 0 4px;">{esc(t("auth.local.display_name"))}</label>
        <input name="display_name" type="text" maxlength="32" placeholder="{esc(t("auth.local.display_name_hint"))}" style="width:100%;max-width:360px;" />
        <div class="actions" style="margin-top:16px;">
          <button type="submit" class="btn primary">{esc(t("setup.admin_submit"))}</button>
        </div>
      </form>
      <p class="card-muted" style="margin-top:16px;">
        {esc(t("setup.mcp_secondary"))}
        <a href="{esc(base)}/mcp/info">{esc(t("setup.mcp_link"))}</a>
      </p>
    </div>
  </div>"""
    return html_response(
        request,
        render_page(
            title=t("setup.admin_title"),
            base=base,
            active_nav="",
            body=body,
            brand_href=f"{base}/ui/setup/",
            **_setup_page_kwargs(request, locale=locale, user=None),
        ),
    )


def _render_guided_ramp(request: Request) -> HTMLResponse:
    locale, t = ui_locale(request)
    base = _base(request)
    user = resolve_ui_user(request)
    status = setup_service.checklist_status()
    flash_ok = (request.query_params.get("ok") or "").strip()
    flash_err = (request.query_params.get("error") or "").strip()
    flash = ""
    if flash_err:
        flash = f'<div class="alert error">{esc(flash_err)}</div>'
    elif flash_ok:
        flash = f'<div class="alert success">{esc(flash_ok)}</div>'

    c1 = _done(t("setup.c1"))
    c3 = _done(t("setup.c3")) if status["has_admin_key"] else _todo(t("setup.c3"))
    c4 = (
        _done(t("setup.c4"))
        if status["registration_handled"]
        else _todo(t("setup.c4"))
    )
    c5 = _soft(t("setup.c5"))

    login_hint = ""
    if user is None:
        login_hint = (
            f'<div class="alert info">{esc(t("setup.login_to_continue"))} '
            f'<a href="{esc(base)}/auth/login?next={esc(base)}/ui/setup/">{esc(t("auth.local.login_link"))}</a></div>'
        )
    elif not user.is_admin:
        login_hint = f'<div class="alert info">{esc(t("setup.admin_only_actions"))}</div>'

    key_action = ""
    if not status["has_admin_key"]:
        key_action = (
            f'<a class="btn primary" href="{esc(base)}/ui/keys/">{esc(t("setup.go_mint_key"))}</a>'
        )

    reg_actions = ""
    if not status["registration_handled"] and user and user.is_admin:
        reg_actions = f"""
        <form method="post" action="{esc(base)}/ui/setup/registration" style="display:inline;">
          <input type="hidden" name="open" value="0" />
          <button type="submit" class="btn primary">{esc(t("setup.close_registration"))}</button>
        </form>
        <form method="post" action="{esc(base)}/ui/setup/registration-ack" style="display:inline;margin-left:8px;">
          <button type="submit" class="btn">{esc(t("setup.keep_registration"))}</button>
        </form>
        """
    elif status["registration_open"] and status["registration_handled"]:
        reg_actions = f'<span class="card-muted">{esc(t("setup.kept_open_note"))}</span>'
    elif not status["registration_open"]:
        reg_actions = f'<span class="card-muted">{esc(t("setup.closed_note"))}</span>'
        if user and user.is_admin:
            reg_actions += f"""
            <form method="post" action="{esc(base)}/ui/setup/registration" style="display:inline;margin-left:8px;">
              <input type="hidden" name="open" value="1" />
              <button type="submit" class="btn">{esc(t("setup.reopen_registration"))}</button>
            </form>
            """

    complete_btn = ""
    if user and user.is_admin:
        can_finish = bool(status["checklist_ready"])
        complete_btn = f"""
        <form method="post" action="{esc(base)}/ui/setup/complete" style="margin-top:20px;">
          <button type="submit" class="btn primary" {"disabled" if not can_finish else ""}>
            {esc(t("setup.finish"))}
          </button>
          <p class="card-muted" style="margin-top:8px;">{esc(t("setup.finish_hint"))}</p>
        </form>
        """

    skip_links = f"""
      <p class="card-muted" style="margin-top:16px;">
        <a href="{esc(base)}/ui/me/">{esc(t("setup.skip_portal"))}</a>
      </p>
    """

    body = f"""
  <div class="card" style="margin-top:24px;max-width:640px;">
    <div class="card-header"><h1 style="margin:0;font-size:20px;">{esc(t("setup.ramp_title"))}</h1></div>
    <div class="card-body">
      <p class="card-muted">{esc(t("setup.ramp_lead"))}</p>
      {flash}
      {login_hint}
      <ul style="list-style:none;padding:0;margin:16px 0;line-height:1.9;">
        <li>{c1}</li>
        <li>{c3} {key_action}</li>
        <li>{c4} {reg_actions}</li>
        <li>{c5}
          <a class="btn" href="{esc(base)}/mcp/info">{esc(t("setup.mcp_docs"))}</a>
          <a class="btn subtle" href="{esc(base)}/client/agent-onboarding.md">{esc(t("setup.onboarding"))}</a>
        </li>
      </ul>
      {complete_btn}
      {skip_links}
    </div>
  </div>"""
    return html_response(
        request,
        render_page(
            title=t("setup.ramp_title"),
            base=base,
            active_nav="",
            body=body,
            brand_href=f"{base}/ui/setup/",
            **_setup_page_kwargs(request, locale=locale, user=user),
        ),
    )


@router.get("/ui/setup", response_class=HTMLResponse)
@router.get("/ui/setup/", response_class=HTMLResponse)
def setup_page(request: Request) -> Response:
    if not settings.local_auth_enabled:
        return RedirectResponse("/ui/home/", status_code=302)
    state = setup_service.setup_state()
    if state == "needs_owner":
        return _render_needs_owner(request)
    if state == "guided_ramp":
        return _render_guided_ramp(request)
    return RedirectResponse("/ui/home/", status_code=302)


@router.post("/ui/setup/registration")
async def setup_set_registration(request: Request, open: str = Form("0")) -> Response:
    _assert_same_origin(request)
    base = _base(request)
    user = resolve_ui_user(request)
    if user is None or not user.is_admin:
        return RedirectResponse(
            f"{base}/ui/setup/?error={quote('admin required')}",
            status_code=303,
        )
    want_open = str(open).strip() in {"1", "true", "yes", "on"}
    setup_service.set_registration_open(want_open)
    msg = "registration opened" if want_open else "registration closed"
    # Stay on checklist so admin can click Finish (do not auto-leave).
    return RedirectResponse(f"{base}/ui/setup/?ok={quote(msg)}", status_code=303)


@router.post("/ui/setup/registration-ack")
async def setup_ack_registration(request: Request) -> Response:
    _assert_same_origin(request)
    base = _base(request)
    user = resolve_ui_user(request)
    if user is None or not user.is_admin:
        return RedirectResponse(
            f"{base}/ui/setup/?error={quote('admin required')}",
            status_code=303,
        )
    setup_service.ack_registration_keep_open()
    return RedirectResponse(
        f"{base}/ui/setup/?ok={quote('kept registration open')}",
        status_code=303,
    )


@router.post("/ui/setup/complete")
async def setup_complete(request: Request) -> Response:
    _assert_same_origin(request)
    base = _base(request)
    user = resolve_ui_user(request)
    if user is None or not user.is_admin:
        return RedirectResponse(
            f"{base}/ui/setup/?error={quote('admin required')}",
            status_code=303,
        )
    status = setup_service.checklist_status()
    if not status["checklist_ready"]:
        return RedirectResponse(
            f"{base}/ui/setup/?error={quote('checklist incomplete')}",
            status_code=303,
        )
    setup_service.mark_setup_complete()
    return RedirectResponse(f"{base}/ui/home/", status_code=303)


def render_setup_banner(request: Request, *, locale: str) -> str:
    """Banner for home / me when guided ramp is active."""
    if not setup_service.setup_in_progress():
        return ""
    base = _base(request)
    user = resolve_ui_user(request)
    if user is None:
        msg = tr(locale, "setup.banner_login")
        login = tr(locale, "auth.local.login_link")
        open_label = tr(locale, "setup.banner_open")
        return (
            f'<div class="alert info" style="margin-bottom:16px;">{esc(msg)} '
            f'<a href="{esc(base)}/auth/login?next={esc(base)}/ui/setup/">{esc(login)}</a>'
            f' · <a href="{esc(base)}/ui/setup/">{esc(open_label)}</a></div>'
        )
    if user.is_admin:
        msg = tr(locale, "setup.banner_admin")
        open_label = tr(locale, "setup.banner_open")
        return (
            f'<div class="alert info" style="margin-bottom:16px;">{esc(msg)} '
            f'<a href="{esc(base)}/ui/setup/">{esc(open_label)}</a></div>'
        )
    return ""
