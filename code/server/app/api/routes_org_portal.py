"""Org and library admin portal routes (design/24)."""
from __future__ import annotations

import math
from urllib.parse import quote, urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.api.routes_portal import _assert_same_origin, _base, _require_user
from app.api.ui_i18n import html_response, ui_locale
from app.api.ui_session import ui_user_line
from app.api.ui_theme import (
    badge,
    esc,
    render_breadcrumb,
    render_list_footer,
    render_page,
    render_stat_cards,
    render_storage_meter,
    render_table,
)
from app.core.config import settings
from app.services.entitlement_service import can_read_library
from app.services.library_admin_service import (
    add_library_grant,
    assert_library_maintainer,
    create_org_library,
    remove_library_grant,
)
from app.services.onboarding_service import ensure_personal_org, personal_org_id
from app.services.org_invite_service import create_org_invite
from app.services.org_quota_service import team_org_creation_summary
from app.services.org_service import (
    DEFAULT_TEAM_LIBRARY_VISIBILITY,
    add_org_member,
    assert_org_admin,
    create_team_org,
    org_card_label,
    org_plan_label,
    remove_org_member,
    search_members_by_display_name,
)
from app.services.storage_quota_service import (
    format_storage_bytes,
    personal_library_quota_summary,
)
from app.storage import db

router = APIRouter(tags=["portal-orgs"])

_DEFAULT_PER_PAGE = 50
_RECORD_STATUS_FILTERS = frozenset({"all", "active", "buffered", "draft", "invalid", "trashed"})


def _problem_summary(problem: str | None, *, max_len: int = 80) -> str:
    text = " ".join(str(problem or "").split())
    if len(text) <= max_len:
        return text or "—"
    return text[: max_len - 1] + "…"


def _org_role_badge(role: str, *, locale: str, t) -> str:
    if role == "admin":
        label = t("portal.orgs.role.admin")
        return badge(label, "primary")
    return badge(t("portal.orgs.role.member"), "muted")


@router.get("/ui/orgs/", response_class=HTMLResponse)
def portal_orgs_list(request: Request) -> Response:
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    locale, t = ui_locale(request)
    base = _base(request)
    ensure_personal_org(user.principal_id, user.display_name)
    orgs = db.list_orgs_for_principal(user.principal_id)
    orgs.sort(key=lambda o: (0 if str(o.get("kind") or "") == "personal" else 1, str(o.get("name") or "")))
    cards: list[str] = []
    for org in orgs:
        org_id = str(org["id"])
        kind = str(org.get("kind") or "custom")
        title = org_card_label(org, locale=locale)
        libs = db.list_org_libraries(org_id)
        members = db.count_active_org_members(org_id)
        role_badge = _org_role_badge(str(org.get("role") or "member"), locale=locale, t=t)
        subtitle = t("portal.orgs.card.libraries_members", libraries=len(libs), members=members)
        cards.append(
            f"""
  <div class="card" style="margin-bottom:16px;">
    <div class="card-header"><h2>{esc(title)} {role_badge}</h2></div>
    <div class="card-body">
      <p class="card-muted">{esc(subtitle)}</p>
      <p><a class="btn" href="{esc(base)}/ui/orgs/{esc(org_id)}/">{esc(t("portal.orgs.enter"))}</a></p>
    </div>
  </div>"""
        )
    if not cards:
        cards.append(f'<div class="empty"><div>{esc(t("portal.orgs.empty"))}</div></div>')
    create_cta = f"""
  <div style="margin-bottom:16px;">
    <a class="btn primary" href="{esc(base)}/ui/orgs/new/">{esc(t("portal.orgs.create_team"))}</a>
  </div>"""
    body = create_cta + "".join(cards)
    return html_response(
        request,
        render_page(
            title=t("portal.orgs.title"),
            base=base,
            active_nav="orgs",
            subtitle=t("portal.orgs.subtitle"),
            user_line=ui_user_line(user),
            show_logout=True,
            is_admin=user.is_admin,
            body=body,
            locale=locale,
            request=request,
        ),
    )


