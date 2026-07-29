"""GET /metrics — Prometheus scrape endpoint (Phase 1).

Enabled only when ``MA3_METRICS_ENABLED=1``. Self-host defaults to off (decision A).
SaaS should enable on the loopback listener and not proxy this path via Caddy.
"""
from __future__ import annotations

from fastapi import APIRouter, Response
from fastapi.responses import PlainTextResponse

from app.core import metrics as metrics_mod
from app.core.config import settings

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def prometheus_metrics() -> Response:
    if not settings.metrics_enabled:
        return PlainTextResponse("metrics disabled\n", status_code=404)
    body, content_type = metrics_mod.render_latest()
    return Response(content=body, media_type=content_type)
