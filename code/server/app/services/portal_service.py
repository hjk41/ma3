"""User portal entitlement and library presentation helpers."""
from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.storage import db


def entitled_library_ids(principal_id: str) -> set[str]:
    libs = {settings.default_library_id}
    personal = db.find_personal_library(principal_id)
    if personal:
        libs.add(str(personal["library_id"]))
    for key in db.list_api_keys_for_principal(principal_id):
        for grant in db.get_api_key_grants(str(key["key_id"])):
            libs.add(str(grant["library_id"]))
    return libs


def can_read_library(principal_id: str | None, library_id: str) -> bool:
    if library_id == settings.default_library_id:
        return True
    if principal_id is None:
        return False
    return library_id in entitled_library_ids(principal_id)


def is_library_owner(principal_id: str, library_id: str) -> bool:
    lib = db.get_library(library_id)
    if not lib:
        return False
    owner = lib.get("owner_principal_id")
    return bool(owner and str(owner) == principal_id)


def list_entitled_libraries(principal_id: str) -> list[dict[str, Any]]:
    ids = entitled_library_ids(principal_id)
    keys = db.list_api_keys_for_principal(principal_id)
    key_labels_by_lib: dict[str, list[str]] = {}
    for key in keys:
        prefix = str(key.get("key_prefix") or key.get("key_id", ""))[:12]
        for grant in key.get("grants") or []:
            lid = str(grant["library_id"])
            key_labels_by_lib.setdefault(lid, [])
            if prefix and prefix not in key_labels_by_lib[lid]:
                key_labels_by_lib[lid].append(prefix)

    out: list[dict[str, Any]] = []
    for lib in db.list_libraries(ids):
        lid = str(lib["library_id"])
        stats = db.get_library_stats(lid) or {}
        rec = stats.get("records") or {}
        role = "contributor"
        access = "读"
        if is_library_owner(principal_id, lid):
            role = "owner"
            access = "读写·维护"
        elif lid in key_labels_by_lib:
            access = "读写"
        out.append(
            {
                "library_id": lid,
                "name": lib.get("name") or lid,
                "visibility": lib.get("visibility") or "org",
                "kind": lib.get("kind") or "",
                "access": access,
                "role": role,
                "cases": stats.get("cases", 0),
                "records_active": (rec.get("by_status") or {}).get("active", 0),
                "key_prefixes": key_labels_by_lib.get(lid, []),
                "is_owner": role == "owner",
            }
        )
    out.sort(key=lambda item: (0 if item["library_id"] == settings.default_library_id else 1, item["name"]))
    return out


def validate_authing_admin_config() -> None:
    if settings.authing_configured and not settings.auth_admin_users:
        raise RuntimeError(
            "MA3_AUTH_ADMIN_USERS must list at least one product admin when MA3_AUTHING_ENABLED=1"
        )
