from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.auth.authing_client import AuthingUser
from app.core.config import settings
from app.services.onboarding_service import ensure_personal_library
from app.services.principal_service import (
    complete_display_name_setup,
    ensure_user_principal,
    normalize_display_name,
    update_user_display_name,
)
from app.storage import db
from app.storage.db import initialize_database


@pytest.fixture(autouse=True)
def isolated_display_name_db(tmp_path, monkeypatch):
    db_path = tmp_path / "display-name-unit.db"
    monkeypatch.setenv("MA3_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("MA3_DISABLE_EMBEDDINGS", "1")
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(settings, "disable_embeddings", True)
    initialize_database()
    db.set_library_write_buffer_hours(settings.default_library_id, 0)


def test_normalize_display_name_rejects_short_and_uuid_like():
    with pytest.raises(HTTPException):
        normalize_display_name("a")
    with pytest.raises(HTTPException):
        normalize_display_name("6a45abec4d2ef946d80649f6")


def test_normalize_display_name_accepts_cjk():
    assert normalize_display_name("  小明  ") == "小明"


def test_upsert_preserves_locked_display_name():
    db.upsert_user_principal(sso_user="name-lock-test", display_name="name-lock-test")
    complete_display_name_setup("user:name-lock-test", "我的昵称")
    row = ensure_user_principal(
        AuthingUser(
            sub="name-lock-test",
            display_name="6a45abec4d2ef946d80649f6",
            email=None,
            phone=None,
            username=None,
            photo=None,
            is_admin=False,
        )
    )
    assert row["display_name"] == "我的昵称"


def test_update_display_name_renames_personal_library():
    pid = "user:display-name-lib"
    db.upsert_user_principal(sso_user="display-name-lib", display_name="display-name-lib")
    ensure_personal_library(pid, "display-name-lib")
    update_user_display_name(pid, "新名字")
    personal = db.find_personal_library(pid)
    assert personal is not None
    assert personal["name"] == "新名字 的个人库"
    row = db.get_user_principal(pid)
    assert row["display_name"] == "新名字"
    assert row["display_name_locked"]


def test_update_display_name_rejects_duplicate():
    db.upsert_user_principal(sso_user="name-owner-a", display_name="name-owner-a")
    db.upsert_user_principal(sso_user="name-owner-b", display_name="name-owner-b")
    update_user_display_name("user:name-owner-a", "唯一昵称")
    with pytest.raises(HTTPException) as exc:
        update_user_display_name("user:name-owner-b", "唯一昵称")
    assert exc.value.status_code == 400
    assert "已被使用" in str(exc.value.detail)


def test_update_display_name_rejects_change_after_locked():
    pid = "user:name-keep"
    db.upsert_user_principal(sso_user="name-keep", display_name="name-keep")
    update_user_display_name(pid, "保留名")
    with pytest.raises(HTTPException) as exc:
        update_user_display_name(pid, "另一个名字")
    assert exc.value.status_code == 400
    assert "不可修改" in str(exc.value.detail)


def test_display_name_uniqueness_is_case_insensitive():
    db.upsert_user_principal(sso_user="case-a", display_name="case-a")
    db.upsert_user_principal(sso_user="case-b", display_name="case-b")
    update_user_display_name("user:case-a", "Alice")
    with pytest.raises(HTTPException):
        update_user_display_name("user:case-b", "alice")


def test_upsert_uses_sso_placeholder_until_setup():
    db.upsert_user_principal(sso_user="first-user", display_name="first-user")
    complete_display_name_setup("user:first-user", "共享昵称")
    row = ensure_user_principal(
        AuthingUser(
            sub="second-user",
            display_name="共享昵称",
            email=None,
            phone=None,
            username=None,
            photo=None,
            is_admin=False,
        )
    )
    assert row["display_name"] == "second-user"
    assert not row.get("display_name_locked")
