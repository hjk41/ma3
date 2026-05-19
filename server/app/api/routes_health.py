from fastapi import APIRouter

from app.core.config import settings


router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str | list[str] | None]:
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.service_version,
        "min_client_version": settings.min_client_version,
        "recommended_client_version": settings.recommended_client_version,
        "client_manifest_url": "/client/manifest.json",
        "features": list(settings.feature_flags),
        "public_base_url": settings.public_base_url,
        "instance_id": settings.instance_id,
        "git_commit": settings.git_commit,
        "job_name": settings.job_name,
        "deployed_at": settings.started_at,
        "auth_mode": "v3",
    }
