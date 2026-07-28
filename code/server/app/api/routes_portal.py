from __future__ import annotations

import math
from typing import Any, Callable
from urllib.parse import quote, unquote, urlencode, urlparse

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.core.security import assert_same_origin as _assert_same_origin
from app.api.ui_session import (
    login_redirect,
    require_authed_ui_user,
    resolve_ui_user,
    ui_user_line,
)
from app.api.ui_i18n import html_response, tr, ui_locale
from app.api.ui_theme import (
    badge,
    esc,
    render_breadcrumb,
    render_list_footer,
    render_page,
    render_pagination,
    render_sort_link,
    render_stat_cards,
    render_storage_meter,
    render_subnav,
    render_table,
)
from app.api.routes_setup import render_setup_banner
from app.services import setup_service
from app.auth.session import SessionUser
from app.core.config import settings
from app.services.feedback_service import apply_record_feedback, resolve_ui_feedback_principal
from app.services.buffer_service import can_read_record, is_library_settings_editor
from app.services.onboarding_service import ensure_personal_library, ensure_personal_org
from app.services.entitlement_service import can_maintain_library
from app.services.portal_service import can_read_library, entitled_library_ids, list_entitled_libraries
from app.services.storage_quota_service import format_storage_bytes, personal_library_quota_summary
from app.services.principal_service import complete_display_name_setup, display_name_setup_required
from app.services.record_read_service import format_record_for_read
from app.storage import db

router = APIRouter(tags=["portal"])

_DEFAULT_PER_PAGE = 50
_ALLOWED_PER_PAGE = (10, 25, 50, 100)
_WRITES_SORT_COLUMNS = frozenset({"created_at", "record_status", "library_name", "report_kind"})
_VOTES_SORT_COLUMNS = frozenset({"updated_at", "vote", "library_name"})
_WRITES_STATUS_FILTERS = frozenset({"all", "active", "buffered", "deleted"})
_VOTES_FILTERS = frozenset({"all", "up", "down"})


def _personal_library_label(display_name: str, *, locale: str) -> str:
    if locale == "en-US":
        return f"{display_name}'s personal library"
    return f"{display_name} 的个人库"


def _normalize_per_page(per_page: int) -> int:
    return per_page if per_page in _ALLOWED_PER_PAGE else _DEFAULT_PER_PAGE


def _page_offset(page: int, per_page: int) -> tuple[int, int]:
    page = max(1, page)
    return page, (page - 1) * per_page


def _writes_list_query(
    *,
    page: int,
    per_page: int,
    sort: str,
    dir: str,
    status: str,
) -> dict[str, str]:
    q: dict[str, str] = {}
    if page > 1:
        q["page"] = str(page)
    if per_page != _DEFAULT_PER_PAGE:
        q["per_page"] = str(per_page)
    if sort != "created_at":
        q["sort"] = sort
    if dir != "desc":
        q["dir"] = dir
    if status != "all":
        q["status"] = status
    return q


def _writes_list_redirect(base: str, *, list_query: dict[str, str], error: str | None = None) -> RedirectResponse:
    q = dict(list_query)
    if error:
        q["error"] = error
    suffix = f"?{urlencode(q)}" if q else ""
    return RedirectResponse(f"{base}/ui/me/writes/{suffix}", status_code=303)


_WRITES_BATCH_JS = """
<script>
(function () {
  var form = document.getElementById('writes-batch-form');
  var master = document.getElementById('writes-select-all');
  if (master) {
    master.addEventListener('change', function () {
      document.querySelectorAll('input[name="record_ids"][form="writes-batch-form"]').forEach(function (cb) {
        cb.checked = master.checked;
      });
    });
    document.querySelectorAll('input[name="record_ids"][form="writes-batch-form"]').forEach(function (cb) {
      cb.addEventListener('change', function () {
        var boxes = document.querySelectorAll('input[name="record_ids"][form="writes-batch-form"]');
        var checked = document.querySelectorAll('input[name="record_ids"][form="writes-batch-form"]:checked');
        master.checked = boxes.length > 0 && checked.length === boxes.length;
        master.indeterminate = checked.length > 0 && checked.length < boxes.length;
      });
    });
  }
  if (form) {
    form.addEventListener('submit', function (e) {
      var checked = document.querySelectorAll('input[name="record_ids"][form="writes-batch-form"]:checked');
      if (!checked.length) {
        e.preventDefault();
        var err = document.getElementById('writes-batch-error');
        if (err) err.style.display = 'block';
      }
    });
  }
})();
</script>
"""


def _votes_list_query(
    *,
    page: int,
    per_page: int,
    sort: str,
    dir: str,
    vote: str,
) -> dict[str, str]:
    q: dict[str, str] = {}
    if page > 1:
        q["page"] = str(page)
    if per_page != _DEFAULT_PER_PAGE:
        q["per_page"] = str(per_page)
    if sort != "updated_at":
        q["sort"] = sort
    if dir != "desc":
        q["dir"] = dir
    if vote != "all":
        q["vote"] = vote
    return q


def _render_filter_pills(
    *,
    items: list[tuple[str, str, str | None]],
    base_path: str,
    query: dict[str, str],
    param: str,
) -> str:
    from urllib.parse import urlencode

    links: list[str] = []
    for key, label, value in items:
        params = dict(query)
        params.pop("page", None)
        if value is None:
            params.pop(param, None)
        else:
            params[param] = value
        qs = urlencode(params)
        href = f"{esc(base_path)}?{esc(qs)}" if qs else esc(base_path)
        active = query.get(param) == value or (value is None and param not in query)
        cls = "active" if active else ""
        links.append(f'<a class="{cls}" href="{href}">{esc(label)}</a>')
    return f'<div class="filter-pills">{"".join(links)}</div>'


def _publish_record_with_relations(record_id: str) -> None:
    record = db.get_record(record_id)
    if not record or record.get("status") != "buffered":
        raise HTTPException(status_code=404, detail="record not found")
    db.publish_buffered_record(record_id, record=record)
    db.apply_record_relations_from_payload(record_id, record.get("payload") or {})


def _delete_owned_record(record_id: str, *, principal_id: str) -> None:
    record = db.get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="record not found")
    if not db.is_record_owner(record_id, principal_id):
        raise HTTPException(status_code=404, detail="record not found")
    library_id = str(record["library_id"])
    protected, _ret = db.library_deletion_protection(library_id)
    if protected:
        db.soft_delete_record(record_id)
    else:
        db.hard_delete_record(record_id, deleted_by=principal_id)


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _page_params(page: int, per_page: int = _DEFAULT_PER_PAGE) -> tuple[int, int]:
    return _page_offset(page, per_page)


def _require_user(request: Request, *, require_setup: bool = True) -> SessionUser | Response:
    return require_authed_ui_user(request, require_setup=require_setup)


def _render_profile_header(user: SessionUser) -> str:
    """Avatar + display name only; account details live under /ui/me/settings/."""
    initial = (user.display_name or "?")[:1].upper()
    return f"""
  <div class="profile-header">
    <div class="profile-avatar">{esc(initial)}</div>
    <div class="profile-body">
      <h2 class="profile-name">{esc(user.display_name)}</h2>
    </div>
  </div>"""