@router.get("/ui/orgs/new/", response_class=HTMLResponse)
def portal_orgs_new(request: Request, error: str = Query("")) -> Response:
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    locale, t = ui_locale(request)
    base = _base(request)
    ensure_personal_org(user.principal_id, user.display_name)
    summary = team_org_creation_summary(user.principal_id, is_product_admin=user.is_admin)
    alert = f'<div class="alert error">{esc(error)}</div>' if error else ""
    if summary["allowed"]:
        body = f"""
  {alert}
  <div class="card">
    <div class="card-header"><h2>{esc(t("portal.orgs.create_team"))}</h2></div>
    <div class="card-body">
      <p class="card-muted">{esc(t("portal.orgs.create_team_help"))}</p>
      <form method="post" action="{esc(base)}/ui/orgs/new/">
        <label>{esc(t("portal.orgs.create_team_name"))}<br>
          <input name="name" type="text" required maxlength="80" autofocus
                 style="width:100%;max-width:420px;" placeholder="{esc(t("portal.orgs.create_team_name_placeholder"))}">
        </label>
        <p class="card-muted" style="margin-top:8px;">{esc(t("portal.orgs.create_team_plan_note", plan=summary["plan_code"]))}</p>
        <button type="submit" class="btn primary" style="margin-top:12px;">{esc(t("portal.orgs.create_team_submit"))}</button>
      </form>
    </div>
  </div>
  <p style="margin-top:12px;"><a class="btn" href="{esc(base)}/ui/orgs/">{esc(t("common.back"))}</a></p>"""
    else:
        personal_settings = f"{base}/ui/orgs/{personal_org_id(user.principal_id)}/settings/"
        if summary.get("reason") == "upgrade_required":
            headline = t("portal.orgs.create_team_upgrade_title")
            detail = t("portal.orgs.create_team_upgrade_body")
        else:
            headline = t("portal.orgs.create_team_limit_title")
            detail = t(
                "portal.orgs.create_team_limit_body",
                owned=summary["owned"],
                limit=summary["limit"],
            )
        body = f"""
  {alert}
  <div class="card">
    <div class="card-header"><h2>{esc(headline)}</h2></div>
    <div class="card-body">
      <p>{esc(detail)}</p>
      <div class="actions" style="margin-top:16px;">
        <a class="btn primary" href="{esc(personal_settings)}">{esc(t("portal.orgs.create_team_upgrade_cta"))}</a>
        <a class="btn" href="{esc(base)}/ui/orgs/">{esc(t("common.back"))}</a>
      </div>
    </div>
  </div>"""
    breadcrumb = render_breadcrumb([(t("portal.orgs.title"), f"{base}/ui/orgs/"), (t("portal.orgs.create_team"), None)])
    return html_response(
        request,
        render_page(
            title=t("portal.orgs.create_team"),
            base=base,
            active_nav="orgs",
            subtitle=t("portal.orgs.create_team_subtitle"),
            user_line=ui_user_line(user),
            show_logout=True,
            is_admin=user.is_admin,
            breadcrumb_html=breadcrumb,
            body=body,
            locale=locale,
            request=request,
        ),
    )


