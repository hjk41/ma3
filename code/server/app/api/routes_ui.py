from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app.api.ui_theme import badge, esc, render_page, render_page_403, render_stat_cards, render_table
from app.api.ui_session import login_redirect, resolve_ui_user, ui_user_line
from app.core.config import settings
from app.services.feedback_service import apply_record_feedback, resolve_ui_feedback_principal
from app.services.record_read_service import format_record_for_read
from app.storage.db import get_feedback_summaries, get_record, get_system_stats, is_postgres

router = APIRouter(prefix="/ui/observatory", tags=["observatory"])


def _render_observatory_page(
    base: str,
    stats: dict[str, Any],
    user_line: str,
    *,
    show_logout: bool,
    is_admin: bool = True,
) -> str:
    knowledge = stats["knowledge"]
    records = knowledge["records"]
    active = records["by_status"].get("active", 0)
    draft = records["by_status"].get("draft", 0)
    invalid = records["by_status"].get("invalid", 0)
    stat_cards = render_stat_cards(
        [
            ("Organizations", stats["organizations"]["count"]),
            ("Libraries", stats["libraries"]["count"]),
            ("Users", stats["users"]["count"]),
            ("Cases", knowledge["cases"]),
            ("Records", records["total"]),
            ("Active", active),
            ("Draft", draft),
            ("Invalid", invalid),
        ]
    )
    org_rows = [[o["id"], o["name"]] for o in stats["organizations"]["items"]]
    lib_rows = [
        [
            lib["id"],
            lib["name"],
            lib["org_name"],
            badge(lib["visibility"], "muted"),
            lib["cases"],
            lib["records"]["total"],
            lib["records"]["by_status"].get("active", 0),
            lib["records"]["by_status"].get("draft", 0),
            lib["records"]["by_status"].get("invalid", 0),
        ]
        for lib in stats["libraries"]["items"]
    ]
    outcome_rows = [[item["outcome"], item["count"]] for item in stats["knowledge"]["by_outcome"]]
    task_rows = [[item["task_type"], item["count"]] for item in stats["knowledge"]["by_task_type"]]
    user_rows = [[u["id"], u["kind"], u["display_name"], u["created_at"]] for u in stats["users"]["items"]]
    meta_pills = " ".join(
        [
            f'<span class="pill">DB {esc("postgresql" if is_postgres() else "sqlite")}</span>',
            f'<span class="pill">{esc(settings.instance_id or "local")}</span>',
            f'<span class="pill">{esc(settings.git_commit or "dev")}</span>',
        ]
    )
    actions = f'<a class="btn" href="{esc(base)}/ui/observatory/stats.json">stats.json</a>'
    body = f"""
  <div class="pill-list" style="margin-bottom:16px;">{meta_pills}</div>
  {stat_cards}
  <div class="grid" style="gap:16px;">
    <div class="card">
      <div class="card-header"><h2>Organizations ({esc(stats["organizations"]["count"])})</h2></div>
      <div class="card-body" style="padding:0;">
        {render_table(["ID", "名称"], org_rows)}
      </div>
    </div>
    <div class="card">
      <div class="card-header"><h2>Libraries ({esc(stats["libraries"]["count"])})</h2></div>
      <div class="card-body" style="padding:0;">
        {render_table(
            ["ID", "名称", "组织", "可见性", "Cases", "Records", "Active", "Draft", "Invalid"],
            lib_rows,
        )}
      </div>
    </div>
    <div class="card">
      <div class="card-header"><h2>Users ({esc(stats["users"]["count"])})</h2></div>
      <div class="card-body">
        <div class="alert info">{esc(stats["users"]["note"])}</div>
        {render_table(["ID", "类型", "显示名", "创建时间"], user_rows)}
      </div>
    </div>
    <div class="card">
      <div class="card-header"><h2>知识分布</h2></div>
      <div class="card-body">
        <div class="split">
          <div>
            <h3 style="margin:0 0 8px;font-size:14px;">按 outcome</h3>
            {render_table(["Outcome", "数量"], outcome_rows)}
          </div>
          <div>
            <h3 style="margin:0 0 8px;font-size:14px;">按 task_type</h3>
            {render_table(["Task type", "数量"], task_rows)}
          </div>
        </div>
      </div>
    </div>
  </div>"""
    return render_page(
        title="Observatory",
        base=base,
        active_nav="observatory",
        subtitle="系统概览：组织、知识库、用户与知识条目统计（只读）。",
        user_line=user_line,
        show_logout=show_logout,
        is_admin=is_admin,
        actions_html=actions,
        body=body,
    )


