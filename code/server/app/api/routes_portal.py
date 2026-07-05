from __future__ import annotations

import math
from typing import Any
from urllib.parse import quote, unquote, urlparse

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.api.ui_session import (
    login_redirect,
    require_authed_ui_user,
    require_authing_for_ui,
    resolve_ui_user,
    ui_user_line,
)
from app.api.ui_theme import (
    badge,
    esc,
    render_breadcrumb,
    render_page,
    render_pagination,
    render_stat_cards,
    render_subnav,
    render_table,
)
from app.auth.session import SessionUser
from app.core.config import settings
from app.services.feedback_service import apply_record_feedback, resolve_ui_feedback_principal
from app.services.buffer_service import can_read_record, is_library_settings_editor
from app.services.portal_service import can_read_library, entitled_library_ids, list_entitled_libraries
from app.services.principal_service import complete_display_name_setup, display_name_setup_required
from app.services.record_read_service import format_record_for_read
from app.storage import db

router = APIRouter(tags=["portal"])

_PAGE_SIZE = 50


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _page_params(page: int) -> tuple[int, int]:
    page = max(1, page)
    return page, (page - 1) * _PAGE_SIZE


def _assert_same_origin(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    expected = (settings.public_base_url or str(request.base_url)).rstrip("/")
    origin = request.headers.get("origin")
    if origin:
        if origin.rstrip("/") != expected:
            raise HTTPException(status_code=403, detail="cross-origin request rejected")
        return
    referer = request.headers.get("referer")
    if referer:
        ref = urlparse(referer)
        exp = urlparse(expected if "://" in expected else f"http://{expected}")
        if ref.netloc and exp.netloc and ref.netloc != exp.netloc:
            raise HTTPException(status_code=403, detail="cross-origin request rejected")
        return
    raise HTTPException(status_code=403, detail="origin or referer required")


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


def _render_principal_id_card(user: SessionUser) -> str:
    return f"""
  <div class="card">
    <div class="card-header"><h2>Principal ID</h2></div>
    <div class="card-body">
      <p class="card-muted">ma3 内部身份标识，创建 API key 或排查权限时可能需要。显示名在注册时设定，之后不可修改。</p>
      <code class="mono id-block">{esc(user.principal_id)}</code>
    </div>
  </div>"""


def _problem_summary(problem: str | None, *, width: int = 60) -> str:
    text = (problem or "").strip()
    if len(text) <= width:
        return text
    return text[: width - 1] + "…"


@router.get("/ui/me", response_class=HTMLResponse)
@router.get("/ui/me/", response_class=HTMLResponse)
def portal_me(request: Request) -> Response:
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    base = _base(request)
    db.publish_due_buffered_records()
    writes_count = db.count_write_audit_for_principal(user.principal_id)
    buffered_count = db.count_buffered_for_principal(user.principal_id)
    votes_count = db.count_feedback_for_principal(user.principal_id)
    libs = list_entitled_libraries(user.principal_id)
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
        if not rid or db.get_record_deletion(str(rid)):
            list_items.append(
                '<div class="list-item">'
                f'<div class="list-item-title">{esc(_problem_summary(row.get("problem")))}</div>'
                f'<div class="list-item-meta">{esc(row.get("library_name") or "")} · 已删除</div></div>'
            )
            continue
        status_label = row.get("record_status") or "active"
        meta_suffix = f" · {esc(status_label)}" if status_label == "buffered" else f" · {esc(row.get('created_at') or '')}"
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
            "<div>还没有贡献。</div>"
            f'<div class="empty-cta"><a class="btn primary" href="{esc(base)}/ui/keys/">创建 API key</a> '
            f'<a class="btn" href="{esc(base)}/client/agent-onboarding.md">接入文档</a></div></div>'
        )
    )

    body = f"""
  {_render_profile_header(user)}
  {render_subnav(base, active="overview")}
  {render_stat_cards([
      ("我的贡献", writes_count),
      ("待发布", buffered_count),
      ("可访问库", len(libs)),
      ("我的投票", votes_count),
      ("API Keys", keys_count),
  ])}
  <div class="card" style="margin-top:16px;">
    <div class="card-header">
      <h2>我的库</h2>
      <a class="btn subtle" href="{esc(base)}/ui/libraries/">查看全部 →</a>
    </div>
    <div class="card-body" style="padding:0;">
      {render_table(["库名", "可见性", "权限", "角色"], lib_rows, empty="暂无库")}
    </div>
  </div>
  <div class="card" style="margin-top:16px;">
    <div class="card-header">
      <h2>最近贡献</h2>
      <a class="btn subtle" href="{esc(base)}/ui/me/writes/">查看全部 →</a>
    </div>
    <div class="card-body">{recent_block}</div>
  </div>"""
    return HTMLResponse(
        render_page(
            title="我的主页",
            base=base,
            active_nav="me",
            subtitle="你在 ma3 的贡献与权限概览。",
            user_line=ui_user_line(user),
            show_logout=True,
            is_admin=user.is_admin,
            body=body,
        )
    )


