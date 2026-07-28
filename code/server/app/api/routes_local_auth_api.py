"""JSON APIs for local auth register/login (agent day-0)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.services import local_auth_service

router = APIRouter(prefix="/api/auth", tags=["local-auth-api"])


class ApiKeyRequest(BaseModel):
    label: str = Field(min_length=1, max_length=120)


class RegisterBody(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=8, max_length=200)
    display_name: str | None = Field(default=None, max_length=32)
    api_key: ApiKeyRequest | None = None
    invite: str | None = Field(default=None, max_length=200)


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=200)
    api_key: ApiKeyRequest


def _require_local_auth() -> None:
    if not settings.local_auth_enabled:
        raise HTTPException(status_code=503, detail="local auth is not enabled")


@router.post("/register")
def api_register(body: RegisterBody) -> JSONResponse:
    _require_local_auth()
    try:
        result = local_auth_service.register_local_user_api(
            username=body.username,
            password=body.password,
            display_name=body.display_name,
            api_key_label=body.api_key.label if body.api_key else None,
            invite_token=body.invite,
        )
    except HTTPException:
        raise
    return JSONResponse(result, status_code=201)


@router.post("/login")
def api_login(body: LoginBody) -> JSONResponse:
    _require_local_auth()
    result = local_auth_service.login_local_user_api(
        username=body.username,
        password=body.password,
        api_key_label=body.api_key.label,
    )
    return JSONResponse(result)