def _render_principal_id_card(user: SessionUser, *, locale: str) -> str:
    return f"""
  <div class="card">
    <div class="card-header"><h2>{esc(tr(locale, "portal.settings.principal_title"))}</h2></div>
    <div class="card-body">
      <p class="card-muted">{esc(tr(locale, "portal.settings.principal_help"))}</p>
      <code class="mono id-block">{esc(user.principal_id)}</code>
    </div>
  </div>"""


def _problem_summary(problem: str | None, *, width: int = 60) -> str:
    text = (problem or "").strip()
    if len(text) <= width:
        return text
    return text[: width - 1] + "…"


def _landing_primary_href(base: str) -> str:
    if setup_service.setup_needs_owner():
        return f"{base}/ui/setup/"
    if settings.portal_auth_enabled:
        return f"{base}/auth/login?next={base}/ui/me/"
    if settings.bootstrap_selfhost:
        return f"{base}/mcp/info"
    return f"{base}/client/agent-onboarding.md"


def _render_public_landing(request: Request, *, locale: str, t: Callable[..., str]) -> str:
    from app.services import local_auth_service

    base = _base(request)
    lib_id = settings.default_library_id
    lib_stats = db.get_library_stats(lib_id) or {}
    rec = lib_stats.get("records") or {}
    by_status = rec.get("by_status") or {}
    primary_href = _landing_primary_href(base)
    reg_open = local_auth_service.is_registration_open() if settings.local_auth_enabled else True
    if setup_service.setup_needs_owner():
        primary_label = t("setup.admin_title")
    elif settings.local_auth_enabled and not reg_open:
        primary_label = t("landing.hero.cta_signin")
    elif settings.local_auth_enabled:
        primary_label = t("landing.hero.cta_primary")
    elif settings.portal_auth_enabled:
        primary_label = t("landing.hero.cta_primary")
    elif settings.bootstrap_selfhost:
        primary_label = t("landing.hero.cta_primary_bootstrap")
    else:
        primary_label = t("landing.hero.cta_primary_dev")
    library_href = f"{base}/ui/libraries/{lib_id}/"
    docs_href = f"{base}/client/agent-onboarding.md"
    instance = settings.instance_id or "local"
    version = settings.service_version

    setup_banner = render_setup_banner(request, locale=locale)

    dev_alert = ""
    if settings.local_auth_enabled:
        alert_key = "landing.local_auth_alert" if reg_open else "landing.local_auth_alert_closed"
        dev_alert = f'<div class="alert info">{esc(t(alert_key))}</div>'
    elif not settings.authing_configured:
        alert_key = "landing.bootstrap_alert" if settings.bootstrap_selfhost else "landing.dev_alert"
        dev_alert = f'<div class="alert info">{esc(t(alert_key))}</div>'

    workflow_steps = "".join(
        f'<li><span class="landing-flow-step">{i}</span>'
        f'<span class="landing-flow-text">{esc(t(f"landing.workflow.s{i}"))}</span></li>'
        for i in range(1, 6)
    )
    feature_cards = "".join(
        f'<div class="card landing-feature-card"><div class="card-body">'
        f'<h3>{esc(t(f"landing.features.f{i}_title"))}</h3>'
        f'<p>{esc(t(f"landing.features.f{i}_body"))}</p></div></div>'
        for i in range(1, 4)
    )
    if settings.local_auth_enabled:
        if setup_service.setup_needs_owner():
            prefix = "landing.getstarted.local"
        elif not reg_open or setup_service.setup_complete():
            prefix = "landing.getstarted.local_ready"
        else:
            prefix = "landing.getstarted.local_ramp"
        getstarted_steps = (
            f"<li>{esc(t(f'{prefix}.s1'))}</li>"
            f"<li>{esc(t(f'{prefix}.s2'))}</li>"
            f"<li>{esc(t(f'{prefix}.s3'))}</li>"
            f"<li>{esc(t(f'{prefix}.s4'))}</li>"
        )
    else:
        getstarted_step3 = (
            f'{esc(t("landing.getstarted.s3_prefix"))}'
            f'<a href="{esc(docs_href)}">{esc(t("landing.getstarted.s3_link"))}</a>'
            f'{esc(t("landing.getstarted.s3_suffix"))}'
        )
        getstarted_steps = (
            f"<li>{esc(t('landing.getstarted.s1'))}</li>"
            f"<li>{esc(t('landing.getstarted.s2'))}</li>"
            f"<li>{getstarted_step3}</li>"
            f"<li>{esc(t('landing.getstarted.s4'))}</li>"
        )

    stat_cards = render_stat_cards(
        [
            (t("landing.status.cases"), lib_stats.get("cases", 0)),
            (t("landing.status.records"), rec.get("total", 0)),
            (t("landing.status.active"), by_status.get("active", 0)),
            (t("landing.status.version"), version),
        ]
    )
    status_meta = t(
        "landing.status.meta",
        instance=instance,
        running=t("landing.status.running"),
        version=version,
    )

    return f"""
  <div class="landing-hero">
    <h1 class="landing-hero-title">{esc(t("landing.hero.title"))}</h1>
    <p class="landing-hero-lead">{esc(t("landing.hero.subtitle"))}</p>
    <div class="landing-hero-actions">
      <a class="btn primary" href="{esc(primary_href)}">{esc(primary_label)}</a>
      <a class="btn" href="{library_href}">{esc(t("landing.hero.cta_library"))}</a>
      <a class="btn subtle" href="{esc(docs_href)}">{esc(t("landing.hero.cta_docs"))}</a>
    </div>
  </div>
  {setup_banner}
  {dev_alert}
  <section class="landing-section">
    <h2 class="landing-section-title">{esc(t("landing.problem.title"))}</h2>
    <ul class="landing-problem-list">
      <li>{esc(t("landing.problem.b1"))}</li>
      <li>{esc(t("landing.problem.b2"))}</li>
      <li>{esc(t("landing.problem.b3"))}</li>
    </ul>
  </section>
  <section class="landing-section">
    <h2 class="landing-section-title">{esc(t("landing.product.title"))}</h2>
    <div class="landing-compare-grid">
      <div class="card"><div class="card-body">
        <h3>{esc(t("landing.product.is_title"))}</h3>
        <ul>
          <li>{esc(t("landing.product.is_b1"))}</li>
          <li>{esc(t("landing.product.is_b2"))}</li>
          <li>{esc(t("landing.product.is_b3"))}</li>
        </ul>
      </div></div>
      <div class="card"><div class="card-body">
        <h3>{esc(t("landing.product.isnot_title"))}</h3>
        <ul>
          <li>{esc(t("landing.product.isnot_b1"))}</li>
          <li>{esc(t("landing.product.isnot_b2"))}</li>
          <li>{esc(t("landing.product.isnot_b3"))}</li>
        </ul>
      </div></div>
    </div>
  </section>
  <section class="landing-section">
    <h2 class="landing-section-title">{esc(t("landing.workflow.title"))}</h2>
    <ol class="landing-flow">{workflow_steps}</ol>
  </section>
  <section class="landing-section">
    <h2 class="landing-section-title">{esc(t("landing.features.title"))}</h2>
    <div class="landing-feature-grid">{feature_cards}</div>
  </section>
  <section class="landing-section landing-status">
    <h2 class="landing-section-title">{esc(t("landing.status.title"))}</h2>
    {stat_cards}
    <p class="landing-status-meta">{esc(status_meta)}</p>
    <p style="margin-top:12px;"><a class="btn subtle" href="{library_href}">{esc(t("landing.status.view_library"))}</a></p>
  </section>
  <section class="landing-section landing-getstarted">
    <h2 class="landing-section-title">{esc(t("landing.getstarted.title"))}</h2>
    <ol class="landing-numbered-steps">{getstarted_steps}</ol>
    <div class="landing-getstarted-cta">
      <a class="btn primary" href="{esc(primary_href)}">{esc(primary_label)}</a>
    </div>
  </section>"""


