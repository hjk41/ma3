from __future__ import annotations

import secrets

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.services.library_quota_service import (
    assert_library_creation_allowed,
    library_quota_summary,
    plan_max_libraries,
    platform_max_libraries,
    resolve_personal_plan_code,
)
from app.storage import db


def test_plan_and_platform_defaults():
    assert plan_max_libraries(plan_code="free", scope="personal") == 1
    assert plan_max_libraries(plan_code="pro", scope="personal") == 5
    assert plan_max_libraries(plan_code="team", scope="team") == 10
    assert platform_max_libraries("personal") == 100
    assert platform_max_libraries("team") == 1000


def test_resolve_personal_plan(monkeypatch):
    monkeypatch.setattr(settings, "paid_principal_ids", ("user:paid",))
    assert resolve_personal_plan_code("user:paid") == "pro"
    assert resolve_personal_plan_code("user:free") == "free"


def test_free_user_blocked_from_second_personal_library(monkeypatch):
    monkeypatch.setattr(settings, "plan_max_libraries_free", 1)
    principal = f"user:libquota-{secrets.token_hex(4)}"
    db.create_library(
        db.new_id("lib"),
        name="first personal",
        visibility="private",
        kind="personal",
        owner_principal_id=principal,
    )
    with pytest.raises(HTTPException) as exc:
        assert_library_creation_allowed(
            library_id=db.new_id("lib"),
            kind="personal",
            org_id=settings.default_org_id,
            owner_principal_id=principal,
            plan_code="free",
        )
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "plan_library_limit_exceeded"


def test_pro_user_allowed_up_to_plan_cap(monkeypatch):
    monkeypatch.setattr(settings, "plan_max_libraries_pro", 3)
    monkeypatch.setattr(settings, "plan_max_libraries_team", 3)
    org_id = db.new_id("org")
    for i in range(3):
        db.create_library(db.new_id("lib"), name=f"team {i}", org_id=org_id, kind="custom")
    with pytest.raises(HTTPException) as exc:
        db.create_library(db.new_id("lib"), name="fourth", org_id=org_id, kind="custom")
    assert exc.value.detail["error"] == "plan_library_limit_exceeded"
    assert exc.value.detail["scope"] == "team"


def test_platform_cap_blocks_before_absurd_growth(monkeypatch):
    monkeypatch.setattr(settings, "plan_max_libraries_team", 999)
    monkeypatch.setattr(settings, "platform_max_libraries_team_org", 2)
    org_id = db.new_id("org")
    db.create_library(db.new_id("lib"), name="t1", org_id=org_id, kind="custom")
    db.create_library(db.new_id("lib"), name="t2", org_id=org_id, kind="custom")
    with pytest.raises(HTTPException) as exc:
        db.create_library(db.new_id("lib"), name="t3", org_id=org_id, kind="custom")
    assert exc.value.detail["error"] == "platform_library_limit_exceeded"


def test_community_and_org_default_exempt():
    before = db.count_org_libraries(settings.default_org_id)
    db.create_library(
        db.new_id("lib"),
        name="test helper on default org",
        visibility="private",
        org_id=settings.default_org_id,
        kind="custom",
    )
    assert db.count_org_libraries(settings.default_org_id) == before + 1
    assert_library_creation_allowed(
        library_id=db.new_id("lib"),
        kind="custom",
        org_id=settings.default_org_id,
        owner_principal_id=None,
    ) is None


def test_team_org_library_quota(monkeypatch):
    monkeypatch.setattr(settings, "plan_max_libraries_team", 2)
    org_id = db.new_id("org")
    db.ensure_library(
        settings.default_library_id,
        name="Community",
        visibility="public",
        org_id=settings.default_org_id,
    )
    db.create_library(db.new_id("lib"), name="t1", org_id=org_id, kind="custom")
    db.create_library(db.new_id("lib"), name="t2", org_id=org_id, kind="custom")
    with pytest.raises(HTTPException) as exc:
        db.create_library(db.new_id("lib"), name="t3", org_id=org_id, kind="custom")
    assert exc.value.detail["error"] == "plan_library_limit_exceeded"
    assert exc.value.detail["scope"] == "team"


def test_library_quota_summary_shape():
    summary = library_quota_summary(scope="personal", used=1, plan_code="free")
    assert summary["limit"] == 1
    assert summary["remaining"] == 0
    assert summary["platform_limit"] == 100
