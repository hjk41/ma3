"""HTTP metrics middleware (Phase 1)."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core import metrics as metrics_mod
from app.core.config import settings


class PrometheusHTTPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.metrics_enabled:
            return await call_next(request)
        # Do not recurse on the scrape endpoint itself for duration histograms of /metrics
        # (still counted lightly via in-flight only if desired — skip entirely for simplicity).
        if request.url.path == "/metrics":
            return await call_next(request)

        timer = metrics_mod.Timer()
        with metrics_mod.track_in_flight():
            try:
                response = await call_next(request)
            except Exception:
                route = metrics_mod.route_template(request)
                metrics_mod.observe_http(
                    method=request.method,
                    route=route,
                    status_code=500,
                    duration_sec=timer.seconds(),
                )
                raise
        route = metrics_mod.route_template(request)
        metrics_mod.observe_http(
            method=request.method,
            route=route,
            status_code=response.status_code,
            duration_sec=timer.seconds(),
        )
        return response