@router.get("/")
@router.get("/ui")
@router.get("/ui/")
def portal_root(request: Request) -> Response:
    if setup_service.setup_needs_owner():
        return RedirectResponse("/ui/setup/", status_code=302)
    user = resolve_ui_user(request)
    target = "/ui/me/" if user is not None else "/ui/home/"
    return RedirectResponse(target, status_code=302)


@router.get("/ui/home", response_class=HTMLResponse)
@router.get("/ui/home/", response_class=HTMLResponse)
def portal_home(request: Request) -> Response:
    # Day-0: keep marketing landing visible (primary CTA → /ui/setup/).
    if not setup_service.setup_needs_owner():
        user = resolve_ui_user(request)
        if user is not None:
            return RedirectResponse("/ui/me/", status_code=302)
    locale, t = ui_locale(request)
    base = _base(request)
    body = _render_public_landing(request, locale=locale, t=t)
    return html_response(
        request,
        render_page(
            title=t("landing.meta.title"),
            base=base,
            active_nav="",
            body=body,
            show_minimal_header=True,
            brand_href=f"{base}/ui/home/",
            meta_description=t("landing.meta.description"),
            locale=locale,
            request=request,
        ),
    )


@router.get("/ui/me", response_class=HTMLResponse)
@router.get("/ui/me/", response_class=HTMLResponse)
def portal_me(request: Request) -> Response:
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    locale, t = ui_locale(request)
    base = _base(request)
    ensure_personal_org(user.principal_id, user.display_name)
    db.publish_due_buffered_records()
    writes_count = db.count_write_audit_for_principal(user.principal_id)
    buffered_count = db.count_buffered_for_principal(user.principal_id)
    votes_count = db.count_feedback_for_principal(user.principal_id)
    libs = list_entitled_libraries(user.principal_id)
    orgs_count = len(db.list_orgs_for_principal(user.principal_id))
    keys_count = len(db.list_api_keys_for_principal(user.principal_id))
    recent = db.list_write_audit_for_principal(user.principal_id, limit=5, offset=0)

    lib_rows = []
    for lib in libs[:5]:
        name_cell = (
            f'<a class="key-link" href="{esc(base)}/ui/libraries/{esc(lib["library_id"])}/">'
            f'{esc(lib["name"])}</a>'
        )
        lib_rows.append(
            [
                name_cell,
                badge(lib["visibility"], "muted"),
                esc(lib["access"]),
                esc(lib["role"]),
            ]
        )

    list_items = []
    for row in recent:
        rid = row.get("record_id")
        if not rid or row.get("is_deleted"):
            list_items.append(
                '<div class="list-item">'
                f'<div class="list-item-title">{esc(_problem_summary(row.get("problem")))}</div>'
                f'<div class="list-item-meta">{esc(row.get("library_name") or "")} · {esc(t("portal.me.deleted_suffix"))}</div></div>'
            )
            continue
        status_label = row.get("record_status") or "active"
        if status_label == "buffered":
            meta_suffix = f" · {esc(t('status.buffered'))}"
        else:
            meta_suffix = f" · {esc(row.get('created_at') or '')}"
        list_items.append(
            f'<a class="list-item" href="{esc(base)}/ui/records/{esc(rid)}/">'
            f'<div class="list-item-title">{esc(_problem_summary(row.get("problem")))}</div>'
            f'<div class="list-item-meta">{esc(row.get("library_name") or "")}{meta_suffix}</div>'
            f"</a>"
        )
    recent_block = (
        f'<div class="list-group">{"".join(list_items)}</div>'
        if list_items
        else (
            '<div class="empty"><div class="empty-icon">⬡</div>'
            f"<div>{esc(t('portal.me.no_contributions'))}</div>"
            f'<div class="empty-cta"><a class="btn primary" href="{esc(base)}/ui/keys/">{esc(t("portal.me.create_key"))}</a> '
            f'<a class="btn" href="{esc(base)}/client/agent-onboarding.md">{esc(t("portal.me.onboarding_docs"))}</a></div></div>'
        )
    )

    body = f"""
  {render_setup_banner(request, locale=locale)}
  {_render_profile_header(user)}
  {render_subnav(base, active="overview", locale=locale)}
  {render_stat_cards([
      (t("portal.me.stats.records"), writes_count, f"{base}/ui/me/writes/"),
      (t("portal.me.stats.buffered"), buffered_count, f"{base}/ui/me/writes/?status=buffered"),
      (t("portal.me.stats.libraries"), len(libs), f"{base}/ui/libraries/"),
      (t("portal.me.stats.orgs"), orgs_count, f"{base}/ui/orgs/"),
      (t("portal.me.stats.votes"), votes_count, f"{base}/ui/me/votes/"),
      (t("portal.me.stats.keys"), keys_count, f"{base}/ui/keys/"),
  ])}
  <div class="card" style="margin-top:16px;">
    <div class="card-header">
      <h2>{esc(t("portal.me.my_libraries"))}</h2>
      <a class="btn subtle" href="{esc(base)}/ui/libraries/">{esc(t("portal.me.view_all"))}</a>
    </div>
    <div class="card-body" style="padding:0;">
      {render_table([t("portal.me.table.name"), t("portal.me.table.visibility"), t("portal.me.table.access"), t("portal.me.table.role")], lib_rows, empty=t("portal.me.empty_libraries"), locale=locale)}
    </div>
  </div>
  <div class="card" style="margin-top:16px;">
    <div class="card-header">
      <h2>{esc(t("portal.me.recent_contributions"))}</h2>
      <a class="btn subtle" href="{esc(base)}/ui/me/writes/">{esc(t("portal.me.view_all"))}</a>
    </div>
    <div class="card-body">{recent_block}</div>
  </div>"""
    return html_response(
        request,
        render_page(
            title=t("portal.me.title"),
            base=base,
            active_nav="me",
            subtitle=t("portal.me.subtitle"),
            user_line=ui_user_line(user),
            show_logout=True,
            is_admin=user.is_admin,
            body=body,
            locale=locale,
            request=request,
        ),
    )


