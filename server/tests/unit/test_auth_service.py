from __future__ import annotations

from app.models.auth import ResolvedPrincipal
from app.models.library import LibraryCreate
from app.core.auth import _resolve_from_raw_only
from app.services.auth_service import bootstrap_library_admin, grant_library_access, issue_api_key
from app.services.library_service import create_library
from app.storage.repositories import ApiKeyRepository, AuthAuditRepository, PrincipalRepository


def _user(name: str) -> ResolvedPrincipal:
    p = PrincipalRepository().upsert_user(name, name)
    return ResolvedPrincipal(p.principal_id, p.kind, p.display_name, "sso_cookie", False)


def test_audit_row_written_on_mutations():
    alice = _user("alice")
    bob = PrincipalRepository().upsert_user("bob", "bob")
    lib = create_library(LibraryCreate(name="lib", is_public=False))
    bootstrap_library_admin(lib.library_id, alice.principal_id, actor=alice)
    issue_api_key(alice.principal_id, "key", [lib.library_id], None, actor=alice)
    grant_library_access(lib.library_id, bob.principal_id, "reader", actor=alice)
    actions = AuthAuditRepository().count_by_action()
    assert actions["acl.grant"] >= 2
    assert actions["key.issue"] == 1


def test_last_used_update_is_throttled():
    alice = _user("alice")
    lib = create_library(LibraryCreate(name="lib", is_public=False))
    bootstrap_library_admin(lib.library_id, alice.principal_id, actor=alice)
    issued = issue_api_key(alice.principal_id, "key", [lib.library_id], None, actor=alice)
    _resolve_from_raw_only(issued.raw)
    first = ApiKeyRepository().get(issued.info.key_id).last_used_at
    _resolve_from_raw_only(issued.raw)
    second = ApiKeyRepository().get(issued.info.key_id).last_used_at
    assert first is not None
    assert second == first