@router.post("/ui/orgs/new/")
async def portal_orgs_new_save(request: Request) -> Response:
    _assert_same_origin(request)
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    base = _base(request)
    form = await request.form()
    name = str(form.get("name") or "")
    try:
        org = create_team_org(
            name=name,
            owner_principal_id=user.principal_id,
            is_product_admin=user.is_admin,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        msg = str(detail.get("message") or detail.get("error") or exc.detail)
        if detail.get("error") == "team_org_upgrade_required":
            return RedirectResponse(f"{base}/ui/orgs/new/?error={quote(msg)}", status_code=303)
        return RedirectResponse(
            f"{base}/ui/orgs/new/?error={quote(msg)}",
            status_code=303,
        )
    return RedirectResponse(f"{base}/ui/orgs/{org['id']}/", status_code=303)


@router.get("/ui/orgs/{org_id}/", response_class=HTMLResponse)
def portal_org_detail(request: Request, org_id: str) -> Response:
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    locale, t = ui_locale(request)
    base = _base(request)
    org = db.get_organization(org_id)
    member = db.get_org_member(org_id, user.principal_id)
    if not org or not member or member.get("seat_status") != "active":
        raise HTTPException(status_code=404, detail="organization not found")
    is_admin = member.get("role") == "admin"
    libs = db.list_org_libraries(org_id)
    members_count = db.count_active_org_members(org_id)
    used_bytes = db.sum_org_storage_bytes(org_id)
    lib_rows = []
    for lib in libs:
        stats = db.get_library_stats(str(lib["library_id"])) or {}
        rec = stats.get("records") or {}
        active = (rec.get("by_status") or {}).get("active", 0)
        lib_rows.append(
            [
                f'<a class="key-link" href="{esc(base)}/ui/libraries/{esc(lib["library_id"])}/">{esc(lib["name"])}</a>',
                badge(str(lib.get("visibility") or ""), "muted"),
                esc(active),
            ]
        )
    admin_actions = ""
    if is_admin:
        admin_actions = f"""
  <div class="actions" style="margin:16px 0;">
    <a class="btn" href="{esc(base)}/ui/orgs/{esc(org_id)}/members/">{esc(t("portal.orgs.members"))}</a>
    <a class="btn" href="{esc(base)}/ui/orgs/{esc(org_id)}/settings/">{esc(t("portal.orgs.settings"))}</a>
  </div>
  <div class="card" style="margin-bottom:16px;">
    <div class="card-header"><h2>{esc(t("portal.orgs.create_library"))}</h2></div>
    <div class="card-body">
      <form method="post" action="{esc(base)}/ui/orgs/{esc(org_id)}/libraries/">
        <label>{esc(t("portal.orgs.library_name"))}<br>
          <input name="name" type="text" required maxlength="120" style="width:100%;max-width:420px;">
        </label>
        <p style="margin-top:12px;">
          <label>{esc(t("portal.orgs.library_visibility"))}<br>
            <select name="visibility">
              <option value="private" selected>{esc(t("portal.orgs.visibility.private"))}</option>
              <option value="org">{esc(t("portal.orgs.visibility.org"))}</option>
            </select>
          </label>
        </p>
        <p class="card-muted">{esc(t("portal.orgs.visibility.private_help"))}</p>
        <p><label><input type="checkbox" name="confirm_org_visibility" value="1">
          {esc(t("portal.orgs.visibility.org_confirm"))}</label></p>
        <button type="submit" class="btn primary">{esc(t("portal.orgs.create_library"))}</button>
      </form>
    </div>
  </div>"""
    stats = render_stat_cards(
        [
            (t("portal.orgs.stats.members"), members_count),
            (t("portal.orgs.stats.libraries"), len(libs)),
            (
                t("portal.orgs.stats.storage"),
                format_storage_bytes(used_bytes),
            ),
        ]
    )
    breadcrumb = render_breadcrumb(
        [(t("portal.orgs.title"), f"{base}/ui/orgs/"), (str(org.get("name") or org_id), None)]
    )
    body = f"""
  {stats}
  {admin_actions}
  <div class="card">
    <div class="card-header"><h2>{esc(t("portal.orgs.libraries"))}</h2></div>
    <div class="card-body" style="padding:0;">
      {render_table([t("portal.orgs.table.library"), t("portal.orgs.table.visibility"), "Active"], lib_rows, empty=t("portal.orgs.libraries_empty"))}
    </div>
  </div>
  <p class="card-muted" style="margin-top:12px;">{esc(t("portal.orgs.storage_preview_hint"))}</p>"""
    return html_response(
        request,
        render_page(
            title=str(org.get("name") or org_id),
            base=base,
            active_nav="orgs",
            subtitle=t("portal.orgs.detail_subtitle"),
            user_line=ui_user_line(user),
            show_logout=True,
            is_admin=user.is_admin,
            breadcrumb_html=breadcrumb,
            body=body,
            locale=locale,
            request=request,
        ),
    )


@router.post("/ui/orgs/{org_id}/libraries/")
async def portal_org_create_library(request: Request, org_id: str) -> Response:
    _assert_same_origin(request)
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    base = _base(request)
    form = await request.form()
    name = str(form.get("name") or "")
    visibility = str(form.get("visibility") or DEFAULT_TEAM_LIBRARY_VISIBILITY)
    confirm = str(form.get("confirm_org_visibility") or "") in {"1", "on", "true", "yes"}
    try:
        lib = create_org_library(
            org_id=org_id,
            actor_principal_id=user.principal_id,
            name=name,
            visibility=visibility,  # type: ignore[arg-type]
            confirm_org_visibility=confirm or visibility == "private",
        )
    except HTTPException as exc:
        q = urlencode({"error": str(exc.detail)})
        return RedirectResponse(f"{base}/ui/orgs/{org_id}/?{q}", status_code=303)
    return RedirectResponse(f"{base}/ui/libraries/{lib['library_id']}/", status_code=303)


@router.get("/ui/orgs/{org_id}/members/", response_class=HTMLResponse)
def portal_org_members(
    request: Request,
    org_id: str,
    q: str = Query(""),
    error: str = Query(""),
    invite_url: str = Query(""),
) -> Response:
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    locale, t = ui_locale(request)
    base = _base(request)
    try:
        assert_org_admin(org_id, user.principal_id)
    except HTTPException:
        raise HTTPException(status_code=404, detail="organization not found") from None
    org = db.get_organization(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="organization not found")
    members = db.list_org_members(org_id)
    search_hits = search_members_by_display_name(q, limit=10) if q.strip() else []
    rows = []
    sole_admin = db.count_active_org_admins(org_id) <= 1
    for m in members:
        pid = str(m["principal_id"])
        is_last_admin = sole_admin and m.get("role") == "admin" and m.get("seat_status") == "active"
        remove_btn = ""
        if m.get("seat_status") == "active" and not is_last_admin:
            remove_btn = (
                f'<form method="post" action="{esc(base)}/ui/orgs/{esc(org_id)}/members/remove/" '
                f'onsubmit="return confirm({json_escape(t("portal.orgs.members.remove_confirm"))});" style="display:inline;">'
                f'<input type="hidden" name="principal_id" value="{esc(pid)}">'
                f'<button type="submit" class="btn">{esc(t("portal.orgs.members.remove"))}</button></form>'
            )
        elif is_last_admin:
            remove_btn = f'<span class="card-muted">{esc(t("portal.orgs.members.last_admin"))}</span>'
        rows.append(
            [
                esc(m.get("alias") or "—"),
                esc(m.get("display_name") or pid),
                f'<code>{esc(pid)}</code>',
                _org_role_badge(str(m.get("role") or "member"), locale=locale, t=t),
                esc(m.get("joined_at") or ""),
                remove_btn,
            ]
        )
    search_options = ""
    for hit in search_hits:
        search_options += (
            f'<option value="{esc(hit["principal_id"])}">'
            f'{esc(hit.get("display_name") or hit["principal_id"])} ({esc(hit["principal_id"])})</option>'
        )
    alert = f'<div class="alert error">{esc(error)}</div>' if error else ""
    invite_flash = ""
    if invite_url:
        invite_flash = f"""
  <div class="alert success" style="margin-bottom:16px;">
    <p style="margin:0 0 8px;">{esc(t("portal.orgs.invites.created"))}</p>
    <div class="copy-row">
      <input class="copy-input" type="text" readonly value="{esc(invite_url)}" onclick="this.select();" style="width:100%;max-width:640px;" />
      <button type="button" class="btn primary" onclick="ma3CopyFrom(this)">{esc(t("common.copy"))}</button>
    </div>
  </div>"""

    from app.services.billing_service import seat_usage

    try:
        usage = seat_usage(org_id)
    except Exception:
        usage = {
            "used": db.count_active_org_members(org_id),
            "active_members": db.count_active_org_members(org_id),
            "pending_invite_uses": 0,
            "included_seats": 1 if str(org.get("kind") or "") == "personal" else 3,
        }
    seats_used = int(usage.get("used") or 0)
    seats_limit = int(usage.get("included_seats") or 1)
    seats_pending = int(usage.get("pending_invite_uses") or 0)
    seats_label = t("portal.orgs.members.seats", used=seats_used, limit=seats_limit)
    if seats_pending > 0:
        seats_label = f"{seats_label} {t('portal.orgs.members.seats_pending', pending=seats_pending)}"
    seats_banner = f"""
  <div class="card" style="margin-bottom:16px;" data-testid="org-seats-banner">
    <div class="card-body" style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;">
      <div>
        <strong data-testid="org-seats-used-limit">{esc(seats_label)}</strong>
      </div>
    </div>
  </div>"""
    org_kind = str(org.get("kind") or "")
    is_personal = org_kind == "personal"
    at_or_over_cap = seats_used >= seats_limit
    over_cap = seats_used > seats_limit

    if is_personal:
        manage_section = f"""
  <div class="alert info" style="margin-bottom:16px;" data-testid="org-personal-only">
    {esc(t("portal.orgs.members.personal_only"))}
  </div>"""
    else:
        cap_note = ""
        if over_cap:
            cap_note = (
                f'<div class="alert warning" style="margin-bottom:12px;" data-testid="org-seats-over">'
                f'{esc(t("portal.orgs.members.seats_over", used=seats_used, limit=seats_limit))}</div>'
            )
        elif at_or_over_cap:
            cap_note = (
                f'<div class="alert warning" style="margin-bottom:12px;" data-testid="org-seats-at-cap">'
                f'{esc(t("portal.orgs.members.seats_at_cap"))}</div>'
            )
        remaining = max(0, seats_limit - seats_used)
        max_uses_default = 0 if remaining <= 0 else 1
        max_uses_attr = f'min="1" max="{remaining}"' if remaining > 0 else 'min="0" max="0"'
        invite_disabled = " disabled" if remaining <= 0 else ""
        add_disabled = " disabled" if remaining <= 0 else ""
        invite_btn_class = "btn" if remaining <= 0 else "btn primary"
        add_btn_class = "btn" if remaining <= 0 else "btn primary"
        manage_section = f"""
  {cap_note}
  <div class="card" style="margin-bottom:16px;">
    <div class="card-header"><h2>{esc(t("portal.orgs.invites.title"))}</h2></div>
    <div class="card-body">
      <p class="card-muted">{esc(t("portal.orgs.invites.help"))}</p>
      <form method="post" action="{esc(base)}/ui/orgs/{esc(org_id)}/invites/">
        <p>
          <label>{esc(t("portal.orgs.invites.alias"))}<br>
            <input name="member_alias" type="text" maxlength="32" placeholder="{esc(t("portal.orgs.invites.alias_hint"))}" style="width:100%;max-width:320px;"{invite_disabled}>
          </label>
        </p>
        <p style="margin-top:8px;">
          <label>{esc(t("portal.orgs.members.role"))}
            <select name="role"{invite_disabled}><option value="member" selected>member</option><option value="admin">admin</option></select>
          </label>
        </p>
        <p style="margin-top:8px;">
          <label>{esc(t("portal.orgs.invites.max_uses"))}
            <input name="max_uses" type="number" {max_uses_attr} value="{max_uses_default}" style="width:80px;"{invite_disabled}>
          </label>
          <label style="margin-left:12px;">{esc(t("portal.orgs.invites.expires_hours"))}
            <input name="expires_in_hours" type="number" min="1" max="2160" value="168" style="width:100px;"{invite_disabled}>
          </label>
        </p>
        <button type="submit" class="{invite_btn_class}"{invite_disabled}>{esc(t("portal.orgs.invites.create"))}</button>
      </form>
    </div>
  </div>
  <div class="card" style="margin-bottom:16px;">
    <div class="card-header"><h2>{esc(t("portal.orgs.members.add"))}</h2></div>
    <div class="card-body">
      <p class="card-muted">{esc(t("portal.orgs.members.add_help"))}</p>
      <form method="get" action="{esc(base)}/ui/orgs/{esc(org_id)}/members/" style="margin-bottom:12px;">
        <input name="q" type="search" value="{esc(q)}" placeholder="{esc(t("portal.orgs.members.search_placeholder"))}" style="width:100%;max-width:420px;">
        <button type="submit" class="btn">{esc(t("portal.orgs.members.search"))}</button>
      </form>
      <form method="post" action="{esc(base)}/ui/orgs/{esc(org_id)}/members/">
        <label>{esc(t("portal.orgs.members.pick_user"))}<br>
          <select name="principal_id" required style="min-width:320px;"{add_disabled}>
            <option value="">{esc(t("portal.orgs.members.pick_placeholder"))}</option>
            {search_options}
          </select>
        </label>
        <p style="margin-top:8px;">
          <label>{esc(t("portal.orgs.members.or_principal"))}<br>
            <input name="principal_id_manual" type="text" placeholder="user:…" style="width:100%;max-width:420px;"{add_disabled}>
          </label>
        </p>
        <p style="margin-top:8px;">
          <label>{esc(t("portal.orgs.members.or_display_name"))}<br>
            <input name="display_name" type="text" style="width:100%;max-width:420px;"{add_disabled}>
          </label>
        </p>
        <p style="margin-top:8px;">
          <label>{esc(t("portal.orgs.members.alias"))}<br>
            <input name="alias" type="text" maxlength="32" placeholder="{esc(t("portal.orgs.invites.alias_hint"))}" style="width:100%;max-width:420px;"{add_disabled}>
          </label>
        </p>
        <p style="margin-top:8px;">
          <label>{esc(t("portal.orgs.members.role"))}
            <select name="role"{add_disabled}><option value="member">member</option><option value="admin">admin</option></select>
          </label>
        </p>
        <button type="submit" class="{add_btn_class}"{add_disabled}>{esc(t("portal.orgs.members.add"))}</button>
      </form>
    </div>
  </div>"""

    body = f"""
  {alert}
  {invite_flash}
  {seats_banner}
  {manage_section}
  <div class="card">
    <div class="card-body" style="padding:0;">
      {render_table(
          [t("portal.orgs.members.alias"), t("portal.orgs.members.display_name"), "Principal ID", t("portal.orgs.members.role"), t("common.created_at"), ""],
          rows,
          empty=t("portal.orgs.members.empty"),
      )}
    </div>
  </div>"""
    breadcrumb = render_breadcrumb(
        [
            (t("portal.orgs.title"), f"{base}/ui/orgs/"),
            (str(org.get("name") or org_id), f"{base}/ui/orgs/{org_id}/"),
            (t("portal.orgs.members"), None),
        ]
    )
    return html_response(
        request,
        render_page(
            title=t("portal.orgs.members"),
            base=base,
            active_nav="orgs",
            subtitle=str(org.get("name") or org_id),
            user_line=ui_user_line(user),
            show_logout=True,
            is_admin=user.is_admin,
            breadcrumb_html=breadcrumb,
            body=body,
            locale=locale,
            request=request,
        ),
    )


def json_escape(text: str) -> str:
    import json

    return json.dumps(text, ensure_ascii=False)


@router.post("/ui/orgs/{org_id}/invites/")
async def portal_org_invite_create(request: Request, org_id: str) -> Response:
    _assert_same_origin(request)
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    base = _base(request)
    form = await request.form()
    role = str(form.get("role") or "member")
    try:
        max_uses = int(form.get("max_uses") or 1)
        expires_in_hours = int(form.get("expires_in_hours") or 168)
        created = create_org_invite(
            org_id=org_id,
            actor_principal_id=user.principal_id,
            role=role,  # type: ignore[arg-type]
            max_uses=max_uses,
            expires_in_hours=expires_in_hours,
            base_url=base,
            member_alias=str(form.get("member_alias") or "").strip() or None,
        )
    except HTTPException as exc:
        if isinstance(exc.detail, dict):
            err = str(exc.detail.get("error") or "")
            if err == "seat_limit_exceeded":
                detail = (
                    f"seat_limit_exceeded "
                    f"(used={exc.detail.get('used')}, included_seats={exc.detail.get('included_seats')})"
                )
            else:
                detail = err or str(exc.detail)
        else:
            detail = str(exc.detail)
        return RedirectResponse(
            f"{base}/ui/orgs/{org_id}/members/?error={quote(detail)}",
            status_code=303,
        )
    except (TypeError, ValueError) as exc:
        return RedirectResponse(
            f"{base}/ui/orgs/{org_id}/members/?error={quote(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(
        f"{base}/ui/orgs/{org_id}/members/?invite_url={quote(str(created.get('invite_url') or ''), safe='')}",
        status_code=303,
    )


@router.post("/ui/orgs/{org_id}/members/")
async def portal_org_members_add(request: Request, org_id: str) -> Response:
    _assert_same_origin(request)
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    base = _base(request)
    form = await request.form()
    pid = str(form.get("principal_id") or form.get("principal_id_manual") or "").strip()
    display_name = str(form.get("display_name") or "").strip()
    role = str(form.get("role") or "member")
    alias = str(form.get("alias") or "").strip() or None
    try:
        add_org_member(
            org_id=org_id,
            actor_principal_id=user.principal_id,
            principal_id=pid or None,
            display_name=display_name or None,
            role=role,  # type: ignore[arg-type]
            alias=alias,
        )
    except HTTPException as exc:
        if isinstance(exc.detail, dict):
            err = str(exc.detail.get("error") or "")
            if err == "seat_limit_exceeded":
                detail = (
                    f"seat_limit_exceeded "
                    f"(used={exc.detail.get('used')}, included_seats={exc.detail.get('included_seats')})"
                )
            else:
                detail = err or str(exc.detail)
        else:
            detail = str(exc.detail)
        return RedirectResponse(
            f"{base}/ui/orgs/{org_id}/members/?error={quote(detail)}",
            status_code=303,
        )
    return RedirectResponse(f"{base}/ui/orgs/{org_id}/members/", status_code=303)


@router.post("/ui/orgs/{org_id}/members/remove/")
async def portal_org_members_remove(request: Request, org_id: str) -> Response:
    _assert_same_origin(request)
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    base = _base(request)
    form = await request.form()
    target = str(form.get("principal_id") or "").strip()
    try:
        remove_org_member(org_id=org_id, actor_principal_id=user.principal_id, target_principal_id=target)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        msg = detail.get("message") or detail.get("error") or str(detail)
        return RedirectResponse(
            f"{base}/ui/orgs/{org_id}/members/?error={quote(str(msg))}",
            status_code=303,
        )
    return RedirectResponse(f"{base}/ui/orgs/{org_id}/members/", status_code=303)


@router.get("/ui/orgs/{org_id}/settings/", response_class=HTMLResponse)
def portal_org_settings(request: Request, org_id: str) -> Response:
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    locale, t = ui_locale(request)
    base = _base(request)
    try:
        assert_org_admin(org_id, user.principal_id)
    except HTTPException:
        raise HTTPException(status_code=404, detail="organization not found") from None
    org = db.get_organization(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="organization not found")
    plan_label = org_plan_label(org, locale=locale)
    upgrade_block = ""
    if str(org.get("kind") or "") == "personal":
        creation = team_org_creation_summary(user.principal_id, is_product_admin=user.is_admin)
        if not creation["allowed"] and creation.get("reason") == "upgrade_required":
            upgrade_block = f"""
      <div class="alert info" style="margin-top:16px;">{esc(t("portal.orgs.settings.upgrade_for_team"))}</div>"""
    body = f"""
  <div class="card">
    <div class="card-body">
      <dl class="kv">
        <dt>{esc(t("portal.orgs.settings.name"))}</dt><dd>{esc(org.get("name") or "")}</dd>
        <dt>{esc(t("portal.orgs.settings.kind"))}</dt><dd>{esc(org.get("kind") or "")}</dd>
        <dt>{esc(t("portal.orgs.settings.plan"))}</dt><dd>{esc(plan_label)}</dd>
      </dl>
      {upgrade_block}
      <p class="card-muted">{esc(t("portal.orgs.settings.billing_hint"))}</p>
    </div>
  </div>"""
    breadcrumb = render_breadcrumb(
        [
            (t("portal.orgs.title"), f"{base}/ui/orgs/"),
            (str(org.get("name") or org_id), f"{base}/ui/orgs/{org_id}/"),
            (t("portal.orgs.settings"), None),
        ]
    )
    return html_response(
        request,
        render_page(
            title=t("portal.orgs.settings"),
            base=base,
            active_nav="orgs",
            subtitle=str(org.get("name") or org_id),
            user_line=ui_user_line(user),
            show_logout=True,
            is_admin=user.is_admin,
            breadcrumb_html=breadcrumb,
            body=body,
            locale=locale,
            request=request,
        ),
    )


@router.get("/ui/libraries/{library_id}/grants/", response_class=HTMLResponse)
def portal_library_grants(request: Request, library_id: str, error: str = Query("")) -> Response:
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    locale, t = ui_locale(request)
    base = _base(request)
    try:
        assert_library_maintainer(library_id, user.principal_id)
    except HTTPException:
        raise HTTPException(status_code=404, detail="library not found") from None
    lib = db.get_library(library_id)
    if not lib:
        raise HTTPException(status_code=404, detail="library not found")
    grants = db.list_library_grants(library_id)
    rows = []
    for g in grants:
        pid = str(g["principal_id"])
        rows.append(
            [
                esc(g.get("display_name") or pid),
                f'<code>{esc(pid)}</code>',
                badge(str(g.get("role") or ""), "muted"),
                esc(g.get("created_at") or ""),
                (
                    f'<form method="post" action="{esc(base)}/ui/libraries/{esc(library_id)}/grants/remove/" style="display:inline;">'
                    f'<input type="hidden" name="principal_id" value="{esc(pid)}">'
                    f'<button type="submit" class="btn">{esc(t("portal.library.grants.remove"))}</button></form>'
                ),
            ]
        )
    alert = f'<div class="alert error">{esc(error)}</div>' if error else ""
    body = f"""
  {alert}
  <div class="alert info">{esc(t("portal.library.grants.layer_hint"))}</div>
  <div class="card" style="margin-top:16px;">
    <div class="card-header"><h2>{esc(t("portal.library.grants.add"))}</h2></div>
    <div class="card-body">
      <form method="post" action="{esc(base)}/ui/libraries/{esc(library_id)}/grants/">
        <p><label>Principal ID<br><input name="principal_id" type="text" placeholder="user:…" style="width:100%;max-width:420px;"></label></p>
        <p><label>{esc(t("portal.orgs.members.or_display_name"))}<br><input name="display_name" type="text" style="width:100%;max-width:420px;"></label></p>
        <p><label>{esc(t("portal.library.grants.role"))}
          <select name="role"><option value="reader">reader</option><option value="writer">writer</option><option value="maintainer">maintainer</option></select>
        </label></p>
        <button type="submit" class="btn primary">{esc(t("portal.library.grants.add"))}</button>
      </form>
    </div>
  </div>
  <div class="card" style="margin-top:16px;">
    <div class="card-body" style="padding:0;">
      {render_table(["Display name", "Principal ID", t("portal.library.grants.role"), t("common.created_at"), ""], rows, empty=t("portal.library.grants.empty"))}
    </div>
  </div>
  <p style="margin-top:12px;"><a class="btn" href="{esc(base)}/ui/libraries/{esc(library_id)}/">{esc(t("common.back"))}</a></p>"""
    breadcrumb = render_breadcrumb(
        [
            (t("nav.libraries"), f"{base}/ui/libraries/"),
            (str(lib.get("name") or library_id), f"{base}/ui/libraries/{library_id}/"),
            (t("portal.library.grants.title"), None),
        ]
    )
    return html_response(
        request,
        render_page(
            title=t("portal.library.grants.title"),
            base=base,
            active_nav="libraries",
            subtitle=str(lib.get("name") or library_id),
            user_line=ui_user_line(user),
            show_logout=True,
            is_admin=user.is_admin,
            breadcrumb_html=breadcrumb,
            body=body,
            locale=locale,
            request=request,
        ),
    )


@router.post("/ui/libraries/{library_id}/grants/")
async def portal_library_grants_add(request: Request, library_id: str) -> Response:
    _assert_same_origin(request)
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    base = _base(request)
    form = await request.form()
    try:
        add_library_grant(
            library_id=library_id,
            actor_principal_id=user.principal_id,
            principal_id=str(form.get("principal_id") or "").strip() or None,
            display_name=str(form.get("display_name") or "").strip() or None,
            role=str(form.get("role") or "reader"),  # type: ignore[arg-type]
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return RedirectResponse(
            f"{base}/ui/libraries/{library_id}/grants/?error={quote(detail)}",
            status_code=303,
        )
    return RedirectResponse(f"{base}/ui/libraries/{library_id}/grants/", status_code=303)


@router.post("/ui/libraries/{library_id}/grants/remove/")
async def portal_library_grants_remove(request: Request, library_id: str) -> Response:
    _assert_same_origin(request)
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    base = _base(request)
    form = await request.form()
    remove_library_grant(
        library_id=library_id,
        actor_principal_id=user.principal_id,
        target_principal_id=str(form.get("principal_id") or "").strip(),
    )
    return RedirectResponse(f"{base}/ui/libraries/{library_id}/grants/", status_code=303)


@router.get("/ui/libraries/{library_id}/records/", response_class=HTMLResponse)
def portal_library_records(
    request: Request,
    library_id: str,
    page: int = Query(1, ge=1),
    status: str = Query("all"),
) -> Response:
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    locale, t = ui_locale(request)
    base = _base(request)
    try:
        assert_library_maintainer(library_id, user.principal_id)
    except HTTPException:
        raise HTTPException(status_code=404, detail="library not found") from None
    lib = db.get_library(library_id)
    if not lib:
        raise HTTPException(status_code=404, detail="library not found")
    st = status if status in _RECORD_STATUS_FILTERS else "all"
    per_page = _DEFAULT_PER_PAGE
    offset = (page - 1) * per_page
    records, total = db.list_records_for_library(
        library_id,
        status=None if st == "all" else st,
        limit=per_page,
        offset=offset,
    )
    rows = []
    for rec in records:
        rid = str(rec["id"])
        st_label = str(rec.get("status") or "")
        detail_href = ""
        if st_label == "buffered" and not db.is_record_owner(rid, user.principal_id):
            problem_cell = esc(t("portal.library.records.buffered_hidden"))
            outcome_cell = "—"
        else:
            problem_cell = esc(_problem_summary(rec.get("problem")))
            outcome_cell = esc(rec.get("outcome") or "")
            detail_href = f'<a class="key-link" href="{esc(base)}/ui/records/{esc(rid)}/">{esc(t("portal.library.records.detail"))}</a>'
        rows.append(
            [
                esc(rec.get("created_at") or ""),
                problem_cell,
                badge(st_label, "muted"),
                outcome_cell,
                detail_href,
            ]
        )
    total_pages = max(1, math.ceil(total / per_page))
    footer = render_list_footer(
        base_path=f"{base}/ui/libraries/{library_id}/records/",
        page=page,
        total_pages=total_pages,
        total_items=total,
        per_page=per_page,
        query={"status": st} if st != "all" else {},
        locale=locale,
    )
    body = f"""
  <div class="card">
    <div class="card-body" style="padding:0;">
      {render_table([t("portal.writes.table.time"), t("portal.writes.table.problem"), "Status", "Outcome", ""], rows, empty=t("portal.library.records.empty"))}
    </div>
  </div>
  {footer}
  <p style="margin-top:12px;"><a class="btn" href="{esc(base)}/ui/libraries/{esc(library_id)}/">{esc(t("common.back"))}</a></p>"""
    breadcrumb = render_breadcrumb(
        [
            (t("nav.libraries"), f"{base}/ui/libraries/"),
            (str(lib.get("name") or library_id), f"{base}/ui/libraries/{library_id}/"),
            (t("portal.library.records.title"), None),
        ]
    )
    return html_response(
        request,
        render_page(
            title=t("portal.library.records.title"),
            base=base,
            active_nav="libraries",
            subtitle=str(lib.get("name") or library_id),
            user_line=ui_user_line(user),
            show_logout=True,
            is_admin=user.is_admin,
            breadcrumb_html=breadcrumb,
            body=body,
            locale=locale,
            request=request,
        ),
    )


@router.get("/ui/libraries/{library_id}/storage/", response_class=HTMLResponse)
def portal_library_storage(request: Request, library_id: str) -> Response:
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    locale, t = ui_locale(request)
    base = _base(request)
    if not can_read_library(user.principal_id, library_id):
        raise HTTPException(status_code=404, detail="library not found")
    lib = db.get_library(library_id)
    if not lib:
        raise HTTPException(status_code=404, detail="library not found")
    used = db.sum_library_record_content_bytes(library_id)
    record_count = db.count_records_for_library(library_id)
    quota = personal_library_quota_summary(principal_id=user.principal_id, library_id=library_id)
    meter = ""
    tier_block = ""
    if quota:
        label = t(
            "portal.library.storage.used",
            used=format_storage_bytes(quota["used_bytes"]),
            limit=format_storage_bytes(quota["limit_bytes"]),
        )
        meter = render_storage_meter(
            used_bytes=int(quota["used_bytes"]),
            limit_bytes=int(quota["limit_bytes"]),
            label=label,
        )
        tier_block = f"""
      <dl class="kv">
        <dt>{esc(t("portal.library.storage.tier"))}</dt><dd>{esc(quota.get("tier") or "")}</dd>
        <dt>{esc(t("portal.library.storage.record_limit"))}</dt><dd>{esc(format_storage_bytes(settings.max_record_bytes))}</dd>
      </dl>"""
    else:
        meter = render_storage_meter(
            used_bytes=used,
            limit_bytes=None,
            label=t("portal.library.storage.org_preview", used=format_storage_bytes(used)),
        )
        tier_block = f'<p class="card-muted">{esc(t("portal.library.storage.org_billing_hint"))}</p>'
    body = f"""
  <div class="card">
    <div class="card-header"><h2>{esc(t("portal.library.storage.title"))}</h2></div>
    <div class="card-body">
      {meter}
      <dl class="kv" style="margin-top:16px;">
        <dt>{esc(t("portal.library.storage.records"))}</dt><dd>{esc(record_count)}</dd>
        <dt>{esc(t("portal.library.storage.bytes"))}</dt><dd>{esc(format_storage_bytes(used))}</dd>
      </dl>
      {tier_block}
    </div>
  </div>
  <p style="margin-top:12px;"><a class="btn" href="{esc(base)}/ui/libraries/{esc(library_id)}/">{esc(t("common.back"))}</a></p>"""
    breadcrumb = render_breadcrumb(
        [
            (t("nav.libraries"), f"{base}/ui/libraries/"),
            (str(lib.get("name") or library_id), f"{base}/ui/libraries/{library_id}/"),
            (t("portal.library.storage.title"), None),
        ]
    )
    return html_response(
        request,
        render_page(
            title=t("portal.library.storage.title"),
            base=base,
            active_nav="libraries",
            subtitle=str(lib.get("name") or library_id),
            user_line=ui_user_line(user),
            show_logout=True,
            is_admin=user.is_admin,
            breadcrumb_html=breadcrumb,
            body=body,
            locale=locale,
            request=request,
        ),
    )
