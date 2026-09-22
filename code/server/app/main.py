import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.routes_portal import router as portal_router
from app.api.routes_org_portal import router as org_portal_router
from app.api.routes_billing import router as billing_router
from app.api.routes_stripe_webhook import router as stripe_webhook_router
from app.api.routes_auth import router as auth_router
from app.api.routes_client import router as client_router
from app.api.routes_health import router as health_router
from app.api.routes_metrics import router as metrics_router
from app.api.metrics_middleware import PrometheusHTTPMiddleware
from app.api.routes_keys import router as keys_router
from app.api.routes_mcp import router as mcp_router
from app.api.routes_mcp_oauth import router as mcp_oauth_router
from app.api.routes_ui import router as ui_router
from app.api.routes_observatory_ops import router as observatory_ops_router
from app.api.routes_setup import router as setup_router
from app.api.routes_local_auth_api import router as local_auth_api_router
from app.api.routes_setup_api import router as setup_api_router
from app.api.routes_local_users_api import router as local_users_api_router
from app.api.routes_me_api import router as me_api_router
from app.api.routes_orgs_api import router as orgs_api_router
from app.api.routes_libraries_api import router as libraries_api_router
from app.api.routes_admin_api import router as admin_api_router
from app.api.routes_org_invites_api import router as org_invites_api_router
from app.api.setup_gate import NeedsOwnerSetupRedirectMiddleware
from app.core.config import settings
from app.services.portal_service import validate_authing_admin_config
from app.storage.db import initialize_database

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


async def _billing_maintenance_loop() -> None:
    """Flush usage_events often; run past_due grace on a slower cadence (D9)."""
    from app.services import usage_service
    from app.services.billing_jobs import run_billing_maintenance_once

    flush_every = max(5, int(settings.usage_flush_interval_sec))
    grace_every = max(flush_every, int(settings.billing_grace_interval_sec))
    until_grace = 0  # run full maintenance on the first tick
    while True:
        try:
            if until_grace <= 0:
                run_billing_maintenance_once()
                until_grace = grace_every
            else:
                usage_service.flush_usage_events()
        except Exception:
            logger.exception("billing maintenance loop failed")
        await asyncio.sleep(flush_every)
        until_grace -= flush_every


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_authing_admin_config()
    if settings.dev_auth and settings.oidc_configured:
        public = (settings.public_base_url or "").lower()
        if public.startswith("https://") and "localhost" not in public and "127.0.0.1" not in public:
            logger.warning(
                "MA3_DEV_AUTH=1 with OIDC on a public URL (%s) — disable MA3_DEV_AUTH for production",
                settings.public_base_url,
            )
    initialize_database()
    from app.storage import db

    if not settings.oidc_configured and settings.bootstrap_selfhost:
        from app.services.bootstrap_selfhost import ensure_bootstrap_key

        ensure_bootstrap_key()

    db.publish_due_buffered_records()
    buffer_task = asyncio.create_task(_buffer_publish_loop())
    billing_task = asyncio.create_task(_billing_maintenance_loop())
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
    indexed = db.backfill_buffered_search_indexes()
    if indexed:
        logger.info("backfilled private search indexes for %d buffered record(s)", indexed)
    try:
        yield
    finally:
        buffer_task.cancel()
        billing_task.cancel()
        with suppress(asyncio.CancelledError):
            await buffer_task
        with suppress(asyncio.CancelledError):
            await billing_task


app = FastAPI(
    title="马妈妈 (ma3)",
    description="Cross-agent verified knowledge network",
    version=settings.service_version,
    lifespan=lifespan,
)

app.add_middleware(NeedsOwnerSetupRedirectMiddleware)
app.add_middleware(PrometheusHTTPMiddleware)

app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(auth_router)
app.include_router(setup_router)
app.include_router(local_auth_api_router)
app.include_router(setup_api_router)
app.include_router(local_users_api_router)
app.include_router(billing_router)
app.include_router(stripe_webhook_router)
app.include_router(me_api_router)
app.include_router(orgs_api_router)
app.include_router(libraries_api_router)
app.include_router(admin_api_router)
app.include_router(org_invites_api_router)
app.include_router(portal_router)
app.include_router(org_portal_router)
app.include_router(keys_router)
app.include_router(mcp_oauth_router)
app.include_router(mcp_router)
app.include_router(client_router)
app.include_router(ui_router)
app.include_router(observatory_ops_router)
