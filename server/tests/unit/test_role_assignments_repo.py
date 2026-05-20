from app.core.auth import effective_libraries
from app.core.time import utc_now_iso
from app.models.auth import ResolvedPrincipal, RoleAssignment
from app.models.library import LibraryCreate
from app.services.library_service import create_library
from app.storage.repositories import PrincipalRepository, RoleAssignmentRepository


def test_insert_read_delete_role_assignment():
    p = PrincipalRepository().upsert_user("alice", "Alice")
    repo = RoleAssignmentRepository()
    repo.upsert(RoleAssignment(scope_type="library", scope_id="lib1", principal_id=p.principal_id, role_name="library_reader", granted_at=utc_now_iso(), granted_by=p.principal_id))
    assert repo.get_library_role("lib1", p.principal_id) == "reader"
    assert repo.delete("library", "lib1", p.principal_id)
    assert repo.get_library_role("lib1", p.principal_id) is None


def test_effective_libraries_from_role_assignments():
    p = PrincipalRepository().upsert_user("alice", "Alice")
    lib1 = create_library(LibraryCreate(name="private-a", is_public=False))
    lib2 = create_library(LibraryCreate(name="private-b", is_public=False))
    repo = RoleAssignmentRepository()
    now = utc_now_iso()
    repo.upsert(RoleAssignment(scope_type="library", scope_id=lib1.library_id, principal_id=p.principal_id, role_name="library_writer", granted_at=now, granted_by=p.principal_id))
    repo.upsert(RoleAssignment(scope_type="library", scope_id=lib2.library_id, principal_id=p.principal_id, role_name="library_reader", granted_at=now, granted_by=p.principal_id))
    rp = ResolvedPrincipal(p.principal_id, p.kind, p.display_name, "sso_cookie", False)
    assert effective_libraries(rp)[lib1.library_id] == "writer"
    assert effective_libraries(rp)[lib2.library_id] == "reader"
