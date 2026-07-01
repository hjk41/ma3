import asyncio
import threading
import time
from uuid import uuid4

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.api.routes_auth import router as auth_router
from app.api.routes_agent import router as agent_router
from app.api.routes_docs import router as docs_router
from app.api.routes_feedback import router as feedback_router
from app.api.routes_health import router as health_router
from app.api.routes_knowledge import router as knowledge_router
from app.api.routes_libraries import router as libraries_router, invites_router
from app.api.routes_mcp import router as mcp_router
from app.api.routes_relations import router as relations_router
from app.api.routes_records import router as records_router
from app.api.routes_search import router as search_router
from app.api.routes_ui import router as ui_router
from app.api.routes_v3_auth import router as v3_auth_router
from app.api.routes_v2_agent import router as v2_agent_router, search_router as v2_search_router
from app.api.routes_v2_cases import router as v2_cases_router
from app.api.routes_v2_stats import router as v2_stats_router, metrics_router
from app.api.routes_v4 import router as v4_router
from app.core.config import settings
from app.services.metrics_service import metrics
from app.services.op_log_service import write_op_log
from app.storage.db import initialize_database, backfill_search_indexes, close_postgres_pool


app = FastAPI(
    title="马妈妈 (ma3)",
    description="The verified knowledge network for agents.",
    version="4.0.0",
)


_PROBE_PATHS = frozenset({"/healthz"})


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    started = time.perf_counter()
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    response = await call_next(request)
    duration = time.perf_counter() - started
    response.headers["X-Request-ID"] = request_id
    path = request.url.path
    if path not in _PROBE_PATHS:
        metrics.record_http(request.method, path, response.status_code, duration)
        await asyncio.to_thread(
            write_op_log,
            "http_request",
            request_id=request_id,
            method=request.method,
            route=path,
            status=response.status_code,
            latency_ms=round(duration * 1000, 3),
            query=str(request.url.query)[:500] if request.url.query else None,
        )
    return response


def _background_search_backfill() -> None:
    backfill_search_indexes()


@app.on_event("startup")
def on_startup() -> None:
    # Schema creation and seeding are fast — run synchronously.
    initialize_database(run_backfill=False)
    # Embedding backfill loads/downloads the model then indexes records. Keep it
    # off the request path so /healthz stays responsive during first boot.
    t = threading.Thread(target=_background_search_backfill, daemon=True, name="backfill")
    t.start()
    write_op_log("startup", status="ok")


@app.on_event("shutdown")
def on_shutdown() -> None:
    close_postgres_pool()
    write_op_log("shutdown", status="ok")


app.include_router(health_router)
app.include_router(docs_router)
app.include_router(mcp_router)
app.include_router(v2_agent_router)
app.include_router(v2_search_router)
app.include_router(v2_cases_router)
app.include_router(v2_stats_router)
app.include_router(metrics_router)
app.include_router(records_router)
app.include_router(feedback_router)
app.include_router(relations_router)
app.include_router(search_router)
app.include_router(knowledge_router)
app.include_router(ui_router)

if settings.api_version == "v4":
    app.include_router(v4_router)
else:
    app.include_router(libraries_router)
    app.include_router(invites_router)
    app.include_router(agent_router)
    app.include_router(auth_router)
    app.include_router(v3_auth_router)


_web_dist = Path(__file__).resolve().parent / "web" / "dist"
app.mount("/assets", StaticFiles(directory=str(_web_dist / "assets"), check_dir=False), name="ui-assets")
