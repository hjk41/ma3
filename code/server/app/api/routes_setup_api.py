"""JSON APIs for self-host first-run setup."""
from __future__ import annotations

from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.services import setup_service
from app.services.local_admin_service import (
    LocalActor,
    assert_mutating_auth,
    require_local_admin_actor,
)
from app.services.local_auth_service import is_registration_open
from app.storage import db

router = APIRouter(prefix="/api/setup", tags=["setup-api"])


class RegistrationBody(BaseModel):
    open: bool


def _require_local_auth() -> None:
    if not settings.local_auth_enabled:
        raise HTTPException(status_code=503, detail="local auth is not enabled")


def _registration_payload() -> dict:
    return {
        "registration_open": is_registration_open(),
        "registration_ack": db.get_instance_setting(setup_service.SETTING_REGISTRATION_ACK),
        "registration_handled": setup_service.registration_policy_handled(),
    }


@router.get("/status")
def api_setup_status() -> JSONResponse:
    _require_local_auth()
    status = setup_service.checklist_status()
    return JSONResponse({"local_auth_enabled": True, **status})


@router.patch("/registration")
def api_setup_registration(
    request: Request,
    body: RegistrationBody,
    actor: LocalActor = Depends(require_local_admin_actor),
) -> JSONResponse:
    _require_local_auth()
    assert_mutating_auth(request, actor)
    setup_service.set_registration_open(body.open)
    return JSONResponse(_registration_payload())


@router.post("/registration/ack")
def api_setup_registration_ack(
    request: Request,
    actor: LocalActor = Depends(require_local_admin_actor),
) -> JSONResponse:
    _require_local_auth()
    assert_mutating_auth(request, actor)
    if not is_registration_open():
        raise HTTPException(status_code=409, detail="registration must be open to acknowledge it")
    setup_service.ack_registration_keep_open()
    return JSONResponse(_registration_payload())


@router.post("/complete")
def api_setup_complete(
    request: Request,
    actor: LocalActor = Depends(require_local_admin_actor),
) -> JSONResponse:
    _require_local_auth()
    assert_mutating_auth(request, actor)
    if not setup_service.checklist_ready_to_finish():
        raise HTTPException(status_code=409, detail="setup checklist incomplete")
    setup_service.mark_setup_complete()
    return JSONResponse(
        {
            "setup_complete": True,
            "state": setup_service.setup_state(),
        }
    )
