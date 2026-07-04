import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.routes_portal import router as portal_router
from app.api.routes_auth import router as auth_router
from app.api.routes_client import router as client_router
from app.api.routes_health import router as health_router
from app.api.routes_keys import router as keys_router
from app.api.routes_mcp import router as mcp_router
from app.api.routes_ui import router as ui_router
from app.core.config import settings
from app.services.portal_service import validate_authing_admin_config
from app.storage.db import initialize_database
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)

_BUFFER_PUBLISH_INTERVAL_SEC = 60


async def _buffer_publish_loop() -> None:
    from app.storage import db

    while True:
        try:
            published = db.publish_due_buffered_records()
            if published:
                logger.info("auto-published %d buffered record(s)", published)
        except Exception:
            logger.exception("publish_due_buffered_records failed")
        await asyncio.sleep(_BUFFER_PUBLISH_INTERVAL_SEC)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_authing_admin_config()
    initialize_database()
    from app.storage import db

    db.publish_due_buffered_records()
    buffer_task = asyncio.create_task(_buffer_publish_loop())
    if not settings.disable_embeddings:
        from app.services.embedding_service import warm_up_model

        logger.info(
            "loading embedding model %s (HF_HOME=%s)",
            settings.embedding_model,
            os.environ.get("HF_HOME", ""),
        )
        started = time.perf_counter()
        warm_up_model(required=True)
        logger.info("embedding model ready in %.1fs", time.perf_counter() - started)
    try:
        yield
    finally:
        buffer_task.cancel()
        with suppress(asyncio.CancelledError):
            await buffer_task


app = FastAPI(
    title="马妈妈 (ma3)",
    description="Cross-agent verified knowledge network",
    version=settings.service_version,
    lifespan=lifespan,
)


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(portal_router)
app.include_router(keys_router)
app.include_router(mcp_router)
app.include_router(client_router)
app.include_router(ui_router)


@app.get("/")
@app.get("/ui")
@app.get("/ui/")
def root_redirect() -> RedirectResponse:
    return RedirectResponse("/ui/me/", status_code=302)
