from __future__ import annotations

import os

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.storage.db import initialize_database


def _enable_authing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "authing_enabled", True)
    monkeypatch.setattr(settings, "authing_issuer", "https://example.authing.cn")
    monkeypatch.setattr(settings, "authing_app_id", "test-app")
    monkeypatch.setattr(settings, "authing_app_secret", "test-secret")
    monkeypatch.setattr(settings, "auth_admin_users", ["portal-admin"])


def _patch_session(monkeypatch, user) -> None:
    import app.api.routes_keys as routes_keys
    import app.api.routes_mcp_oauth as routes_mcp_oauth
    import app.api.ui_session as ui_session
    import app.auth.session as session_mod
    import app.services.feedback_service as feedback_service
    import app.services.portal_actor_service as portal_actor_service

    resolver = lambda _req: user
    monkeypatch.setattr(session_mod, "resolve_session_user", resolver)
    monkeypatch.setattr(ui_session, "resolve_session_user", resolver)
    monkeypatch.setattr(routes_keys, "resolve_session_user", resolver)
    monkeypatch.setattr(routes_mcp_oauth, "resolve_session_user", resolver)
    monkeypatch.setattr(feedback_service, "resolve_session_user", resolver)
    monkeypatch.setattr(portal_actor_service, "resolve_session_user", resolver)


@pytest.fixture()
def portal_user() -> "SessionUser":
    from app.auth.session import SessionUser

    return SessionUser(
        principal_id="user:portal-a",
        sub="portal-a",
        display_name="Portal A",
        email=None,
        phone=None,
        is_admin=False,
    )


@pytest.fixture()
def admin_user() -> "SessionUser":
    from app.auth.session import SessionUser

    return SessionUser(
        principal_id="user:portal-admin",
        sub="portal-admin",
        display_name="Portal Admin",
        email=None,
        phone=None,
        is_admin=True,
    )


@pytest.fixture()
def authing_portal_client(isolated_client, monkeypatch, portal_user):
    from app.services.onboarding_service import ensure_personal_org
    from app.services.principal_service import complete_display_name_setup
    from app.storage import db

    _enable_authing(monkeypatch)
    _patch_session(monkeypatch, portal_user)
    db.upsert_user_principal(sso_user=portal_user.sub, display_name=portal_user.sub)
    complete_display_name_setup(portal_user.principal_id, portal_user.display_name)
    ensure_personal_org(portal_user.principal_id, portal_user.display_name)
    return isolated_client


@pytest.fixture()
def authing_admin_client(isolated_client, monkeypatch, admin_user):
    from app.services.onboarding_service import ensure_personal_org
    from app.services.principal_service import complete_display_name_setup
    from app.storage import db

    _enable_authing(monkeypatch)
    _patch_session(monkeypatch, admin_user)
    db.upsert_user_principal(sso_user=admin_user.sub, display_name=admin_user.sub)
    complete_display_name_setup(admin_user.principal_id, admin_user.display_name)
    ensure_personal_org(admin_user.principal_id, admin_user.display_name)
    return isolated_client


@pytest.fixture(scope="session")
def _ci_postgres_admin():
    """Session-scoped scratch DB when MA3_CI_DATABASE_URL points at Postgres."""
    ci_pg = (os.environ.get("MA3_CI_DATABASE_URL") or "").strip()
    if not ci_pg.startswith("postgresql"):
        yield None
        return

    import uuid
    from urllib.parse import urlparse, urlunparse

    import psycopg
    from psycopg import sql

    db_name = f"ma3_ci_{uuid.uuid4().hex[:10]}"
    parsed = urlparse(ci_pg)
    admin_url = urlunparse(parsed._replace(path="/postgres"))
    test_url = urlunparse(parsed._replace(path=f"/{db_name}"))
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
    try:
        yield {"admin_url": admin_url, "test_url": test_url, "db_name": db_name}
    finally:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(db_name))
            )


def _truncate_postgres_public_tables() -> None:
    from app.storage import db as _db

    if not _db.is_postgres():
        return
    with _db.connect() as conn:
        rows = _db._fetchall(
            conn,
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'",
        )
        names = [r["tablename"] if isinstance(r, dict) else r[0] for r in (rows or [])]
        if not names:
            return
        # Quote identifiers safely
        quoted = ", ".join('"' + n.replace('"', "") + '"' for n in names)
        conn.execute(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE")
        conn.commit()


@pytest.fixture()
def isolated_client(tmp_path, monkeypatch, _ci_postgres_admin):
    """Fresh database per test (SQLite by default; shared CI Postgres + truncate)."""
    if _ci_postgres_admin is not None:
        test_url = _ci_postgres_admin["test_url"]
        monkeypatch.setenv("MA3_DATABASE_URL", test_url)
        monkeypatch.setattr(settings, "database_url", test_url)
    else:
        db_path = tmp_path / "ma3-test.db"
        monkeypatch.setenv("MA3_DATABASE_URL", f"sqlite:///{db_path}")
        monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")

    monkeypatch.setenv("MA3_DEV_AUTH", "1")
    monkeypatch.setenv("MA3_DEV_API_KEY", "ma3dev")
    monkeypatch.setenv("MA3_DISABLE_EMBEDDINGS", "1")
    monkeypatch.setattr(settings, "dev_auth", True)
    monkeypatch.setattr(settings, "dev_api_key", "ma3dev")
    monkeypatch.setattr(settings, "disable_embeddings", True)
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")
    initialize_database()
    if _ci_postgres_admin is not None:
        _truncate_postgres_public_tables()
        initialize_database()
    from app.storage import db as _db

    _db.set_library_write_buffer_hours(settings.default_library_id, 0)

    from app.main import app

    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


@pytest.fixture(scope="session")
def deploy_base_url() -> str:
    return os.environ.get("MA3_BASE_URL", "https://ma3.io").rstrip("/")


@pytest.fixture(scope="session")
def deploy_api_key() -> str:
    return os.environ.get("MA3_API_KEY", "ma3dev")


@pytest.fixture(scope="session")
def deploy_http(deploy_base_url: str):
    timeout = float(os.environ.get("MA3_HTTP_TIMEOUT", "30"))
    with httpx.Client(base_url=deploy_base_url, timeout=timeout, trust_env=False) as client:
        yield client
