"""User principals: Authing sync and display-name preferences."""
from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException

from app.auth.authing_client import AuthingUser
from app.services.onboarding_service import ensure_personal_library
from app.storage import db

_DISPLAY_NAME_RE = re.compile(r"^[^\x00-\x1f\x7f]+$", re.UNICODE)


def ensure_user_principal(user: AuthingUser) -> dict[str, Any]:
    metadata = {
        "provider": "authing",
        "email": user.email,
        "phone": user.phone,
        "username": user.username,
        "photo": user.photo,
        "is_admin": user.is_admin,
    }
    principal_id = f"user:{user.sub}"
    existing = db.get_user_principal(principal_id)
    if existing and existing.get("display_name_locked"):
        display_name = str(existing["display_name"])
    else:
        display_name = user.sub
    return db.upsert_user_principal(
        sso_user=user.sub,
        display_name=display_name,
        metadata=metadata,
    )


def display_name_setup_required(principal_id: str) -> bool:
    return not db.user_display_name_is_locked(principal_id)


def normalize_display_name(raw: str) -> str:
    name = " ".join(str(raw or "").strip().split())
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="display name must be at least 2 characters")
    if len(name) > 32:
        raise HTTPException(status_code=400, detail="display name must be at most 32 characters")
    if not _DISPLAY_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="display name contains invalid characters")
    if re.fullmatch(r"[0-9a-f]{20,}", name, flags=re.IGNORECASE):
        raise HTTPException(status_code=400, detail="display name cannot look like an internal id")
    return name


def assert_display_name_available(display_name: str, *, exclude_principal_id: str | None = None) -> None:
    if db.find_user_by_display_name(display_name, exclude_principal_id=exclude_principal_id):
        raise HTTPException(status_code=400, detail="显示名已被使用，请换一个")


def complete_display_name_setup(principal_id: str, display_name: str) -> str:
    """First-time registration display name; locked afterward."""
    if db.user_display_name_is_locked(principal_id):
        raise HTTPException(status_code=400, detail="显示名已设定，不可修改")
    name = normalize_display_name(display_name)
    assert_display_name_available(name, exclude_principal_id=principal_id)
    updated = db.set_user_display_name(principal_id, name)
    if not updated:
        raise HTTPException(status_code=404, detail="principal not found")
    personal = db.find_personal_library(principal_id)
    if personal:
        db.set_library_name(str(personal["library_id"]), f"{name} 的个人库")
    else:
        ensure_personal_library(principal_id, name)
    return name


def update_user_display_name(principal_id: str, display_name: str) -> str:
    """Alias for registration setup (display names are immutable after lock)."""
    return complete_display_name_setup(principal_id, display_name)


def resolve_display_name(principal_id: str, *, fallback: str) -> str:
    row = db.get_user_principal(principal_id)
    if row and row.get("display_name"):
        return str(row["display_name"])
    return fallback
