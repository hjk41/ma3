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
    return db.upsert_user_principal(
        sso_user=user.sub,
        display_name=user.display_name,
        metadata=metadata,
    )


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


def update_user_display_name(principal_id: str, display_name: str) -> str:
    name = normalize_display_name(display_name)
    updated = db.set_user_display_name(principal_id, name)
    if not updated:
        raise HTTPException(status_code=404, detail="principal not found")
    personal = db.find_personal_library(principal_id)
    if personal:
        db.set_library_name(str(personal["library_id"]), f"{name} 的个人库")
    else:
        ensure_personal_library(principal_id, name)
    return name


def resolve_display_name(principal_id: str, *, fallback: str) -> str:
    row = db.get_user_principal(principal_id)
    if row and row.get("display_name"):
        return str(row["display_name"])
    return fallback
