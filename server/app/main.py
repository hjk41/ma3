import threading

from fastapi import FastAPI

from app.api.routes_agent import router as agent_router
from app.api.routes_docs import router as docs_router
from app.api.routes_feedback import router as feedback_router
from app.api.routes_health import router as health_router
from app.api.routes_knowledge import router as knowledge_router
from app.api.routes_libraries import router as libraries_router, invites_router
from app.api.routes_relations import router as relations_router
from app.api.routes_records import router as records_router
from app.api.routes_search import router as search_router
from app.storage.db import initialize_database, backfill_search_indexes


app = FastAPI(
    title="马妈妈 (ma3)",
    description="The verified knowledge network for agents.",
    version="0.4.0",
)


@app.on_event("startup")
def on_startup() -> None:
    # Schema creation and seeding are fast — run synchronously.
    initialize_database(run_backfill=False)
    # Embedding backfill may download/load the sentence-transformer model on
    # first run (hundreds of MB, slow behind a firewall).  Run it in a daemon
    # thread so the HTTP server becomes available immediately.
    t = threading.Thread(target=backfill_search_indexes, daemon=True, name="backfill")
    t.start()


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
