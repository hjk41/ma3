"""Org library creation and library-level grants (design/24)."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import HTTPException

from app.services.entitlement_service import can_maintain_library, is_org_admin
from app.services.org_service import DEFAULT_TEAM_LIBRARY_VISIBILITY
from app.storage import db

LibraryVisibility = Literal["private", "org"]
GrantRole = Literal["reader", "writer", "maintainer"]


def assert_library_maintainer(library_id: str, principal_id: str) -> None:
    if not can_maintain_library(principal_id, library_id):
        raise HTTPException(status_code=404, detail="library not found")


def create_org_library(
    *,
    org_id: str,
    actor_principal_id: str,
    name: str,
    visibility: LibraryVisibility | None = None,
    write_buffer_hours: int = 24,
    confirm_org_visibility: bool = False,
) -> dict[str, Any]:
    if not is_org_admin(actor_principal_id, org_id):
        raise HTTPException(status_code=404, detail="organization not found")
    if not db.get_organization(org_id):
        raise HTTPException(status_code=404, detail="organization not found")
    lib_name = " ".join(str(name or "").strip().split())
    if len(lib_name) < 2:
        raise HTTPException(status_code=400, detail="library name must be at least 2 characters")
    vis = visibility or DEFAULT_TEAM_LIBRARY_VISIBILITY
    if vis not in ("private", "org"):
        raise HTTPException(status_code=400, detail="invalid visibility")
    if vis == "org" and not confirm_org_visibility:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "org_visibility_confirm_required",
                "message": "confirm org-wide visibility before creating this library",
            },
        )
    library_id = db.new_id("lib")
    created = db.create_library(
        library_id,
        name=lib_name,
        visibility=vis,
        org_id=org_id,
        kind="custom",
    )
    hours = max(0, min(int(write_buffer_hours), 168))
    db.set_library_write_buffer_hours(library_id, hours)
    row = db.get_library(library_id)
    assert row is not None
    return {"library_id": library_id, **{k: v for k, v in row.items() if k != "id"}, "id": library_id}


def add_library_grant(
    *,
    library_id: str,
    actor_principal_id: str,
    principal_id: str | None = None,
    display_name: str | None = None,
    role: GrantRole = "reader",
) -> dict[str, Any]:
    from app.services.org_service import resolve_member_principal_id

    assert_library_maintainer(library_id, actor_principal_id)
    target_id = resolve_member_principal_id(principal_id=principal_id, display_name=display_name)
    if role not in ("reader", "writer", "maintainer"):
        raise HTTPException(status_code=400, detail="invalid grant role")
    return db.upsert_library_grant(
        library_id=library_id,
        principal_id=target_id,
        role=role,
        created_by=actor_principal_id,
    )


def remove_library_grant(
    *,
    library_id: str,
    actor_principal_id: str,
    target_principal_id: str,
) -> None:
    assert_library_maintainer(library_id, actor_principal_id)
    db.delete_library_grant(library_id=library_id, principal_id=target_principal_id)
