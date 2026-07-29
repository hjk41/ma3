"""Prometheus metrics for ma3 (Phase 1).

Cardinality policy (ratified): aggregate labels only — no principal / org / library ids.
When ``settings.metrics_enabled`` is False, recording helpers are no-ops and ``/metrics``
is not mounted as a live endpoint (404).
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Dedicated registry so tests can isolate and multiprocess mode stays optional later.
REGISTRY = CollectorRegistry(auto_describe=True)

_HTTP_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_MCP_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)

HTTP_REQUESTS = Counter(
    "ma3_http_requests_total",
    "HTTP requests by method, route template, and status class",
    ["method", "route", "status"],
    registry=REGISTRY,
)
HTTP_DURATION = Histogram(
    "ma3_http_request_duration_seconds",
    "HTTP request latency by method and route template",
    ["method", "route"],
    buckets=_HTTP_BUCKETS,
    registry=REGISTRY,
)
HTTP_IN_FLIGHT = Gauge(
    "ma3_http_requests_in_flight",
    "In-flight HTTP requests",
    registry=REGISTRY,
)
BUILD_INFO = Gauge(
    "ma3_build_info",
    "Build / instance metadata (value always 1)",
    ["version", "git_commit", "instance_id"],
    registry=REGISTRY,
)
MCP_TOOL_CALLS = Counter(
    "ma3_mcp_tool_calls_total",
    "MCP tool calls by tool name and outcome",
    ["tool", "outcome"],
    registry=REGISTRY,
)
MCP_TOOL_DURATION = Histogram(
    "ma3_mcp_tool_duration_seconds",
    "MCP tool call latency by tool name",
    ["tool"],
    buckets=_MCP_BUCKETS,
    registry=REGISTRY,
)

_build_info_set = False


def metrics_enabled() -> bool:
    from app.core.config import settings

    return bool(settings.metrics_enabled)


def ensure_build_info() -> None:
    """Set ma3_build_info once per process from current settings."""
    global _build_info_set
    if _build_info_set or not metrics_enabled():
        return
    from app.core.config import settings

    BUILD_INFO.labels(
        version=settings.service_version or "unknown",
        git_commit=(settings.git_commit or "unknown")[:40],
        instance_id=settings.instance_id or "unknown",
    ).set(1)
    _build_info_set = True


def status_class(status_code: int) -> str:
    if status_code < 200:
        return "1xx"
    if status_code < 300:
        return "2xx"
    if status_code < 400:
        return "3xx"
    if status_code < 500:
        return "4xx"
    return "5xx"


def route_template(request) -> str:
    """Prefer FastAPI route path template; never use raw URL paths (cardinality)."""
    route = request.scope.get("route")
    path = getattr(route, "path", None) if route is not None else None
    if isinstance(path, str) and path:
        return path
    return "unmatched"


def observe_http(*, method: str, route: str, status_code: int, duration_sec: float) -> None:
    if not metrics_enabled():
        return
    ensure_build_info()
    m = (method or "GET").upper()
    r = route or "unmatched"
    HTTP_REQUESTS.labels(method=m, route=r, status=status_class(status_code)).inc()
    HTTP_DURATION.labels(method=m, route=r).observe(max(duration_sec, 0.0))


def observe_mcp_tool(*, tool: str, outcome: str, duration_sec: float) -> None:
    if not metrics_enabled():
        return
    ensure_build_info()
    t = tool or "unknown"
    o = outcome or "error"
    MCP_TOOL_CALLS.labels(tool=t, outcome=o).inc()
    MCP_TOOL_DURATION.labels(tool=t).observe(max(duration_sec, 0.0))


@contextmanager
def track_in_flight() -> Iterator[None]:
    if not metrics_enabled():
        yield
        return
    HTTP_IN_FLIGHT.inc()
    try:
        yield
    finally:
        HTTP_IN_FLIGHT.dec()


def render_latest() -> tuple[bytes, str]:
    ensure_build_info()
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


def outcome_from_http_status(status_code: int) -> str:
    if status_code in (401, 403):
        return "auth_denied"
    if status_code == 429:
        return "quota_blocked"
    if 400 <= status_code < 500:
        return "invalid_args"
    return "error"


class Timer:
    __slots__ = ("_start",)

    def __init__(self) -> None:
        self._start = time.perf_counter()

    def seconds(self) -> float:
        return time.perf_counter() - self._start