@router.get("/ui/me/writes/", response_class=HTMLResponse)
def portal_writes(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(_DEFAULT_PER_PAGE, ge=1),
    sort: str = Query("created_at"),
    dir: str = Query("desc"),
    status: str = Query("all"),
) -> Response:
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    locale, t = ui_locale(request)
    base = _base(request)
    list_path = f"{base}/ui/me/writes/"
    per_page = _normalize_per_page(per_page)
    sort = sort if sort in _WRITES_SORT_COLUMNS else "created_at"
    dir = dir if dir in {"asc", "desc"} else "desc"
    status_key = status if status in _WRITES_STATUS_FILTERS else "all"
    status_filter = None if status_key == "all" else status_key
    page_num, offset = _page_offset(page, per_page)
    total = db.count_write_audit_for_principal(user.principal_id, status_filter=status_filter)
    total_pages = max(1, math.ceil(total / per_page)) if total else 1
    if page_num > total_pages:
        page_num = total_pages
        offset = (page_num - 1) * per_page
    query = _writes_list_query(page=page_num, per_page=per_page, sort=sort, dir=dir, status=status_key)
    error_msg = unquote(request.query_params.get("error") or "").strip()
    rows_data = db.list_write_audit_for_principal(
        user.principal_id,
        limit=per_page,
        offset=offset,
        status_filter=status_filter,
        sort_by=sort,
        sort_dir=dir,
    )
    table_rows = []
    for row in rows_data:
        rid = row.get("record_id")
        deleted = bool(row.get("is_deleted"))
        is_owner_buffered = (
            bool(rid)
            and not deleted
            and (row.get("record_status") or "active") == "buffered"
        )
        if is_owner_buffered:
            check_cell = f'<input type="checkbox" name="record_ids" value="{esc(rid)}" form="writes-batch-form"/>'
        else:
            check_cell = ""
        if deleted or not rid:
            rec_cell = f'<span class="card-muted">{esc(t("portal.writes.deleted_record"))}</span>'
        else:
            rec_cell = (
                f'<a class="key-link" href="{esc(base)}/ui/records/{esc(rid)}/">'
                f'{esc(_problem_summary(row.get("problem")))}</a>'
            )
        st = row.get("record_status") or "active"
        if deleted:
            st_cell = badge(t("status.deleted"), "muted")
        elif st == "buffered":
            st_cell = badge(t("status.buffered"), "muted")
        else:
            st_cell = badge(st, "success" if st == "active" else "muted")
        table_rows.append(
            [
                check_cell,
                esc(row.get("created_at") or ""),
                rec_cell,
                st_cell,
                esc(row.get("library_name") or ""),
                badge(str(row.get("report_kind") or "new"), "muted"),
                esc(row.get("key_prefix") or row.get("api_key_id") or "—"),
            ]
        )
    sort_q = dict(query)
    has_selectable = any(row[0] for row in table_rows)
    select_all_cell = (
        f'<input type="checkbox" id="writes-select-all" title="{esc(t("portal.writes.select_all_page"))}" aria-label="{esc(t("portal.writes.select_all_page"))}"/>'
        if has_selectable
        else ""
    )
    headers = [
        select_all_cell,
        render_sort_link(label=t("portal.writes.table.time"), column="created_at", current_sort=sort, current_dir=dir, base_path=list_path, query=sort_q),
        t("portal.writes.table.record"),
        render_sort_link(label=t("portal.writes.table.status"), column="record_status", current_sort=sort, current_dir=dir, base_path=list_path, query=sort_q),
        render_sort_link(label=t("portal.writes.table.library"), column="library_name", current_sort=sort, current_dir=dir, base_path=list_path, query=sort_q),
        render_sort_link(label=t("portal.writes.table.kind"), column="report_kind", current_sort=sort, current_dir=dir, base_path=list_path, query=sort_q),
        t("portal.writes.table.key"),
    ]
    filter_pills = _render_filter_pills(
        items=[
            ("all", t("portal.writes.filter.all"), None),
            ("active", t("portal.writes.filter.active"), "active"),
            ("buffered", t("portal.writes.filter.buffered"), "buffered"),
            ("deleted", t("portal.writes.filter.deleted"), "deleted"),
        ],
        base_path=list_path,
        query=query,
        param="status",
    )
    batch_bar = f"""
  <form id="writes-batch-form" method="post" action="{esc(base)}/ui/me/writes/batch/">
    <input type="hidden" name="status" value="{esc(status_key)}"/>
    <input type="hidden" name="sort" value="{esc(sort)}"/>
    <input type="hidden" name="dir" value="{esc(dir)}"/>
    <input type="hidden" name="page" value="{page_num}"/>
    <input type="hidden" name="per_page" value="{per_page}"/>
    <div id="writes-batch-error" class="alert warning" style="display:none;margin:0;border-radius:0;border-left:none;border-right:none;">
      {esc(t("portal.writes.select_required"))}
    </div>
    <div class="batch-bar">
      <span>{esc(t("portal.writes.batch_label"))}</span>
      <button type="submit" name="action" value="publish" class="btn primary">{esc(t("portal.writes.batch_publish"))}</button>
      <button type="submit" name="action" value="delete" class="btn danger">{esc(t("portal.writes.batch_delete"))}</button>
    </div>
  </form>"""
    alert_html = (
        f'<div class="alert warning" style="margin-bottom:12px;">{esc(error_msg)}</div>' if error_msg else ""
    )
    body = f"""
  {alert_html}
  {filter_pills}
  <div class="card">
    {batch_bar}
    <div class="card-body" style="padding:0;">
      {render_table(headers, table_rows, empty=t("portal.writes.empty"), locale=locale)}
    </div>
  </div>
  {render_list_footer(page=page_num, total_pages=total_pages, total_items=total, base_path=list_path, query=query, per_page=per_page, default_per_page=_DEFAULT_PER_PAGE, locale=locale)}
  {_WRITES_BATCH_JS}"""
    return html_response(
        request,
        render_page(
            title=t("portal.writes.title"),
            base=base,
            active_nav="records",
            subtitle=t("portal.writes.subtitle"),
            user_line=ui_user_line(user),
            show_logout=True,
            is_admin=user.is_admin,
            body=body,
            locale=locale,
            request=request,
        ),
    )


@router.post("/ui/me/writes/batch/")
async def portal_writes_batch(request: Request) -> Response:
    _assert_same_origin(request)
    user = resolve_ui_user(request)
    if user is None:
        return login_redirect(request)
    form = await request.form()
    action = str(form.get("action") or "").strip()
    record_ids = [str(rid).strip() for rid in form.getlist("record_ids") if str(rid).strip()]
    base = _base(request)
    list_query = _writes_list_query(
        page=int(form.get("page") or 1),
        per_page=int(form.get("per_page") or _DEFAULT_PER_PAGE),
        sort=str(form.get("sort") or "created_at"),
        dir=str(form.get("dir") or "desc"),
        status=str(form.get("status") or "all"),
    )
    if action not in {"publish", "delete"} or not record_ids:
        _, t = ui_locale(request)
        return _writes_list_redirect(base, list_query=list_query, error=t("portal.writes.select_required"))
    if action == "publish":
        db.publish_buffered_records_batch(record_ids, user.principal_id)
    else:
        db.delete_buffered_records_for_principal_batch(record_ids, user.principal_id)
    return _writes_list_redirect(base, list_query=list_query)


