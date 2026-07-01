from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.core.config import settings

router = APIRouter(prefix="/ui/observatory", tags=["observatory"])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def observatory_home(request: Request) -> str:
    base = str(request.base_url).rstrip("/")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>ma3 Observatory</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
    .banner {{ background: #f4f4f5; padding: 0.75rem 1rem; border-radius: 8px; margin-bottom: 1.5rem; }}
  </style>
</head>
<body>
  <div class="banner">
    <strong>ma3</strong> v{settings.service_version} · {settings.instance_id or "local"} · {settings.git_commit or "dev"}
  </div>
  <h1>Observatory</h1>
  <p>只读浏览 + 人 — 维护者治理（v1 骨架）。</p>
  <ul>
    <li><a href="{base}/healthz">healthz</a></li>
    <li><a href="{base}/mcp/info">MCP info</a></li>
    <li><a href="{base}/client/manifest.json">client manifest</a></li>
  </ul>
</body>
</html>"""
