"""Library and org entitlements: read / maintain / enumerate (design/24 D6)."""
from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.storage import db

_GRANT_READ = frozenset({"reader", "writer", "maintainer"})
_GRANT_MAINTAIN = frozenset({"maintainer"})


def _active_org_member(org_id: str, principal_id: str) -> dict[str, Any] | None:
    row = db.get_org_member(org_id, principal_id)
    if not row or row.get("seat_status") != "active":
        return None
    return row


def is_org_admin(principal_id: str, org_id: str) -> bool:
    member = _active_org_member(org_id, principal_id)
    return bool(member and member.get("role") == "admin")


def is_org_admin_for_library(principal_id: str, library_id: str) -> bool:
    lib = db.get_library(library_id)
    if not lib:
        return False
    org_id = str(lib.get("org_id") or "")
    if not org_id or org_id == settings.default_org_id:
        return False
    return is_org_admin(principal_id, org_id)


def library_entitlement_role(principal_id: str, library_id: str) -> str | None:
    grant = db.get_library_grant(library_id, principal_id)
    if grant:
        return str(grant["role"])
    return None


def is_library_owner(principal_id: str, library_id: str) -> bool:
    lib = db.get_library(library_id)
    if not lib:
        return False
    owner = lib.get("owner_principal_id")
    return bool(owner and str(owner) == principal_id)


def can_read_library(principal_id: str | None, library_id: str) -> bool:
    if library_id == settings.default_library_id:
        return True
    if principal_id is None:
        return False
    if is_library_owner(principal_id, library_id):
        return True
    role = library_entitlement_role(principal_id, library_id)
    if role in _GRANT_READ:
        return True
    lib = db.get_library(library_id)
    if not lib:
        return False
    org_id = str(lib.get("org_id") or "")
    if org_id and org_id != settings.default_org_id:
        if is_org_admin(principal_id, org_id):
            return True
        member = _active_org_member(org_id, principal_id)
        if member and str(lib.get("visibility") or "") == "org":
            return True
    for key in db.list_api_keys_for_principal(principal_id):
        for grant in db.get_api_key_grants(str(key["key_id"])):
            if str(grant["library_id"]) == library_id:
                return True
    return False


def can_maintain_library(principal_id: str, library_id: str) -> bool:
    if is_library_owner(principal_id, library_id):
        return True
    role = library_entitlement_role(principal_id, library_id)
    if role in _GRANT_MAINTAIN:
        return True
    return is_org_admin_for_library(principal_id, library_id)


def entitled_library_ids(principal_id: str) -> set[str]:
    libs = {settings.default_library_id}
    personal = db.find_personal_library(principal_id)
    if personal:
        libs.add(str(personal["library_id"]))
    for grant in db.list_library_grants_for_principal(principal_id):
        libs.add(str(grant["library_id"]))
    for org in db.list_orgs_for_principal(principal_id):
        org_id = str(org["id"])
        for lib in db.list_org_libraries(org_id):
            lid = str(lib["library_id"])
            if is_org_admin(principal_id, org_id):
                libs.add(lid)
            elif str(lib.get("visibility") or "") == "org":
                libs.add(lid)
            elif library_entitlement_role(principal_id, lid) in _GRANT_READ:
                libs.add(lid)
    for key in db.list_api_keys_for_principal(principal_id):
        for grant in db.get_api_key_grants(str(key["key_id"])):
            libs.add(str(grant["library_id"]))
    return libs


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
        if is_library_owner(principal_id, lid):
            role = "owner"
            access = "读写·维护"
        elif can_maintain_library(principal_id, lid):
            role = "maintainer"
            access = "维护"
        elif library_entitlement_role(principal_id, lid):
            role = str(library_entitlement_role(principal_id, lid))
            access = "读" if role == "reader" else "读写"
        elif lid in key_labels_by_lib:
            role = "contributor"
            access = "读写"
        else:
            role = "member"
            access = "读"
        out.append(
            {
                "library_id": lid,
                "name": lib.get("name") or lid,
                "visibility": lib.get("visibility") or "org",
                "kind": lib.get("kind") or "",
                "org_id": lib.get("org_id"),
                "access": access,
                "role": role,
                "cases": stats.get("cases", 0),
                "records_active": (rec.get("by_status") or {}).get("active", 0),
                "key_prefixes": key_labels_by_lib.get(lid, []),
                "is_owner": role == "owner",
                "can_maintain": can_maintain_library(principal_id, lid),
            }
        )
    out.sort(key=lambda item: (0 if item["library_id"] == settings.default_library_id else 1, item["name"]))
    return out