@router.get("/ui/me/votes/", response_class=HTMLResponse)
def portal_votes(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(_DEFAULT_PER_PAGE, ge=1),
    sort: str = Query("updated_at"),
    dir: str = Query("desc"),
    vote: str = Query("all"),
) -> Response:
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    locale, t = ui_locale(request)
    base = _base(request)
    list_path = f"{base}/ui/me/votes/"
    per_page = _normalize_per_page(per_page)
    sort = sort if sort in _VOTES_SORT_COLUMNS else "updated_at"
    dir = dir if dir in {"asc", "desc"} else "desc"
    vote_key = vote if vote in _VOTES_FILTERS else "all"
    vote_filter = None if vote_key == "all" else vote_key
    page_num, offset = _page_offset(page, per_page)
    total = db.count_feedback_for_principal(user.principal_id, vote_filter=vote_filter)
    total_pages = max(1, math.ceil(total / per_page)) if total else 1
    if page_num > total_pages:
        page_num = total_pages
        offset = (page_num - 1) * per_page
    query = _votes_list_query(page=page_num, per_page=per_page, sort=sort, dir=dir, vote=vote_key)
    rows_data = db.list_feedback_for_principal(
        user.principal_id,
        limit=per_page,
        offset=offset,
        vote_filter=vote_filter,
        sort_by=sort,
        sort_dir=dir,
    )
    table_rows = []
    for row in rows_data:
        rid = row.get("record_id")
        vote_icon = "👍" if int(row.get("vote") or 0) > 0 else "👎"
        deleted = bool(rid and db.get_record_deletion(str(rid)))
        if deleted or not rid or row.get("status") != "active":
            rec_cell = esc(_problem_summary(row.get("problem"))) + " " + badge(t("common.not_available"), "muted")
        else:
            rec_cell = (
                f'<a class="key-link" href="{esc(base)}/ui/records/{esc(rid)}/">'
                f'{esc(_problem_summary(row.get("problem")))}</a>'
            )
        table_rows.append(
            [
                esc(row.get("updated_at") or ""),
                vote_icon,
                rec_cell,
                esc(row.get("library_name") or row.get("library_id") or ""),
            ]
        )
    sort_q = dict(query)
    headers = [
        render_sort_link(label=t("portal.votes.table.time"), column="updated_at", current_sort=sort, current_dir=dir, base_path=list_path, query=sort_q),
        render_sort_link(label=t("portal.votes.table.vote"), column="vote", current_sort=sort, current_dir=dir, base_path=list_path, query=sort_q),
        t("portal.votes.table.record"),
        render_sort_link(label=t("portal.votes.table.library"), column="library_name", current_sort=sort, current_dir=dir, base_path=list_path, query=sort_q),
    ]
    filter_pills = _render_filter_pills(
        items=[
            ("all", t("portal.votes.filter.all"), None),
            ("up", t("portal.votes.filter.up"), "up"),
            ("down", t("portal.votes.filter.down"), "down"),
        ],
        base_path=list_path,
        query=query,
        param="vote",
    )
    body = f"""
  {filter_pills}
  <div class="card">
    <div class="card-body" style="padding:0;">
      {render_table(headers, table_rows, empty=t("portal.votes.empty"), locale=locale)}
    </div>
  </div>
  {render_list_footer(page=page_num, total_pages=total_pages, total_items=total, base_path=list_path, query=query, per_page=per_page, default_per_page=_DEFAULT_PER_PAGE, locale=locale)}"""
    return html_response(
        request,
        render_page(
            title=t("portal.votes.title"),
            base=base,
            active_nav="votes",
            subtitle=t("portal.votes.subtitle"),
            user_line=ui_user_line(user),
            show_logout=True,
            is_admin=user.is_admin,
            body=body,
            locale=locale,
            request=request,
        ),
    )


@router.get("/ui/me/setup/", response_class=HTMLResponse)
def portal_me_setup(request: Request, next: str = Query("/ui/me/")) -> Response:
    auth = _require_user(request, require_setup=False)
    if isinstance(auth, Response):
        return auth
    user = auth
    if not display_name_setup_required(user.principal_id):
        target = next if next.startswith("/") and not next.startswith("//") else "/ui/me/"
        return RedirectResponse(target, status_code=302)
    locale, t = ui_locale(request)
    base = _base(request)
    error = unquote(request.query_params.get("error") or "").strip()
    alert = f'<div class="alert error" style="margin-bottom:16px;">{esc(error)}</div>' if error else ""
    body = f"""
  <div class="card">
    <div class="card-header"><h2>{esc(t("portal.setup.card_title"))}</h2></div>
    <div class="card-body">
      <p class="card-muted">{esc(t("portal.setup.welcome"))}</p>
      <ul class="steps">
        <li>{esc(t("portal.setup.unique"))}</li>
        <li>{esc(t("portal.setup.immutable"))}</li>
      </ul>
      {alert}
      <form method="post" action="{esc(base)}/ui/me/setup/">
        <input type="hidden" name="next" value="{esc(next)}"/>
        <label>{esc(t("portal.setup.input_label"))}</label>
        <input name="display_name" type="text" maxlength="32" required autofocus
               style="width:100%;max-width:420px;"/>
        <button type="submit" class="btn primary" style="margin-top:12px;">{esc(t("portal.setup.submit"))}</button>
      </form>
    </div>
  </div>"""
    return html_response(
        request,
        render_page(
            title=t("portal.setup.title"),
            base=base,
            active_nav="me",
            subtitle=t("portal.setup.subtitle"),
            user_line=ui_user_line(user),
            show_logout=True,
            is_admin=user.is_admin,
            body=body,
            locale=locale,
            request=request,
        ),
    )


@router.post("/ui/me/setup/")
async def portal_me_setup_save(request: Request) -> Response:
    _assert_same_origin(request)
    auth = _require_user(request, require_setup=False)
    if isinstance(auth, Response):
        return auth
    user = auth
    if not display_name_setup_required(user.principal_id):
        raise HTTPException(status_code=400, detail="显示名已设定，不可修改")
    form = await request.form()
    base = _base(request)
    next_raw = str(form.get("next") or "/ui/me/")
    next_path = next_raw if next_raw.startswith("/") and not next_raw.startswith("//") else "/ui/me/"
    try:
        complete_display_name_setup(user.principal_id, str(form.get("display_name") or ""))
    except HTTPException as exc:
        if exc.status_code == 400:
            return RedirectResponse(
                f"{base}/ui/me/setup/?next={quote(next_path, safe='')}&error={quote(str(exc.detail), safe='')}",
                status_code=303,
            )
        raise
    return RedirectResponse(next_path, status_code=303)


@router.get("/ui/me/settings/", response_class=HTMLResponse)
def portal_me_settings(request: Request) -> Response:
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    locale, t = ui_locale(request)
    base = _base(request)
    personal_library_name = _personal_library_label(user.display_name, locale=locale)
    body = f"""
  {_render_profile_header(user)}
  {render_subnav(base, active="settings", locale=locale)}
  <div class="card">
    <div class="card-header"><h2>{esc(t("portal.settings.display_name"))}</h2></div>
    <div class="card-body">
      <p class="card-muted">{esc(t("portal.settings.display_name_help", personal_library_name=personal_library_name))}</p>
      <p style="font-size:18px;font-weight:600;margin:8px 0 0;">{esc(user.display_name)}</p>
    </div>
  </div>
  {_render_principal_id_card(user, locale=locale)}"""
    return html_response(
        request,
        render_page(
            title=t("portal.settings.title"),
            base=base,
            active_nav="me",
            subtitle=t("portal.settings.subtitle"),
            user_line=ui_user_line(user),
            show_logout=True,
            is_admin=user.is_admin,
            body=body,
            locale=locale,
            request=request,
        ),
    )


