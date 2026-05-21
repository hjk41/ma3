from __future__ import annotations

from html import escape
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.core.config import settings

router = APIRouter(tags=["ui"])

_SHELL_CSS = """
<style id="ma3-shell-css">
.deploy-banner {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem 0.75rem;
  padding: 0.45rem 0.75rem;
  background: #0f172a;
  color: #cbd5e1;
  border-bottom: 1px solid #1e293b;
  font: 12px/1.4 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.dep-cell { display: inline-flex; align-items: baseline; gap: 0.25rem; min-width: 0; }
.dep-label { color: #94a3b8; text-transform: uppercase; letter-spacing: 0.04em; font-size: 10px; }
.dep-value {
  color: #e2e8f0;
  background: rgba(148, 163, 184, 0.12);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 0.25rem;
  padding: 0.05rem 0.25rem;
  max-width: 32rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sr-only {
  position: absolute !important;
  width: 1px !important;
  height: 1px !important;
  padding: 0 !important;
  margin: -1px !important;
  overflow: hidden !important;
  clip: rect(0, 0, 0, 0) !important;
  white-space: nowrap !important;
  border: 0 !important;
}
</style>
"""


def _deploy_banner_html() -> str:
    def cell(label: str, value: str | None) -> str:
        shown = escape(value) if value else "—"
        return f'<span class="dep-cell"><span class="dep-label">{escape(label)}</span><code class="dep-value">{shown}</code></span>'

    return (
        '<div class="deploy-banner">'
        + cell("instance", settings.instance_id)
        + cell("commit", (settings.git_commit or "")[:12] or None)
        + cell("deployed", settings.started_at)
        + cell("job", settings.job_name)
        + cell("base url", settings.public_base_url)
        + "</div>"
    )


def _spa_html() -> str:
    index = Path(__file__).resolve().parents[1] / "web" / "dist" / "index.html"
    if index.exists():
        html = index.read_text(encoding="utf-8")
    else:
        html = '<!doctype html><html><head><title>ma3</title></head><body><div id="root"></div></body></html>'
    if 'id="ma3-shell-css"' not in html:
        html = html.replace("</head>", _SHELL_CSS + "</head>", 1)
    return html.replace(
        '<div id="root">',
        _deploy_banner_html()
        + '<h1 class="sr-only">ma3 Knowledge Network</h1>'
        + '<div id="root">',
        1,
    )


@router.get("/", response_class=HTMLResponse)
@router.get("/me", response_class=HTMLResponse)
@router.get("/libs", response_class=HTMLResponse)
@router.get("/libs/{library_id}", response_class=HTMLResponse)
@router.get("/keys", response_class=HTMLResponse)
@router.get("/admin", response_class=HTMLResponse)
@router.get("/observatory", response_class=HTMLResponse)
def ui_spa_entry(library_id: str | None = None) -> str:
    return _spa_html()
