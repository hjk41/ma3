from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.services.org_quota_service import (
    assert_team_org_creation_allowed,
    plan_max_team_orgs_owned,
    team_org_creation_summary,
)
from app.services.org_service import create_team_org, seed_team_org
from app.storage import db
from app.storage.db import initialize_database


@pytest.fixture(autouse=True)
def isolated_org_quota_db(tmp_path, monkeypatch):
    db_path = tmp_path / "org-quota-unit.db"
    monkeypatch.setenv("MA3_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(settings, "plan_max_team_orgs_owned_free", 0)
    monkeypatch.setattr(settings, "plan_max_team_orgs_owned_pro", 1)
    monkeypatch.setattr(settings, "paid_principal_ids", ("user:paid",))
    initialize_database()
    db.set_library_write_buffer_hours(settings.default_library_id, 0)


def test_free_user_cannot_create_team_org():
    summary = team_org_creation_summary("user:free")
    assert not summary["allowed"]
    assert summary["reason"] == "upgrade_required"
    with pytest.raises(HTTPException) as exc:
        assert_team_org_creation_allowed("user:free")
    assert exc.value.detail["error"] == "team_org_upgrade_required"


def test_pro_user_can_create_one_team_org():
    pid = "user:paid"
    assert team_org_creation_summary(pid)["allowed"]
    org = create_team_org(name="Paid Team", owner_principal_id=pid)
    assert org["kind"] == "team"
    assert not team_org_creation_summary(pid)["allowed"]
    with pytest.raises(HTTPException) as exc:
        create_team_org(name="Second Team", owner_principal_id=pid)
    assert exc.value.detail["error"] == "team_org_limit_reached"


def test_seed_team_org_bypasses_gate():
    seed_team_org(name="Seed Team", admin_principal_id="user:seed")
    assert db.count_team_orgs_owned("user:seed") == 1


def test_plan_defaults():
    assert plan_max_team_orgs_owned("free") == 0
    assert plan_max_team_orgs_owned("pro") == 1
