"""Local username/password auth for self-host when OIDC is off."""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from app.core.config import settings
from app.services.api_key_encryption import _fernet_key_material
from app.services.onboarding_service import ensure_personal_org
from app.services.principal_service import complete_display_name_setup
from app.storage import db

logger = logging.getLogger(__name__)

_HASHER = PasswordHasher()
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{1,31}$")
_TOKEN_PREFIX = "local.v1."
_SESSION_TTL_SEC = 7 * 24 * 3600


def normalize_username(username: str) -> str:
    return str(username or "").strip().lower()


def validate_username(username: str) -> str:
    raw = normalize_username(username)
    if not _USERNAME_RE.match(raw):
        raise HTTPException(
            status_code=400,
            detail="username must be 2–32 chars: letters, digits, . _ - (start alnum)",
        )
    return raw


def validate_password(password: str) -> str:
    pw = str(password or "")
    if len(pw) < 8:
        raise HTTPException(status_code=400, detail="password must be at least 8 characters")
    if len(pw) > 200:
        raise HTTPException(status_code=400, detail="password too long")
    return pw


def hash_password(password: str) -> str:
    return _HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _HASHER.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        logger.exception("password verify failed")
        return False


def is_admin_username(username: str, *, first_user: bool) -> bool:
    if first_user:
        return True
    admins = {a.lower() for a in settings.auth_admin_users}
    return normalize_username(username) in admins


def is_registration_open() -> bool:
    """DB `local_registration_open` overrides env; first account always allowed."""
    if db.count_local_accounts() == 0:
        return True
    db_val = db.get_instance_setting("local_registration_open")
    if db_val is not None:
        return str(db_val).strip().lower() in {"1", "true", "yes", "on"}
    return bool(settings.local_auth_open_registration)


def register_local_user(
    *,
    username: str,
    password: str,
    display_name: str | None = None,
    invite_token: str | None = None,
) -> dict[str, Any]:
    if not settings.local_auth_enabled:
        raise HTTPException(status_code=503, detail="local auth is not enabled")

    from app.services import org_invite_service

    token = org_invite_service.normalize_invite_token(invite_token)
    invite_preview = None
    if token:
        invite_preview = org_invite_service.assert_invite_allows_registration(token)
    elif not is_registration_open():
        raise HTTPException(status_code=403, detail="registration is closed; ask an admin for an invite link")

    uname = validate_username(username)
    pw = validate_password(password)
    if db.get_local_account(uname):
        raise HTTPException(status_code=409, detail="username already taken")

    first_user = db.count_local_accounts() == 0
    admin = is_admin_username(uname, first_user=first_user)
    name = (display_name or "").strip() or uname

    principal = db.upsert_user_principal(
        sso_user=f"local:{uname}",
        display_name=name,
        metadata={"provider": "local", "username": uname},
    )
    pid = str(principal["principal_id"])
    # Lock display name so portal setup is skipped for local accounts.
    try:
        if not db.user_display_name_is_locked(pid):
            complete_display_name_setup(pid, name)
    except HTTPException:
        # Name collision: fall back to username-derived unique name.
        complete_display_name_setup(pid, f"{uname}-{pid[-4:]}")
        name = f"{uname}-{pid[-4:]}"

    db.create_local_account(
        username=uname,
        password_hash=hash_password(pw),
        principal_id=pid,
        is_admin=admin,
    )
    ensure_personal_org(pid, name)
    out: dict[str, Any] = {
        "username": uname,
        "principal_id": pid,
        "display_name": name,
        "is_admin": admin,
    }
    if token:
        membership = org_invite_service.redeem_invite(token=token, principal_id=pid)
        out["org_membership"] = membership
        if invite_preview:
            out["org_membership"]["org_name"] = invite_preview.get("org_name")
    return out


def authenticate_local_user(*, username: str, password: str) -> dict[str, Any]:
    if not settings.local_auth_enabled:
        raise HTTPException(status_code=503, detail="local auth is not enabled")
    uname = normalize_username(username)
    account = db.get_local_account(uname)
    if not account or not verify_password(str(account["password_hash"]), str(password or "")):
        raise HTTPException(status_code=401, detail="invalid username or password")
    principal = db.get_user_principal(str(account["principal_id"]))
    display = str(principal["display_name"]) if principal else uname
    admin = bool(int(account.get("is_admin") or 0)) or uname in {a.lower() for a in settings.auth_admin_users}
    return {
        "username": uname,
        "principal_id": str(account["principal_id"]),
        "display_name": display,
        "is_admin": admin,
        "sub": uname,
    }


