from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.auth.authing_client import AuthingUser
from app.services.onboarding_service import ensure_personal_library
from app.services.principal_service import ensure_user_principal, normalize_display_name, update_user_display_name
from app.storage import db


def test_normalize_display_name_rejects_short_and_uuid_like():
    with pytest.raises(HTTPException):
        normalize_display_name("a")
    with pytest.raises(HTTPException):
        normalize_display_name("6a45abec4d2ef946d80649f6")


def test_normalize_display_name_accepts_cjk():
    assert normalize_display_name("  小明  ") == "小明"


def test_upsert_preserves_locked_display_name():
    db.initialize_database()
    db.upsert_user_principal(sso_user="name-lock-test", display_name="authing-default")
    db.set_user_display_name("user:name-lock-test", "我的昵称")
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
    db.initialize_database()
    pid = "user:display-name-lib"
    db.upsert_user_principal(sso_user="display-name-lib", display_name="old-name")
    ensure_personal_library(pid, "old-name")
    update_user_display_name(pid, "新名字")
    personal = db.find_personal_library(pid)
    assert personal is not None
    assert personal["name"] == "新名字 的个人库"
    row = db.get_user_principal(pid)
    assert row["display_name"] == "新名字"
