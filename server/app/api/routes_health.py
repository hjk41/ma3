from fastapi import APIRouter

from app.core.config import settings


router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str | list[str]]:
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.service_version,
        "min_client_version": settings.min_client_version,
        "features": list(settings.feature_flags),
    }