@router.post("/ui/me/settings/")
async def portal_me_settings_save(request: Request) -> Response:
    _assert_same_origin(request)
    auth = _require_user(request, require_setup=False)
    if isinstance(auth, Response):
        return auth
    raise HTTPException(status_code=400, detail="显示名已设定，不可修改")


@router.get("/ui/libraries/", response_class=HTMLResponse)
def portal_libraries(request: Request) -> Response:
    user = resolve_ui_user(request)
    if settings.portal_auth_enabled and user is None:
        return login_redirect(request)
    base = _base(request)
    if user is None:
        return RedirectResponse(f"{base}/ui/libraries/{settings.default_library_id}/", status_code=302)
    libs = list_entitled_libraries(user.principal_id)
    table_rows = []
    for lib in libs:
        table_rows.append(
            [
                f'<a class="key-link" href="{esc(base)}/ui/libraries/{esc(lib["library_id"])}/">{esc(lib["name"])}</a>',
                badge(lib["visibility"], "muted"),
                esc(lib.get("kind") or "—"),
                esc(lib["access"]),
                esc(lib["cases"]),
                esc(lib["records_active"]),
            ]
        )
    body = f"""
  <div class="card">
    <div class="card-body" style="padding:0;">
      {render_table(["库名", "可见性", "类型", "我的权限", "Cases", "Active"], table_rows, empty="暂无库")}
    </div>
  </div>"""
    return HTMLResponse(
        render_page(
            title="库",
            base=base,
            active_nav="libraries",
            subtitle="你有读权限的知识库；仅展示统计，不提供 record 枚举。",
            user_line=ui_user_line(user),
            show_logout=bool(user),
            is_admin=bool(user and user.is_admin),
            body=body,
        )
    )


def _render_library_detail(
    request: Request,
    library_id: str,
    *,
    user: SessionUser | None,
) -> Response:
    base = _base(request)
    if library_id != settings.default_library_id and user is None:
        return login_redirect(request)
    if user is not None and not can_read_library(user.principal_id, library_id):
        raise HTTPException(status_code=404, detail="library not found")
    stats = db.get_library_stats(library_id)
    if not stats:
        raise HTTPException(status_code=404, detail="library not found")

    rec = stats.get("records") or {}
    by_status = rec.get("by_status") or {}
    stat_cards = render_stat_cards(
        [
            ("Cases", stats.get("cases", 0)),
            ("Records", rec.get("total", 0)),
            ("Active", by_status.get("active", 0)),
            ("Draft", by_status.get("draft", 0)),
            ("Invalid", by_status.get("invalid", 0)),
        ]
    )
    outcome_rows = [[item["outcome"], item["count"]] for item in stats.get("by_outcome") or []]
    task_rows = [[item["task_type"], item["count"]] for item in stats.get("by_task_type") or []]

    access_block = ""
    settings_link = ""
    admin_block = ""
    storage_block = ""
    if user is not None:
        lib_entry = next((x for x in list_entitled_libraries(user.principal_id) if x["library_id"] == library_id), None)
        prefixes = ", ".join(lib_entry["key_prefixes"]) if lib_entry and lib_entry["key_prefixes"] else "—"
        access_block = f"""
  <div class="card" style="margin-top:16px;">
    <div class="card-header"><h2>我的访问</h2></div>
    <div class="card-body">
      <dl class="kv">
        <dt>权限</dt><dd>{esc(lib_entry["access"] if lib_entry else "读")}</dd>
        <dt>绑定 key</dt><dd><code>{esc(prefixes)}</code></dd>
      </dl>
    </div>
  </div>"""
        quota = personal_library_quota_summary(principal_id=user.principal_id, library_id=library_id)
        if quota:
            label = f'{format_storage_bytes(quota["used_bytes"])} / {format_storage_bytes(quota["limit_bytes"])}'
            storage_block = f"""
  <div class="card" style="margin-top:16px;">
    <div class="card-header"><h2>存储</h2></div>
    <div class="card-body">
      {render_storage_meter(used_bytes=int(quota["used_bytes"]), limit_bytes=int(quota["limit_bytes"]), label=label)}
      <p style="margin-top:8px;"><a class="btn subtle" href="{esc(base)}/ui/libraries/{esc(library_id)}/storage/">存储详情 →</a></p>
    </div>
  </div>"""
        elif library_id != settings.default_library_id:
            used = db.sum_library_record_content_bytes(library_id)
            storage_block = f"""
  <div class="card" style="margin-top:16px;">
    <div class="card-header"><h2>存储</h2></div>
    <div class="card-body">
      {render_storage_meter(used_bytes=used, limit_bytes=None, label=f'已用 {format_storage_bytes(used)}（预览）')}
      <p style="margin-top:8px;"><a class="btn subtle" href="{esc(base)}/ui/libraries/{esc(library_id)}/storage/">存储详情 →</a></p>
    </div>
  </div>"""
        if is_library_settings_editor(library_id, user.principal_id, is_admin=user.is_admin):
            hours = db.get_library_write_buffer_hours(library_id)
            settings_link = f"""
  <p style="margin-top:12px;">
    <a class="btn" href="{esc(base)}/ui/libraries/{esc(library_id)}/settings/">库设置</a>
    <span class="card-muted"> · 写入缓冲期 {esc(hours)}h</span>
  </p>"""
        if can_maintain_library(user.principal_id, library_id):
            admin_block = f"""
  <div class="card" style="margin-top:16px;">
    <div class="card-header"><h2>库管理</h2></div>
    <div class="card-body actions">
      <a class="btn" href="{esc(base)}/ui/libraries/{esc(library_id)}/records/">记录列表</a>
      <a class="btn" href="{esc(base)}/ui/libraries/{esc(library_id)}/grants/">授权</a>
      <a class="btn" href="{esc(base)}/ui/libraries/{esc(library_id)}/storage/">存储</a>
    </div>
  </div>"""
    else:
        access_block = f"""
  <div class="alert info" style="margin-top:16px;">
    <a href="{esc(base)}/auth/login?next={esc(base)}/ui/libraries/{esc(library_id)}/">登录</a>
    以贡献知识、管理 API key 与投票。
  </div>"""

    breadcrumb = render_breadcrumb(
        [
            ("Libraries", f"{base}/ui/libraries/"),
            (stats.get("name") or library_id, None),
        ]
    )
    body = f"""
  {stat_cards}
  <div class="card" style="margin-top:16px;">
    <div class="card-header"><h2>分布</h2></div>
    <div class="card-body">
      <div class="split">
        <div>{render_table(["Outcome", "数量"], outcome_rows[:8], empty="—")}</div>
        <div>{render_table(["Task type", "数量"], task_rows[:8], empty="—")}</div>
      </div>
    </div>
  </div>
  {access_block}
  {storage_block}
  {admin_block}
  {settings_link}
  <p class="card-muted" style="margin-top:12px;">库内 record 列表需库维护权限；普通读权限仅见聚合统计。</p>"""
    return HTMLResponse(
        render_page(
            title=stats.get("name") or library_id,
            base=base,
            active_nav="libraries" if user else "",
            subtitle=f'{badge(stats.get("visibility", ""), "muted")} · {esc(stats.get("org_name") or "")}',
            user_line=ui_user_line(user),
            show_logout=bool(user),
            is_admin=bool(user and user.is_admin),
            breadcrumb_html=breadcrumb,
            show_minimal_header=user is None,
            body=body,
        )
    )