@router.get("/ui/me/writes/", response_class=HTMLResponse)
def portal_writes(request: Request, page: int = Query(1, ge=1)) -> Response:
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    base = _base(request)
    page_num, offset = _page_params(page)
    total = db.count_write_audit_for_principal(user.principal_id)
    total_pages = max(1, math.ceil(total / _PAGE_SIZE))
    rows_data = db.list_write_audit_for_principal(user.principal_id, limit=_PAGE_SIZE, offset=offset)
    table_rows = []
    for row in rows_data:
        rid = row.get("record_id")
        deleted = bool(rid and db.get_record_deletion(str(rid)))
        if deleted or not rid:
            rec_cell = esc(_problem_summary(row.get("problem"))) + " " + badge("已删除", "muted")
        else:
            rec_cell = (
                f'<a class="key-link" href="{esc(base)}/ui/records/{esc(rid)}/">'
                f'{esc(_problem_summary(row.get("problem")))}</a>'
            )
        st = row.get("record_status") or "active"
        st_cell = badge("待发布", "muted") if st == "buffered" else badge(st, "success" if st == "active" else "muted")
        table_rows.append(
            [
                esc(row.get("created_at") or ""),
                rec_cell,
                st_cell,
                esc(row.get("library_name") or ""),
                badge(str(row.get("report_kind") or "new"), "muted"),
                esc(row.get("key_prefix") or row.get("api_key_id") or "—"),
            ]
        )
    body = f"""
  {render_subnav(base, active="writes")}
  <div class="card">
    <div class="card-body" style="padding:0;">
      {render_table(["时间", "记录", "状态", "库", "类型", "Key"], table_rows, empty="暂无贡献")}
    </div>
  </div>
  {render_pagination(page=page_num, total_pages=total_pages, base_path=f"{base}/ui/me/writes/")}"""
    return HTMLResponse(
        render_page(
            title="我的贡献",
            base=base,
            active_nav="me",
            subtitle="来自写审计日志；含 API key 写入记录。",
            user_line=ui_user_line(user),
            show_logout=True,
            is_admin=user.is_admin,
            body=body,
        )
    )


