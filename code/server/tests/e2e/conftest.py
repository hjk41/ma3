"""Playwright E2E fixtures: subprocess uvicorn + temp SQLite (local-auth, no OIDC)."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

SERVER_ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_healthz(base_url: str, timeout_s: float = 60.0) -> None:
    deadline = time.time() + timeout_s
    last_err = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/healthz", timeout=2) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_err = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"uvicorn not ready at {base_url}/healthz: {last_err}")


@pytest.fixture(scope="session")
def e2e_base_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    data_dir = tmp_path_factory.mktemp("ma3-e2e-data")
    db_path = data_dir / "ma3.db"
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update(
        {
            "MA3_DATABASE_URL": f"sqlite:///{db_path}",
            "MA3_DISABLE_EMBEDDINGS": "1",
            "MA3_LOCAL_AUTH": "1",
            "MA3_LOCAL_AUTH_OPEN_REGISTRATION": "1",
            "MA3_DEV_AUTH": "0",
            "MA3_AUTHING_ENABLED": "0",
            "MA3_AUTHING_ISSUER": "",
            "MA3_AUTHING_APP_ID": "",
            "MA3_AUTHING_APP_SECRET": "",
            "MA3_API_KEY_ENCRYPTION_SECRET": "e2e-portal-test-secret-32bytes!!",
            "MA3_PUBLIC_BASE_URL": base_url,
            "MA3_INSTANCE_ID": "ma3-e2e-portal",
            "PYTHONPATH": str(SERVER_ROOT),
        }
    )
    # Ensure OIDC env vars do not leak from the developer machine.
    for k in list(env):
        if k.startswith("MA3_OIDC_") or k.startswith("AUTHING_"):
            env.pop(k, None)

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--app-dir",
            str(SERVER_ROOT),
        ],
        cwd=str(SERVER_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_healthz(base_url)
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


@pytest.fixture(scope="session")
def owner_creds(e2e_base_url: str) -> dict[str, str]:
    """Create first admin via /ui/setup/ register form (Playwright once per session)."""
    from playwright.sync_api import sync_playwright

    username = "e2eowner"
    password = "password123"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{e2e_base_url}/ui/me/", wait_until="domcontentloaded")
        page.wait_for_url("**/ui/setup/**", timeout=15000)
        form = page.locator('form[action$="/auth/register"]')
        form.locator('input[name="username"]').fill(username)
        form.locator('input[name="password"]').fill(password)
        form.locator('input[name="password_confirm"]').fill(password)
        form.locator('input[name="display_name"]').fill("E2E Owner")
        form.locator('button[type="submit"]').click()
        page.wait_for_load_state("domcontentloaded")
        # After first register, setup wizard may still show; leave session cookies.
        who = page.request.get(f"{e2e_base_url}/auth/whoami")
        assert who.status == 200, who.text()
        browser.close()
    return {"username": username, "password": password, "display_name": "E2E Owner"}


@pytest.fixture(scope="session")
def member_creds(e2e_base_url: str, owner_creds: dict[str, str]) -> dict[str, str]:
    """Register a second non-admin user via HTTP (avoid nested sync Playwright)."""
    import http.cookiejar
    import urllib.parse
    import urllib.request

    username = "e2emember"
    password = "password123"
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    data = urllib.parse.urlencode(
        {
            "username": username,
            "password": password,
            "password_confirm": password,
            "display_name": "E2E Member",
            "next": f"{e2e_base_url}/ui/me/",
        }
    ).encode()
    req = urllib.request.Request(
        f"{e2e_base_url}/auth/register",
        data=data,
        method="POST",
        headers={"Origin": e2e_base_url, "Content-Type": "application/x-www-form-urlencoded"},
    )
    with opener.open(req, timeout=15) as resp:
        assert resp.status in (200, 303, 302), resp.status
    who_req = urllib.request.Request(f"{e2e_base_url}/auth/whoami")
    with opener.open(who_req, timeout=15) as who:
        import json

        body = json.loads(who.read().decode())
        assert body.get("is_admin") is False, body
    return {"username": username, "password": password}


@pytest.fixture
def login_as(e2e_base_url: str, page):
    def _login(username: str, password: str = "password123") -> None:
        page.goto(f"{e2e_base_url}/auth/logout", wait_until="domcontentloaded")
        page.goto(f"{e2e_base_url}/auth/login?next={e2e_base_url}/ui/me/", wait_until="domcontentloaded")
        form = page.locator('form[action$="/auth/login"]')
        form.locator('input[name="username"]').fill(username)
        form.locator('input[name="password"]').fill(password)
        form.locator('button[type="submit"]').click()
        page.wait_for_url("**/ui/me/**", timeout=15000)

    return _login
