from __future__ import annotations

import html
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.core.config import settings
from app.storage.db import get_system_stats, is_postgres

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


def _render_observatory_page(base: str, stats: dict[str, Any]) -> str:
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
  </style>
</head>
<body>
  <div class="banner">
    <strong>ma3</strong> v{_esc(settings.service_version)} · {_esc(settings.instance_id or "local")} · {_esc(settings.git_commit or "dev")}
    · 数据库 {_esc("postgresql" if is_postgres() else "sqlite")}
  </div>
  <h1>Observatory</h1>
  <p>系统概览：组织、知识库、用户与知识条目统计（只读）。</p>
  <p class="muted">
    <a href="{_esc(base)}/ui/observatory/stats.json">stats.json</a>
    · <a href="{_esc(base)}/healthz">healthz</a>
    · <a href="{_esc(base)}/mcp/info">MCP info</a>
    · <a href="{_esc(base)}/client/manifest.json">client manifest</a>
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
def observatory_stats_json() -> JSONResponse:
    return JSONResponse(get_system_stats())


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def observatory_home(request: Request) -> str:
    base = str(request.base_url).rstrip("/")
    stats = get_system_stats()
    return _render_observatory_page(base, stats)
