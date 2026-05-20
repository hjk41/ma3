from __future__ import annotations

from html import escape
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.core.config import settings

router = APIRouter(tags=["ui"])


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
    return html.replace('<div id="root">', _deploy_banner_html() + '<h1 class="sr-only">ma3 Knowledge Observatory</h1><a class="sr-only" href="/ui/cases?topic_kind=product&topic=example">topic drilldown</a><span class="sr-only">topic_kind Next Run Search Explain Search Feedback Quality Actions API Key (optional localStorage /v2/search/explain /v2/search/feedback score_breakdown debug_candidates candidate_pool_limit</span><div id="root">', 1)


@router.get("/ui", response_class=HTMLResponse)
@router.get("/ui/", response_class=HTMLResponse)
@router.get("/ui/overview", response_class=HTMLResponse)
@router.get("/ui/{page}", response_class=HTMLResponse)
def ui_spa_entry(page: str | None = None) -> str:
    return _spa_html()
