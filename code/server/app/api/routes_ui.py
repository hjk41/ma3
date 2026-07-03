from __future__ import annotations

import html
from typing import Any

import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app.auth.session import resolve_session_user
from app.core.config import settings
from app.services.feedback_service import apply_record_feedback, resolve_ui_feedback_principal
from app.services.record_read_service import format_record_for_read
from app.storage.db import get_feedback_summaries, get_record, get_system_stats, is_postgres

router = APIRouter(prefix="/ui/observatory", tags=["observatory"])


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _render_stat_cards(stats: dict[str, Any]) -> str:
    knowledge = stats["knowledge"]
    records = knowledge["records"]
    active = records["by_status"].get("active", 0)
    draft = records["by_status"].get("draft", 0)
    invalid = records["by_status"].get("invalid", 0)
    cards = [
        ("Organizations", stats["organizations"]["count"]),
        ("Libraries", stats["libraries"]["count"]),
        ("Users", stats["users"]["count"]),
        ("Cases", knowledge["cases"]),
        ("Records", records["total"]),
        ("Active", active),
        ("Draft", draft),
        ("Invalid", invalid),
    ]
    parts = ['<div class="stats-grid">']
    for label, value in cards:
        parts.append(
            f'<div class="stat-card"><div class="stat-value">{_esc(value)}</div><div class="stat-label">{_esc(label)}</div></div>'
        )
    parts.append("</div>")
    return "\n".join(parts)


