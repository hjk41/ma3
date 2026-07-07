from __future__ import annotations

import secrets

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.services.org_service import (
    add_org_member,
    remove_org_member,
    search_members_by_display_name,
    update_org_member_role,
)
from app.services.principal_service import complete_display_name_setup
from app.storage import db
from app.storage.db import initialize_database


@pytest.fixture(autouse=True)
def isolated_org_db(tmp_path, monkeypatch):
    db_path = tmp_path / "org-service-unit.db"
    monkeypatch.setenv("MA3_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("MA3_DISABLE_EMBEDDINGS", "1")
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(settings, "disable_embeddings", True)
    initialize_database()
    db.set_library_write_buffer_hours(settings.default_library_id, 0)


def _seed_user(*, sso_user: str, display_name: str) -> str:
    principal_id = f"user:{sso_user}"
    db.upsert_user_principal(sso_user=sso_user, display_name=sso_user)
    complete_display_name_setup(principal_id, display_name)
    return principal_id


def _seed_team_org(*, admin_id: str) -> str:
    org_id = db.new_id("org")
    db.create_organization(org_id, name="Test Team", kind="team", owner_principal_id=admin_id)
    db.add_org_member(org_id=org_id, principal_id=admin_id, role="admin")
    return org_id


def test_search_members_by_display_name_prefix_and_substring():
    _seed_user(sso_user="alice-u", display_name="Alice Wang")
    _seed_user(sso_user="bob-u", display_name="Bob")
    _seed_user(sso_user="char-u", display_name="Charlie")

    assert [r["display_name"] for r in search_members_by_display_name("Ali")] == ["Alice Wang"]
    assert "Charlie" in [r["display_name"] for r in search_members_by_display_name("ar")]
    assert search_members_by_display_name("a") == []


def test_search_members_by_display_name_principal_prefix():
    pid = _seed_user(sso_user="prefix-u", display_name="Prefix User")
    hits = search_members_by_display_name(pid)
    assert len(hits) == 1
    assert hits[0]["principal_id"] == pid


def test_add_org_member_by_display_name():
    admin_id = _seed_user(sso_user="org-admin", display_name="Org Admin")
    member_id = _seed_user(sso_user="new-member", display_name="New Member")
    org_id = _seed_team_org(admin_id=admin_id)

    row = add_org_member(
        org_id=org_id,
        actor_principal_id=admin_id,
        display_name="New Member",
        role="member",
    )
    assert row["principal_id"] == member_id
    assert row["role"] == "member"
    assert row["seat_status"] == "active"


def test_cannot_remove_last_org_admin():
    admin_id = _seed_user(sso_user=f"sole-admin-{secrets.token_hex(3)}", display_name="Sole Admin")
    org_id = _seed_team_org(admin_id=admin_id)

    with pytest.raises(HTTPException) as exc:
        remove_org_member(org_id=org_id, actor_principal_id=admin_id, target_principal_id=admin_id)
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "last_org_admin"


def test_cannot_demote_last_org_admin():
    admin_id = _seed_user(sso_user=f"demote-admin-{secrets.token_hex(3)}", display_name="Demote Admin")
    org_id = _seed_team_org(admin_id=admin_id)

    with pytest.raises(HTTPException) as exc:
        update_org_member_role(
            org_id=org_id,
            actor_principal_id=admin_id,
            target_principal_id=admin_id,
            role="member",
        )
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "last_org_admin"


def test_can_remove_admin_when_another_admin_exists():
    admin_a = _seed_user(sso_user=f"admin-a-{secrets.token_hex(3)}", display_name="Admin A")
    admin_b = _seed_user(sso_user=f"admin-b-{secrets.token_hex(3)}", display_name="Admin B")
    org_id = _seed_team_org(admin_id=admin_a)
    db.add_org_member(org_id=org_id, principal_id=admin_b, role="admin")

    remove_org_member(org_id=org_id, actor_principal_id=admin_a, target_principal_id=admin_b)
    row = db.get_org_member(org_id, admin_b)
    assert row is not None
    assert row["seat_status"] == "removed"
    assert db.count_active_org_admins(org_id) == 1
