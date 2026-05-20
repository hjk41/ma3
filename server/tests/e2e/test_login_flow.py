import asyncio
from types import SimpleNamespace
from starlette.datastructures import URL

from app.api.routes_auth import auth_callback, auth_login
from app.core.auth import VerifyResult, _principal_from_user_verify
from app.storage.repositories import PrincipalRepository


def _req(url):
    return SimpleNamespace(url=URL(url))


def test_login_flow_routes_and_principal_materialization(monkeypatch):
    monkeypatch.setattr("app.api.routes_auth.verify_sso_cookie", lambda token: VerifyResult("alice", "Alice"))
    login = asyncio.run(auth_login(_req("https://ma3.zhilicon.com/auth/login"), next="/ui/me"))
    assert login.status_code == 302
    assert "auth.zhilicon.com/login" in login.headers["location"]
    callback = asyncio.run(auth_callback(_req("https://ma3.zhilicon.com/auth/callback"), gateway_token="fake", return_to="/ui/me"))
    assert callback.status_code == 302
    assert "gateway_token=fake" in callback.headers["set-cookie"]
    principal = _principal_from_user_verify(VerifyResult("alice", "Alice"))
    assert principal.principal_id == "user:alice"
    assert PrincipalRepository().get("user:alice") is not None
