import pytest
from fastapi import HTTPException
from app.core.auth import effective_permissions, has_permission, require_permission
from app.models.auth import BUILTIN_ROLES, Permission, ResolvedPrincipal, RoleAssignment
from app.storage.repositories import PrincipalRepository, RoleAssignmentRepository
from app.core.time import utc_now_iso


def _principal(name="alice"):
    p = PrincipalRepository().upsert_user(name, name)
    return ResolvedPrincipal(p.principal_id, p.kind, p.display_name, "sso_cookie", False)


def test_builtin_role_bundles_match_spec():
    assert Permission.RECORD_READ.value in BUILTIN_ROLES["library_reader"]
    assert Permission.LIBRARY_MANAGE_ACL.value in BUILTIN_ROLES["library_admin"]
    assert BUILTIN_ROLES["system_admin"] == ["*"]


def test_writer_includes_reader_permissions():
    assert set(BUILTIN_ROLES["library_reader"]).issubset(set(BUILTIN_ROLES["library_writer"]))


def test_admin_bypass_short_circuits():
    p = ResolvedPrincipal("admin:root", "admin", "root", "admin_key", True)
    assert has_permission(p, "anything", library_id="lib_x")


def test_library_scope_permission_matches_library_only():
    p = _principal()
    RoleAssignmentRepository().upsert(RoleAssignment(scope_type="library", scope_id="lib_a", principal_id=p.principal_id, role_name="library_writer", granted_at=utc_now_iso(), granted_by=p.principal_id))
    assert Permission.RECORD_WRITE.value in effective_permissions(p, "lib_a")
    assert Permission.RECORD_WRITE.value not in effective_permissions(p, "lib_b")


def test_require_permission_raises_403():
    with pytest.raises(HTTPException) as exc:
        require_permission(_principal("bob"), Permission.RECORD_WRITE, library_id="lib_a")
    assert exc.value.status_code == 403