def issue_local_session_token(account: dict[str, Any], *, ttl_sec: int = _SESSION_TTL_SEC) -> str:
    payload = {
        "v": 1,
        "pid": account["principal_id"],
        "u": account["username"],
        "admin": bool(account.get("is_admin")),
        "exp": int(time.time()) + int(ttl_sec),
    }
    token = Fernet(_fernet_key_material()).encrypt(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return _TOKEN_PREFIX + token.decode("ascii")


def parse_local_session_token(token: str) -> dict[str, Any] | None:
    if not token.startswith(_TOKEN_PREFIX):
        return None
    raw = token[len(_TOKEN_PREFIX) :]
    try:
        payload = json.loads(Fernet(_fernet_key_material()).decrypt(raw.encode("ascii")).decode("utf-8"))
    except (InvalidToken, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if int(payload.get("v") or 0) != 1:
        return None
    if int(payload.get("exp") or 0) < int(time.time()):
        return None
    username = normalize_username(str(payload.get("u") or ""))
    account = db.get_local_account(username)
    if not account:
        return None
    if str(account["principal_id"]) != str(payload.get("pid") or ""):
        return None
    principal = db.get_user_principal(str(account["principal_id"]))
    display = str(principal["display_name"]) if principal else username
    admin = bool(int(account.get("is_admin") or 0)) or username in {a.lower() for a in settings.auth_admin_users}
    return {
        "username": username,
        "principal_id": str(account["principal_id"]),
        "display_name": display,
        "is_admin": admin,
        "sub": username,
    }


def set_local_account_admin(*, username: str, is_admin: bool) -> dict[str, Any] | None:
    return db.set_local_account_admin(normalize_username(username), is_admin=is_admin)


def list_local_accounts(*, limit: int = 200) -> list[dict[str, Any]]:
    return db.list_local_accounts(limit=limit)


def public_account_payload(account: dict[str, Any]) -> dict[str, Any]:
    from app.services.local_admin_service import public_account

    return public_account(account)


def mint_api_key_for_account(account: dict[str, Any], *, label: str) -> dict[str, Any]:
    from app.services.onboarding_service import create_personal_dev_key

    created = create_personal_dev_key(
        str(account["principal_id"]),
        str(account.get("display_name") or account["username"]),
        label=label,
    )
    return {
        "key_id": created["key_id"],
        "key_prefix": created["key_prefix"],
        "label": created["label"],
        "plaintext_key": created["plaintext_key"],
        "grants": created["grants"],
    }


def register_local_user_api(
    *,
    username: str,
    password: str,
    display_name: str | None = None,
    api_key_label: str | None = None,
    invite_token: str | None = None,
) -> dict[str, Any]:
    account = register_local_user(
        username=username,
        password=password,
        display_name=display_name,
        invite_token=invite_token,
    )
    out: dict[str, Any] = {"account": public_account_payload({**account, "created_at": None})}
    # Refresh from DB for created_at / is_admin int
    row = db.get_local_account(account["username"])
    if row:
        out["account"] = public_account_payload(row)
    if account.get("org_membership"):
        out["org_membership"] = account["org_membership"]
    if api_key_label is not None:
        out["api_key"] = mint_api_key_for_account(
            {"principal_id": account["principal_id"], "username": account["username"], "display_name": account["display_name"]},
            label=api_key_label,
        )
    return out


def login_local_user_api(
    *,
    username: str,
    password: str,
    api_key_label: str,
) -> dict[str, Any]:
    auth = authenticate_local_user(username=username, password=password)
    row = db.get_local_account(auth["username"])
    if row is None:
        raise HTTPException(status_code=401, detail="invalid username or password")
    return {
        "account": public_account_payload(row),
        "api_key": mint_api_key_for_account(
            {
                "principal_id": auth["principal_id"],
                "username": auth["username"],
                "display_name": auth["display_name"],
            },
            label=api_key_label,
        ),
    }