def _render_table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{_esc(cell)}</td>" for cell in row)
        body_rows.append(f"<tr>{cells}</tr>")
    if not body_rows:
        body_rows.append(f'<tr><td colspan="{len(headers)}" class="muted">暂无数据</td></tr>')
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def _render_observatory_page(base: str, stats: dict[str, Any], user_line: str, *, show_logout: bool) -> str:
    org_rows = [[o["id"], o["name"]] for o in stats["organizations"]["items"]]
    lib_rows = [
        [
            lib["id"],
            lib["name"],
            lib["org_name"],
            lib["visibility"],
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

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>ma3 Observatory</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; line-height: 1.5; color: #18181b; }}
    .banner {{ background: #f4f4f5; padding: 0.75rem 1rem; border-radius: 8px; margin-bottom: 1.5rem; }}
    h1, h2 {{ margin-top: 2rem; }}
    h1 {{ margin-top: 0; }}
    .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 0.75rem; margin: 1rem 0 2rem; }}
    .stat-card {{ background: #fafafa; border: 1px solid #e4e4e7; border-radius: 8px; padding: 1rem; text-align: center; }}
    .stat-value {{ font-size: 1.75rem; font-weight: 700; }}
    .stat-label {{ font-size: 0.85rem; color: #71717a; margin-top: 0.25rem; }}
    table {{ border-collapse: collapse; width: 100%; margin: 0.75rem 0 1.5rem; }}
    th, td {{ border: 1px solid #e4e4e7; padding: 0.5rem 0.75rem; text-align: left; }}
    th {{ background: #f4f4f5; }}
    .muted {{ color: #71717a; }}
    .note {{ background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 0.75rem 1rem; margin: 1rem 0; }}
    a {{ color: #2563eb; }}
    .feedback {{ display: flex; gap: 0.75rem; align-items: center; margin: 1rem 0; }}
    .feedback form {{ display: inline; }}
    .feedback button {{
      font-size: 1.1rem; padding: 0.35rem 0.75rem; border-radius: 8px;
      border: 1px solid #d4d4d8; background: #fff; cursor: pointer;
    }}
    .feedback button.active {{ border-color: #2563eb; background: #eff6ff; }}
    pre {{ background: #fafafa; border: 1px solid #e4e4e7; padding: 1rem; overflow-x: auto; }}
  </style>
</head>
<body>
  <div class="banner">
    <strong>ma3</strong> v{_esc(settings.service_version)} · {_esc(settings.instance_id or "local")} · {_esc(settings.git_commit or "dev")}
    · 数据库 {_esc("postgresql" if is_postgres() else "sqlite")}
  </div>
  <h1>Observatory</h1>
  <p>系统概览：组织、知识库、用户与知识条目统计（只读）。</p>
  <p class="muted">{_esc(user_line)}</p>
  <p class="muted">
    <a href="{_esc(base)}/ui/observatory/stats.json">stats.json</a>
    · <a href="{_esc(base)}/healthz">healthz</a>
    · <a href="{_esc(base)}/mcp/info">MCP info</a>
    · <a href="{_esc(base)}/client/manifest.json">client manifest</a>
    {('· <a href="' + _esc(base) + '/auth/account">账户设置 / 修改密码</a> · <a href="' + _esc(base) + '/auth/logout">退出登录</a>') if show_logout else ''}
  </p>

  <h2>总览</h2>
  {_render_stat_cards(stats)}

  <h2>Organizations ({_esc(stats["organizations"]["count"])})</h2>
  {_render_table(["ID", "名称"], org_rows)}

  <h2>Libraries ({_esc(stats["libraries"]["count"])})</h2>
  {_render_table(
      ["ID", "名称", "Organization", "可见性", "Cases", "Records", "Active", "Draft", "Invalid"],
      lib_rows,
  )}

  <h2>Users ({_esc(stats["users"]["count"])})</h2>
  <div class="note">{_esc(stats["users"]["note"])}</div>
  {_render_table(["ID", "类型", "显示名", "创建时间"], user_rows)}

  <h2>知识分布</h2>
  <h3>按 outcome</h3>
  {_render_table(["Outcome", "数量"], outcome_rows)}
  <h3>按 task_type</h3>
  {_render_table(["Task type", "数量"], task_rows)}
</body>
</html>"""


@router.get("/stats.json")
def observatory_stats_json(request: Request) -> JSONResponse:
    if settings.authing_configured and resolve_session_user(request) is None:
        return JSONResponse({"detail": "authentication required"}, status_code=401)
    return JSONResponse(get_system_stats())


def _observatory_user_line(request: Request) -> tuple[str | None, str]:
    if not settings.authing_configured:
        return None, "未启用 Authing；Observatory 为开放只读（LAN dev）。"
    user = resolve_session_user(request)
    if user is None:
        return None, ""
    admin = " · 管理员" if user.is_admin else ""
    return user, f"已登录：{user.display_name}{admin}"


def _require_observatory_session(request: Request) -> Response | None:
    if settings.authing_configured and resolve_session_user(request) is None:
        return RedirectResponse(f"/auth/login?next={request.url.path}", status_code=302)
    return None


def _render_record_page(
    base: str,
    record: dict[str, Any],
    feedback: dict[str, Any],
    user_line: str,
    *,
    show_logout: bool,
) -> str:
    my_vote = feedback.get("my_vote")
    up_active = my_vote == "up"
    down_active = my_vote == "down"
    feedback_action = f"{base}/ui/observatory/records/{_esc(record['id'])}/feedback"
    btn = lambda label, vote, active: (
        f'<form method="post" action="{feedback_action}?vote={_esc(vote)}">'
        f'<button type="submit" class="{"active" if active else ""}">{label}</button></form>'
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>Record {_esc(record["id"])} · ma3</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; line-height: 1.5; color: #18181b; }}
    .banner {{ background: #f4f4f5; padding: 0.75rem 1rem; border-radius: 8px; margin-bottom: 1.5rem; }}
    .muted {{ color: #71717a; }}
    a {{ color: #2563eb; }}
    .feedback {{ display: flex; gap: 0.75rem; align-items: center; margin: 1.25rem 0; }}
    .feedback form {{ display: inline; }}
    .feedback button {{
      font-size: 1.1rem; padding: 0.35rem 0.75rem; border-radius: 8px;
      border: 1px solid #d4d4d8; background: #fff; cursor: pointer;
    }}
    .feedback button.active {{ border-color: #2563eb; background: #eff6ff; }}
    dl {{ display: grid; grid-template-columns: 8rem 1fr; gap: 0.5rem 1rem; }}
    dt {{ color: #71717a; }}
  </style>
</head>
<body>
  <div class="banner">
    <strong>ma3</strong> Observatory · <a href="{_esc(base)}/ui/observatory/">返回概览</a>
  </div>
  <h1>知识条目</h1>
  <p class="muted">{_esc(user_line)}</p>
  <p class="muted">
    {('· <a href="' + _esc(base) + '/auth/logout">退出登录</a>') if show_logout else ''}
  </p>
  <dl>
    <dt>ID</dt><dd><code>{_esc(record["id"])}</code></dd>
    <dt>Library</dt><dd>{_esc(record.get("library_id", ""))}</dd>
    <dt>Case</dt><dd>{_esc(record.get("case_id") or "—")}</dd>
    <dt>Status</dt><dd>{_esc(record.get("status", ""))}</dd>
    <dt>Outcome</dt><dd>{_esc(record.get("outcome", ""))}</dd>
    <dt>Created</dt><dd>{_esc(record.get("created_at", ""))}</dd>
  </dl>
  <h2>Problem</h2>
  <p>{_esc(record.get("problem", ""))}</p>
  <h2>Summary</h2>
  <p>{_esc(record.get("result_summary", ""))}</p>
  <h2>Feedback</h2>
  <div class="feedback">
    {btn(f"👍 {_esc(feedback.get('up', 0))}", "up", up_active)}
    {btn(f"👎 {_esc(feedback.get('down', 0))}", "down", down_active)}
    {btn("清除我的投票", "clear", False)}
  </div>
  <p class="muted">同一用户对同一 record 只能保留一票，可改投或清除。</p>
</body>
</html>"""


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def observatory_home(request: Request) -> Response:
    user, user_line = _observatory_user_line(request)
    if settings.authing_configured and user is None:
        return RedirectResponse(f"/auth/login?next={request.url.path}", status_code=302)
    base = str(request.base_url).rstrip("/")
    stats = get_system_stats()
    html = _render_observatory_page(base, stats, user_line, show_logout=settings.authing_configured)
    response = HTMLResponse(html)
    if not settings.authing_configured and not request.cookies.get("ma3_ui_session"):
        response.set_cookie("ma3_ui_session", uuid.uuid4().hex, httponly=True, samesite="lax", max_age=86400 * 30)
    return response


@router.get("/records/{record_id}", response_class=HTMLResponse)
def observatory_record(request: Request, record_id: str) -> Response:
    redirect = _require_observatory_session(request)
    if redirect is not None:
        return redirect
    record = get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="record not found")
    if record.get("library_id") != settings.default_library_id:
        raise HTTPException(status_code=404, detail="record not found")
    if record.get("status") != "active":
        raise HTTPException(status_code=404, detail="record not found")
    display = format_record_for_read(record, include_full_json=False)
    _, user_line = _observatory_user_line(request)
    try:
        principal_id = resolve_ui_feedback_principal(request)
        feedback = get_feedback_summaries([record_id], principal_id=principal_id)[record_id]
    except HTTPException:
        feedback = get_feedback_summaries([record_id])[record_id]
    base = str(request.base_url).rstrip("/")
    return _render_record_page(base, display, feedback, user_line, show_logout=settings.authing_configured)


@router.post("/records/{record_id}/feedback")
def observatory_record_feedback(
    request: Request,
    record_id: str,
    vote: str = Query(...),
) -> Response:
    redirect = _require_observatory_session(request)
    if redirect is not None:
        return redirect
    if vote not in {"up", "down", "clear"}:
        raise HTTPException(status_code=400, detail="vote must be up, down, or clear")
    principal_id = resolve_ui_feedback_principal(request)
    apply_record_feedback(
        record_id=record_id,
        principal_id=principal_id,
        vote=vote,  # type: ignore[arg-type]
        readable_library_ids={settings.default_library_id},
    )
    return RedirectResponse(f"/ui/observatory/records/{record_id}", status_code=303)
