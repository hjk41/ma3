from fastapi import APIRouter

from app.core.config import settings


router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.service_version,
        "skill_bundle_version": settings.skill_version,
        "api_version": settings.api_version,
        "min_client_version": settings.min_client_version,
        "recommended_client_version": settings.recommended_client_version,
        "features": list(settings.feature_flags),
        "public_base_url": settings.public_base_url,
        "instance_id": settings.instance_id,
        "git_commit": settings.git_commit,
        "job_name": settings.job_name,
        "deployed_at": settings.started_at,
        "client_manifest_url": "/client/manifest.json",
    }