@router.get("/ui/me/votes/", response_class=HTMLResponse)
def portal_votes(request: Request, page: int = Query(1, ge=1)) -> Response:
    auth = _require_user(request)
    if isinstance(auth, Response):
        return auth
    user = auth
    base = _base(request)
    page_num, offset = _page_params(page)
    total = db.count_feedback_for_principal(user.principal_id)
    total_pages = max(1, math.ceil(total / _PAGE_SIZE))
    rows_data = db.list_feedback_for_principal(user.principal_id, limit=_PAGE_SIZE, offset=offset)
    table_rows = []
    for row in rows_data:
        rid = row.get("record_id")
        vote = "👍" if int(row.get("vote") or 0) > 0 else "👎"
        deleted = bool(rid and db.get_record_deletion(str(rid)))
        if deleted or not rid or row.get("status") != "active":
            rec_cell = esc(_problem_summary(row.get("problem"))) + " " + badge("不可用", "muted")
        else:
            rec_cell = (
                f'<a class="key-link" href="{esc(base)}/ui/records/{esc(rid)}/">'
                f'{esc(_problem_summary(row.get("problem")))}</a>'
            )
        table_rows.append(
            [
                esc(row.get("updated_at") or ""),
                vote,
                rec_cell,
                esc(row.get("library_name") or row.get("library_id") or ""),
            ]
        )
    body = f"""
  {render_subnav(base, active="votes")}
  <div class="card">
    <div class="card-body" style="padding:0;">
      {render_table(["时间", "投票", "记录", "库"], table_rows, empty="还没有投过票")}
    </div>
  </div>
  {render_pagination(page=page_num, total_pages=total_pages, base_path=f"{base}/ui/me/votes/")}"""
    return HTMLResponse(
        render_page(
            title="我的投票",
            base=base,
            active_nav="me",
            subtitle="只读列表；改票请进入 record 详情页。",
            user_line=ui_user_line(user),
            show_logout=True,
            is_admin=user.is_admin,
            body=body,
        )
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
    base = _base(request)
    error = unquote(request.query_params.get("error") or "").strip()
    alert = f'<div class="alert error" style="margin-bottom:16px;">{esc(error)}</div>' if error else ""
    body = f"""
  <div class="card">
    <div class="card-header"><h2>设定显示名</h2></div>
    <div class="card-body">
      <p class="card-muted">欢迎加入 ma3。请选择一个<strong>显示名</strong>：它将出现在门户顶部、个人库名称等位置。</p>
      <ul class="steps">
        <li>显示名在 ma3 内<strong>全局唯一</strong>（不区分大小写）</li>
        <li>设定后<strong>不可修改</strong>，请谨慎选择</li>
      </ul>
      {alert}
      <form method="post" action="{esc(base)}/ui/me/setup/">
        <input type="hidden" name="next" value="{esc(next)}"/>
        <label>显示名（2–32 字符）</label>
        <input name="display_name" type="text" maxlength="32" required autofocus
               style="width:100%;max-width:420px;"/>
        <button type="submit" class="btn primary" style="margin-top:12px;">确认并继续</button>
      </form>
    </div>
  </div>"""
    return HTMLResponse(
        render_page(
            title="设定显示名",
            base=base,
            active_nav="me",
            subtitle="注册后一次性设定，之后不可更改。",
            user_line=ui_user_line(user),
            show_logout=True,
            is_admin=user.is_admin,
            body=body,
        )
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
    base = _base(request)
    body = f"""
  {_render_profile_header(user)}
  {render_subnav(base, active="settings")}
  <div class="card">
    <div class="card-header"><h2>显示名</h2></div>
    <div class="card-body">
      <p class="card-muted">注册时设定，之后不可修改。用于门户顶部、个人库名称（「{esc(user.display_name)} 的个人库」）等。</p>
      <p style="font-size:18px;font-weight:600;margin:8px 0 0;">{esc(user.display_name)}</p>
    </div>
  </div>
  {_render_principal_id_card(user)}"""
    return HTMLResponse(
        render_page(
            title="账户设置",
            base=base,
            active_nav="me",
            subtitle="账户与身份信息",
            user_line=ui_user_line(user),
            show_logout=True,
            is_admin=user.is_admin,
            body=body,
        )
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
    if settings.authing_configured and user is None:
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
            title="Libraries",
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
        if is_library_settings_editor(library_id, user.principal_id, is_admin=user.is_admin):
            hours = db.get_library_write_buffer_hours(library_id)
            settings_link = f"""
  <p style="margin-top:12px;">
    <a class="btn" href="{esc(base)}/ui/libraries/{esc(library_id)}/settings/">库设置</a>
    <span class="card-muted"> · 写入缓冲期 {esc(hours)}h</span>
  </p>"""
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
  {settings_link}
  <p class="card-muted" style="margin-top:12px;">库内 record 列表仅管理员可枚举；此处仅展示聚合统计。</p>"""
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
