from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models.auth import AclEntry, ResolvedPrincipal
from app.models.library import LibraryCreate
from app.core.time import utc_now_iso
from app.core.auth import effective_libraries
from app.services.auth_service import bootstrap_library_admin, grant_library_access, issue_api_key
from app.services.library_service import create_library
from app.storage.repositories import LibraryAclRepository, PrincipalRepository


def _user(name: str) -> ResolvedPrincipal:
    p = PrincipalRepository().upsert_user(name, name)
    return ResolvedPrincipal(p.principal_id, p.kind, p.display_name, "sso_cookie", False)


def test_grant_requires_equal_or_higher_role():
    alice = _user("alice")
    bob = PrincipalRepository().upsert_user("bob", "bob")
    lib = create_library(LibraryCreate(name="lib", is_public=False))
    LibraryAclRepository().upsert(AclEntry(library_id=lib.library_id, principal_id=alice.principal_id, role="writer", granted_at=utc_now_iso(), granted_by=alice.principal_id))
    with pytest.raises(HTTPException) as exc:
        grant_library_access(lib.library_id, bob.principal_id, "admin", actor=alice)
    assert exc.value.status_code == 403


def test_legacy_actor_cannot_grant():
    legacy = ResolvedPrincipal("legacy:tok", "legacy", "tok", "api_key", False)
    bob = PrincipalRepository().upsert_user("bob", "bob")
    lib = create_library(LibraryCreate(name="lib", is_public=False))
    with pytest.raises(HTTPException) as exc:
        grant_library_access(lib.library_id, bob.principal_id, "reader", actor=legacy)
    assert exc.value.detail == "legacy_cannot_grant"


def test_scope_empty_is_rejected():
    alice = _user("alice")
    PrincipalRepository().upsert_user("bob", "bob")
    lib = create_library(LibraryCreate(name="owned", is_public=False))
    bootstrap_library_admin(lib.library_id, alice.principal_id, actor=alice)
    with pytest.raises(HTTPException) as exc:
        issue_api_key(alice.principal_id, "bad", ["lib_missing"], None, actor=alice)
    assert exc.value.status_code == 400
    assert exc.value.detail == "scope_empty"


def test_public_library_contributes_reader_for_anonymous():
    lib = create_library(LibraryCreate(name="public", is_public=True))
    anon = ResolvedPrincipal("anonymous", "anonymous", "anonymous", "anonymous", False)
    assert effective_libraries(anon)[lib.library_id] == "reader"


def test_admin_bypass_dominates_everything():
    lib = create_library(LibraryCreate(name="private", is_public=False))
    admin = ResolvedPrincipal("admin:root", "admin", "root", "admin_key", True)
    assert effective_libraries(admin)[lib.library_id] == "admin"
