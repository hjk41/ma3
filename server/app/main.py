import threading
import time
from uuid import uuid4

from fastapi import FastAPI, Request

from app.api.routes_agent import router as agent_router
from app.api.routes_docs import router as docs_router
from app.api.routes_feedback import router as feedback_router
from app.api.routes_health import router as health_router
from app.api.routes_knowledge import router as knowledge_router
from app.api.routes_libraries import router as libraries_router, invites_router
from app.api.routes_relations import router as relations_router
from app.api.routes_records import router as records_router
from app.api.routes_search import router as search_router
from app.api.routes_ui import router as ui_router
from app.api.routes_v2_agent import router as v2_agent_router, search_router as v2_search_router
from app.api.routes_v2_cases import router as v2_cases_router
from app.api.routes_v2_stats import router as v2_stats_router, metrics_router
from app.services.metrics_service import metrics
from app.services.op_log_service import write_op_log
from app.storage.db import initialize_database, backfill_search_indexes


app = FastAPI(
    title="马妈妈 (ma3)",
    description="The verified knowledge network for agents.",
    version="0.4.0",
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    started = time.perf_counter()
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    response = await call_next(request)
    duration = time.perf_counter() - started
    response.headers["X-Request-ID"] = request_id
    metrics.record_http(request.method, request.url.path, response.status_code, duration)
    write_op_log(
        "http_request",
        request_id=request_id,
        method=request.method,
        route=request.url.path,
        status=response.status_code,
        latency_ms=round(duration * 1000, 3),
        query=str(request.url.query)[:500] if request.url.query else None,
    )
    return response


@app.on_event("startup")
def on_startup() -> None:
    # Schema creation and seeding are fast — run synchronously.
    initialize_database(run_backfill=False)
    # Embedding backfill may download/load the sentence-transformer model on
    # first run (hundreds of MB, slow behind a firewall).  Run it in a daemon
    # thread so the HTTP server becomes available immediately.
    t = threading.Thread(target=backfill_search_indexes, daemon=True, name="backfill")
    t.start()
    write_op_log("startup", status="ok")


app.include_router(health_router)
app.include_router(docs_router)
app.include_router(libraries_router)
app.include_router(invites_router)
app.include_router(agent_router)
app.include_router(knowledge_router)
app.include_router(records_router)
app.include_router(feedback_router)
app.include_router(relations_router)
app.include_router(search_router)
app.include_router(ui_router)
app.include_router(v2_agent_router)
app.include_router(v2_search_router)
app.include_router(v2_cases_router)
app.include_router(v2_stats_router)
app.include_router(metrics_router)
