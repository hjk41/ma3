from app.core.auth import require_library_write
from app.models.auth import ResolvedPrincipal
from app.models.library import LibraryCreate
from app.services.auth_service import bootstrap_library_admin, grant_library_access, revoke_library_access
from app.services.library_service import create_library
from app.storage.repositories import PrincipalRepository, RoleAssignmentRepository


def _user(name: str):
    p = PrincipalRepository().upsert_user(name, name)
    return ResolvedPrincipal(p.principal_id, p.kind, p.display_name, "sso_cookie", False)


def test_v3_acl_services_use_role_assignments_and_permissions():
    alice = _user("alice")
    bob = PrincipalRepository().upsert_user("bob", "Bob")
    bob_rp = ResolvedPrincipal(bob.principal_id, bob.kind, bob.display_name, "sso_cookie", False)
    lib = create_library(LibraryCreate(name="private", is_public=False))
    bootstrap_library_admin(lib.library_id, alice.principal_id, actor=alice)
    grant = grant_library_access(lib.library_id, bob.principal_id, "writer", actor=alice)
    assert grant.role == "writer"
    assert RoleAssignmentRepository().get_library_role(lib.library_id, bob.principal_id) == "writer"
    assert require_library_write(lib.library_id, bob_rp) == "writer"
    revoke_library_access(lib.library_id, bob.principal_id, actor=alice)
    assert RoleAssignmentRepository().get_library_role(lib.library_id, bob.principal_id) is None
