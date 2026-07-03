import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes_auth import router as auth_router
from app.api.routes_client import router as client_router
from app.api.routes_health import router as health_router
from app.api.routes_mcp import router as mcp_router
from app.api.routes_ui import router as ui_router
from app.core.config import settings
from app.storage.db import initialize_database


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize_database()
    if not settings.disable_embeddings:
        from app.services.embedding_service import warm_up_model

        warm_up_model()
    yield


app = FastAPI(
    title="马妈妈 (ma3)",
    description="Cross-agent verified knowledge network",
    version=settings.service_version,
    lifespan=lifespan,
)


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(mcp_router)
app.include_router(client_router)
app.include_router(ui_router)
