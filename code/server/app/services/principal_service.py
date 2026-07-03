from __future__ import annotations

from typing import Any

from app.auth.authing_client import AuthingUser
from app.storage import db


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