@router.get("/ui/libraries/{library_id}", response_class=HTMLResponse)
@router.get("/ui/libraries/{library_id}/", response_class=HTMLResponse)
def portal_library_detail(request: Request, library_id: str) -> Response:
    user = resolve_ui_user(request)
    return _render_library_detail(request, library_id, user=user)


def _render_record_page(
    base: str,
    record: dict[str, Any],
    feedback: dict[str, Any],
    user: SessionUser | None,
    *,
    is_owner: bool = False,
) -> str:
    my_vote = feedback.get("my_vote")
    up_active = my_vote == "up"
    down_active = my_vote == "down"
    feedback_action = f"{base}/ui/records/{esc(record['id'])}/feedback"
    btn = lambda label, vote, active: (
        f'<form method="post" action="{feedback_action}?vote={esc(vote)}" style="display:inline;">'
        f'<button type="submit" class="btn{" primary" if active else ""}">{label}</button></form>'
    )
    status = record.get("status", "")
    status_kind = "success" if status == "active" else "muted"
    publish_line = ""
    if status == "buffered" and record.get("publish_at"):
        publish_line = f"<dt>发布于</dt><dd>{esc(record.get('publish_at') or '')}</dd>"
    buffer_actions = ""
    if status == "buffered" and is_owner and user is not None:
        rid = esc(record["id"])
        buffer_actions = f"""
        <div class="card" style="margin-bottom:16px;">
          <div class="card-header"><h2>待发布</h2></div>
          <div class="card-body">
            <p class="card-muted">仅你可见；到期自动发布，或立即发布 / 修改 / 删除。</p>
            <div class="actions" style="margin-bottom:12px;">
              <form method="post" action="{base}/ui/records/{rid}/publish" style="display:inline;">
                <button type="submit" class="btn primary">立即发布</button>
              </form>
              <form method="post" action="{base}/ui/records/{rid}/delete" style="display:inline;"
                    onsubmit="return confirm('确定删除？');">
                <button type="submit" class="btn">删除</button>
              </form>
            </div>
            <form method="post" action="{base}/ui/records/{rid}/edit">
              <label>Problem</label>
              <textarea name="problem" rows="3" style="width:100%;">{esc(record.get("problem", ""))}</textarea>
              <label style="margin-top:8px;display:block;">Outcome</label>
              <input name="outcome" type="text" style="width:100%;" value="{esc(record.get("outcome", ""))}"/>
              <label style="margin-top:8px;display:block;">Summary</label>
              <textarea name="result_summary" rows="4" style="width:100%;">{esc(record.get("result_summary", ""))}</textarea>
              <button type="submit" class="btn" style="margin-top:12px;">保存修改</button>
            </form>
          </div>
        </div>"""
    vote_block = ""
    if user is not None and status == "active":
        vote_block = f"""
        <div class="actions" style="margin-bottom:12px;">
          {btn(f"👍 {esc(feedback.get('up', 0))}", "up", up_active)}
          {btn(f"👎 {esc(feedback.get('down', 0))}", "down", down_active)}
          {btn("清除我的投票", "clear", False)}
        </div>
        <p class="card-muted">同一用户对同一 record 只能保留一票。</p>"""
    body = f"""
  {buffer_actions}
  <div class="split">
    <div class="card">
      <div class="card-header">
        <h2>知识条目</h2>
        {badge(record.get("status", ""), status_kind)}
      </div>
      <div class="card-body">
        <dl class="kv">
          <dt>ID</dt><dd><code>{esc(record["id"])}</code></dd>
          <dt>Library</dt><dd><code>{esc(record.get("library_id", ""))}</code></dd>
          <dt>Case</dt><dd>{esc(record.get("case_id") or "—")}</dd>
          <dt>Outcome</dt><dd>{badge(record.get("outcome", ""), "muted")}</dd>
          <dt>Created</dt><dd>{esc(record.get("created_at", ""))}</dd>
          {publish_line}
        </dl>
        <h3 style="margin:20px 0 8px;font-size:15px;">Problem</h3>
        <p style="margin:0;">{esc(record.get("problem", ""))}</p>
        <h3 style="margin:20px 0 8px;font-size:15px;">Summary</h3>
        <p style="margin:0;">{esc(record.get("result_summary", ""))}</p>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><h2>Feedback</h2></div>
      <div class="card-body">
        {vote_block}
        <p><a class="btn" href="{esc(base)}/ui/me/">← 我的主页</a></p>
      </div>
    </div>
  </div>"""
    breadcrumb = render_breadcrumb([("我的主页", f"{base}/ui/me/"), (record["id"], None)])
    return render_page(
        title=f"Record {record['id']}",
        base=base,
        active_nav="me",
        subtitle="单条 record 详情。",
        user_line=ui_user_line(user),
        show_logout=bool(user),
        is_admin=bool(user and user.is_admin),
        breadcrumb_html=breadcrumb,
        body=body,
    )


@router.get("/ui/records/{record_id}", response_class=HTMLResponse)
@router.get("/ui/records/{record_id}/", response_class=HTMLResponse)
def portal_record(request: Request, record_id: str) -> Response:
    db.publish_due_buffered_records()
    user = resolve_ui_user(request)
    if user is None:
        return login_redirect(request)
    record = db.get_record(record_id)
    if not record or db.get_record_deletion(record_id):
        raise HTTPException(status_code=404, detail="record not found")
    library_id = str(record.get("library_id") or "")
    if not can_read_library(user.principal_id, library_id) and not user.is_admin:
        raise HTTPException(status_code=404, detail="record not found")
    if not can_read_record(
        record,
        principal_id=user.principal_id,
        is_admin=user.is_admin,
        readable_library_ids=entitled_library_ids(user.principal_id),
    ):
        raise HTTPException(status_code=404, detail="record not found")
    display = format_record_for_read(record, include_full_json=False)
    base = _base(request)
    is_owner = db.is_record_owner(record_id, user.principal_id)
    feedback: dict[str, Any] = {"up": 0, "down": 0}
    if record.get("status") == "active":
        try:
            principal_id = resolve_ui_feedback_principal(request)
            feedback = db.get_feedback_summaries([record_id], principal_id=principal_id)[record_id]
        except HTTPException:
            feedback = db.get_feedback_summaries([record_id])[record_id]
    return HTMLResponse(_render_record_page(base, display, feedback, user, is_owner=is_owner))