@router.get("/stats.json")
def observatory_stats_json(request: Request) -> JSONResponse:
    denied = _require_observatory_admin(request)
    if denied is not None:
        if isinstance(denied, HTMLResponse):
            return JSONResponse({"detail": "forbidden"}, status_code=403)
        return JSONResponse({"detail": "authentication required"}, status_code=401)
    return JSONResponse(get_system_stats())


def _observatory_user_line(request: Request) -> tuple[Any | None, str]:
    if not settings.authing_configured:
        return None, "未启用 Authing；Observatory 为开放只读（LAN dev）。"
    user = resolve_ui_user(request)
    if user is None:
        return None, ""
    return user, ui_user_line(user)


def _require_observatory_admin(request: Request) -> Response | None:
    if not settings.authing_configured:
        return None
    user = resolve_ui_user(request)
    if user is None:
        return RedirectResponse(f"/auth/login?next={request.url.path}", status_code=302)
    if not user.is_admin:
        base = str(request.base_url).rstrip("/")
        return HTMLResponse(
            render_page_403(
                base=base,
                message="Observatory 仅产品管理员可访问。",
                back_href=f"{base}/ui/me/",
                back_label="返回我的主页",
            ),
            status_code=403,
        )
    return None


def _require_observatory_session(request: Request) -> Response | None:
    if not settings.authing_configured:
        return None
    user = resolve_ui_user(request)
    if user is None:
        return RedirectResponse(f"/auth/login?next={request.url.path}", status_code=302)
    return None


def _render_record_page(
    base: str,
    record: dict[str, Any],
    feedback: dict[str, Any],
    user_line: str,
    *,
    show_logout: bool,
    is_admin: bool = False,
) -> str:
    my_vote = feedback.get("my_vote")
    up_active = my_vote == "up"
    down_active = my_vote == "down"
    feedback_action = f"{base}/ui/records/{esc(record['id'])}/feedback"
    btn = lambda label, vote, active: (
        f'<form method="post" action="{feedback_action}?vote={esc(vote)}" style="display:inline;">'
        f'<button type="submit" class="btn{" primary" if active else ""}">{label}</button></form>'
    )
    status_kind = "success" if record.get("status") == "active" else "muted"
    body = f"""
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
        <div class="actions" style="margin-bottom:12px;">
          {btn(f"👍 {esc(feedback.get('up', 0))}", "up", up_active)}
          {btn(f"👎 {esc(feedback.get('down', 0))}", "down", down_active)}
          {btn("清除我的投票", "clear", False)}
        </div>
        <p class="card-muted">同一用户对同一 record 只能保留一票，可改投或清除。</p>
        <p><a class="btn" href="{esc(base)}/ui/me/">← 我的主页</a></p>
      </div>
    </div>
  </div>"""
    return render_page(
        title=f"Record {record['id']}",
        base=base,
        active_nav="me",
        subtitle="知识条目详情。",
        user_line=user_line,
        show_logout=show_logout,
        is_admin=is_admin,
        body=body,
    )


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def observatory_home(request: Request) -> Response:
    denied = _require_observatory_admin(request)
    if denied is not None:
        return denied
    user, user_line = _observatory_user_line(request)
    base = str(request.base_url).rstrip("/")
    stats = get_system_stats()
    html = _render_observatory_page(
        base,
        stats,
        user_line,
        show_logout=settings.authing_configured,
        is_admin=bool(user and user.is_admin),
    )
    response = HTMLResponse(html)
    if not settings.authing_configured and not request.cookies.get("ma3_ui_session"):
        response.set_cookie("ma3_ui_session", uuid.uuid4().hex, httponly=True, samesite="lax", max_age=86400 * 30)
    return response


@router.get("/records/{record_id}", response_class=HTMLResponse)
def observatory_record(request: Request, record_id: str) -> Response:
    return RedirectResponse(f"/ui/records/{record_id}/", status_code=301)


@router.post("/records/{record_id}/feedback")
def observatory_record_feedback(
    request: Request,
    record_id: str,
    vote: str = Query(...),
) -> Response:
    return RedirectResponse(f"/ui/records/{record_id}/feedback?vote={vote}", status_code=307)