@router.post("/ui/records/{record_id}/publish")
def portal_record_publish(request: Request, record_id: str) -> Response:
    _assert_same_origin(request)
    user = resolve_ui_user(request)
    if user is None:
        return login_redirect(request)
    record = db.get_record(record_id)
    if not record or record.get("status") != "buffered":
        raise HTTPException(status_code=404, detail="record not found")
    if not db.is_record_owner(record_id, user.principal_id):
        raise HTTPException(status_code=404, detail="record not found")
    db.publish_buffered_record(record_id)
    payload = record.get("payload") or {}
    based_on = payload.get("based_on_record_ids") if isinstance(payload, dict) else []
    if isinstance(based_on, list) and based_on:
        db.insert_record_relations(
            source_id=record_id,
            based_on_record_ids=[str(x) for x in based_on],
            relation_type=payload.get("relation_type") if isinstance(payload, dict) else None,
        )
    return RedirectResponse(f"{_base(request)}/ui/records/{record_id}/", status_code=303)


@router.post("/ui/records/{record_id}/edit")
async def portal_record_edit(request: Request, record_id: str) -> Response:
    _assert_same_origin(request)
    user = resolve_ui_user(request)
    if user is None:
        return login_redirect(request)
    record = db.get_record(record_id)
    if not record or record.get("status") != "buffered":
        raise HTTPException(status_code=404, detail="record not found")
    if not db.is_record_owner(record_id, user.principal_id):
        raise HTTPException(status_code=404, detail="record not found")
    form = await request.form()
    problem = str(form.get("problem") or "").strip()
    outcome = str(form.get("outcome") or "").strip()
    result_summary = str(form.get("result_summary") or "").strip()
    if not problem or not outcome or not result_summary:
        raise HTTPException(status_code=400, detail="problem, outcome, and result_summary required")
    library_id = str(record["library_id"])
    hours = db.get_library_write_buffer_hours(library_id)
    from app.services.buffer_service import compute_publish_at

    publish_at = compute_publish_at(buffer_hours=hours) if hours > 0 else None
    payload = dict(record.get("payload") or {})
    payload.update({"problem": problem, "outcome": outcome, "result_summary": result_summary})
    from app.services.storage_quota_service import assert_personal_library_write_allowed

    assert_personal_library_write_allowed(
        library_id=library_id,
        principal_id=user.principal_id,
        problem=problem,
        outcome=outcome,
        result_summary=result_summary,
        payload=payload,
        exclude_record_id=record_id,
    )
    db.update_buffered_record(
        record_id,
        problem=problem,
        outcome=outcome,
        result_summary=result_summary,
        payload=payload,
        publish_at=publish_at,
    )
    if hours <= 0:
        db.publish_buffered_record(record_id)
        based_on = payload.get("based_on_record_ids") if isinstance(payload, dict) else []
        if isinstance(based_on, list) and based_on:
            db.insert_record_relations(
                source_id=record_id,
                based_on_record_ids=[str(x) for x in based_on],
                relation_type=payload.get("relation_type") if isinstance(payload, dict) else None,
            )
    return RedirectResponse(f"{_base(request)}/ui/records/{record_id}/", status_code=303)


@router.post("/ui/records/{record_id}/delete")
def portal_record_delete(request: Request, record_id: str) -> Response:
    _assert_same_origin(request)
    user = resolve_ui_user(request)
    if user is None:
        return login_redirect(request)
    record = db.get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="record not found")
    if not db.is_record_owner(record_id, user.principal_id):
        raise HTTPException(status_code=404, detail="record not found")
    library_id = str(record["library_id"])
    protected, _ret = db.library_deletion_protection(library_id)
    if protected:
        db.soft_delete_record(record_id)
    else:
        db.hard_delete_record(record_id, deleted_by=user.principal_id)
    return RedirectResponse(f"{_base(request)}/ui/me/writes/", status_code=303)


@router.get("/ui/libraries/{library_id}/settings/", response_class=HTMLResponse)
def portal_library_settings(request: Request, library_id: str) -> Response:
    user = resolve_ui_user(request)
    if user is None:
        return login_redirect(request)
    if not is_library_settings_editor(library_id, user.principal_id, is_admin=user.is_admin):
        raise HTTPException(status_code=404, detail="library not found")
    lib = db.get_library(library_id)
    if not lib:
        raise HTTPException(status_code=404, detail="library not found")
    base = _base(request)
    hours = db.get_library_write_buffer_hours(library_id)
    body = f"""
  <div class="card">
    <div class="card-header"><h2>库设置</h2></div>
    <div class="card-body">
      <form method="post" action="{esc(base)}/ui/libraries/{esc(library_id)}/settings/">
        <label>写入缓冲期（小时，0 = 关闭）</label>
        <input name="write_buffer_hours" type="number" min="0" max="168" value="{esc(hours)}" style="width:120px;"/>
        <p class="card-muted" style="margin-top:8px;">默认 24。设为 0 时新写入立即发布（active）。</p>
        <button type="submit" class="btn primary" style="margin-top:12px;">保存</button>
      </form>
    </div>
  </div>
  <p><a class="btn" href="{esc(base)}/ui/libraries/{esc(library_id)}/">← 返回库详情</a></p>"""
    return HTMLResponse(
        render_page(
            title=f"{lib.get('name') or library_id} · 设置",
            base=base,
            active_nav="libraries",
            subtitle="写入缓冲期配置",
            user_line=ui_user_line(user),
            show_logout=True,
            is_admin=user.is_admin,
            body=body,
        )
    )


@router.post("/ui/libraries/{library_id}/settings/")
async def portal_library_settings_save(request: Request, library_id: str) -> Response:
    _assert_same_origin(request)
    user = resolve_ui_user(request)
    if user is None:
        return login_redirect(request)
    if not is_library_settings_editor(library_id, user.principal_id, is_admin=user.is_admin):
        raise HTTPException(status_code=404, detail="library not found")
    form = await request.form()
    try:
        hours = int(form.get("write_buffer_hours", 24))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="invalid write_buffer_hours")
    db.set_library_write_buffer_hours(library_id, hours)
    return RedirectResponse(f"{_base(request)}/ui/libraries/{library_id}/settings/?saved=1", status_code=303)


@router.post("/ui/records/{record_id}/feedback")
def portal_record_feedback(
    request: Request,
    record_id: str,
    vote: str = Query(...),
) -> Response:
    _assert_same_origin(request)
    user = resolve_ui_user(request)
    if user is None:
        return login_redirect(request)
    if vote not in {"up", "down", "clear"}:
        raise HTTPException(status_code=400, detail="vote must be up, down, or clear")
    record = db.get_record(record_id)
    if not record or record.get("status") != "active":
        raise HTTPException(status_code=404, detail="record not found")
    library_id = str(record.get("library_id") or "")
    if not can_read_library(user.principal_id, library_id):
        raise HTTPException(status_code=404, detail="record not found")
    principal_id = resolve_ui_feedback_principal(request)
    apply_record_feedback(
        record_id=record_id,
        principal_id=principal_id,
        vote=vote,  # type: ignore[arg-type]
        readable_library_ids=entitled_library_ids(user.principal_id),
    )
    return RedirectResponse(f"/ui/records/{record_id}/", status_code=303)
