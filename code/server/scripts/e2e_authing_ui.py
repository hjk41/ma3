#!/usr/bin/env python3
"""Browser E2E: Observatory login, logout, Authing account (password change) page."""
from __future__ import annotations

import os
import re
import sys

BASE_URL = os.environ.get("MA3_E2E_BASE_URL", "https://ma3.io").rstrip("/")
TEST_USER = os.environ.get("AUTHING_TEST_USER", "")
TEST_PASS = os.environ.get("AUTHING_TEST_PASS", "")
TIMEOUT_MS = int(os.environ.get("MA3_E2E_TIMEOUT_MS", "60000"))


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _ok(msg: str) -> None:
    print(f"OK: {msg}")


def _authing_login(page) -> None:
    """Complete Authing hosted login (phone + password)."""
    page.wait_for_timeout(4000)

    # Authing default is SMS; switch to password tab (EN or CN UI).
    for tab in ("Password", "密码登录", "账号密码登录"):
        try:
            loc = page.get_by_role("tab", name=tab)
            if loc.is_visible(timeout=3000):
                loc.click()
                break
        except Exception:
            try:
                loc = page.get_by_text(tab, exact=False).first
                if loc.is_visible(timeout=1500):
                    loc.click()
                    break
            except Exception:
                pass

    page.wait_for_timeout(800)

    filled_user = False
    for sel in (
        'input[placeholder*="Phone"]',
        'input[placeholder*="手机"]',
        'input[type="tel"]',
        'input[name="phone"]',
        'input[type="text"]',
    ):
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=1500):
                el.fill(TEST_USER)
                filled_user = True
                break
        except Exception:
            continue
    if not filled_user:
        _fail("could not find phone/username input on Authing login page")

    try:
        page.locator('input[type="password"]').first.fill(TEST_PASS, timeout=5000)
    except Exception as exc:
        _fail(f"could not fill password: {exc}")

    for label in ("Sign In", "登录", "登 录", "Log in", "Login"):
        try:
            btn = page.get_by_role("button", name=re.compile(label, re.I)).first
            if btn.is_visible(timeout=1500):
                btn.click()
                break
        except Exception:
            continue
    else:
        page.locator('button[type="submit"]').first.click()

    page.wait_for_url(
        re.compile(rf"{re.escape(BASE_URL.replace('http://', '').replace('https://', ''))}|/auth/callback|/ui/observatory", re.I),
        timeout=TIMEOUT_MS,
    )
    page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)


def main() -> None:
    if not TEST_USER or not TEST_PASS:
        _fail("set AUTHING_TEST_USER and AUTHING_TEST_PASS in environment")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _fail("install playwright: pip install playwright && playwright install chromium")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(TIMEOUT_MS)

        # 1) Unauthenticated Observatory redirects to login
        page.goto(f"{BASE_URL}/ui/observatory/", wait_until="domcontentloaded")
        if "/auth/login" not in page.url and "authing" not in page.url.lower():
            _fail(f"expected login redirect, got {page.url}")
        _ok("unauthenticated observatory redirects to login")

        # 2) Login via Authing (direct redirect)
        if "/auth/login" in page.url:
            page.wait_for_url(re.compile(r"authing|/auth/callback|/ui/observatory", re.I), timeout=TIMEOUT_MS)
        if "authing" in page.url.lower():
            _authing_login(page)
            page.wait_for_url(re.compile(rf"{re.escape(BASE_URL)}", re.I), timeout=TIMEOUT_MS)

        if "/ui/observatory" not in page.url:
            page.goto(f"{BASE_URL}/ui/observatory/", wait_until="networkidle")

        content = page.content()
        if "Observatory" not in content and "观测" not in content and "ma3" not in content.lower():
            _fail(f"observatory page missing after login; url={page.url}")
        _ok("logged in and observatory page loads")

        # 3) whoami via fetch in browser context
        whoami = page.evaluate(
            """async (base) => {
                const r = await fetch(base + '/auth/whoami', { credentials: 'include' });
                return { status: r.status, body: await r.text() };
            }""",
            BASE_URL,
        )
        if whoami["status"] != 200:
            _fail(f"/auth/whoami returned {whoami['status']}: {whoami['body'][:200]}")
        _ok(f"whoami authenticated: {whoami['body'][:120]}")

        # 4) API Keys — create via HTML form (requires python-multipart on server)
        page.goto(f"{BASE_URL}/ui/keys/", wait_until="networkidle")
        if "/auth/login" in page.url:
            _fail(f"keys page requires login; got {page.url}")
        page.locator('form[action$="/ui/keys/create"] input[name="label"]').fill("e2e-authing-key")
        page.locator('form[action$="/ui/keys/create"]').locator('button[type="submit"]').click()
        page.wait_for_url(re.compile(r"/ui/keys/key_"), timeout=TIMEOUT_MS)
        keys_html = page.content()
        if "Internal Server Error" in keys_html or "500" in page.title():
            _fail("POST /ui/keys/create returned error page")
        if "e2e-authing-key" not in keys_html:
            _fail("created key label missing on detail page after form submit")
        if "ma3k_" not in keys_html:
            _fail("created key plaintext missing on detail page (expected ma3k_ prefix)")
        if "ma3CopyFrom" not in keys_html:
            _fail("copy helper script missing on detail page")
        _ok("keys form create lands on detail page with plaintext")

        if "撤销" in keys_html:
            _fail("keys page still shows 撤销; expected 删除")

        # Rename + grants via unified save on detail page
        page.locator('form[action$="/edit"] input[name="label"]').fill("e2e-authing-key-renamed")
        page.select_option('form[action$="/edit"] select[name="grant_personal"]', "reader")
        page.locator('form[action$="/edit"] button[type="submit"]:has-text("保存")').click()
        page.wait_for_url(re.compile(r"/ui/keys/key_.*saved=1"), timeout=TIMEOUT_MS)
        if "e2e-authing-key-renamed" not in page.content():
            _fail("renamed key label missing on detail page after unified save")
        _ok("keys unified save on detail page")

        # List page has copy/delete actions
        page.goto(f"{BASE_URL}/ui/keys/", wait_until="networkidle")
        if "cell-actions" not in page.content():
            _fail("list page missing cell-actions column")
        _ok("list page shows copy/delete actions")

        # Delete on detail page danger zone
        page.get_by_role("link", name="e2e-authing-key-renamed").click()
        page.on("dialog", lambda d: d.accept())
        page.locator(".danger-zone form button:has-text('删除')").click()
        page.wait_for_url(re.compile(r"/ui/keys/?$"), timeout=TIMEOUT_MS)
        if "e2e-authing-key-renamed" in page.content():
            _fail("deleted key still visible on list")
        keys_api = page.evaluate(
            """async (base) => {
                const r = await fetch(base + '/api/keys', { credentials: 'include' });
                return r.json();
            }""",
            BASE_URL,
        )
        if any(k.get("label") == "e2e-authing-key-renamed" for k in keys_api.get("keys", [])):
            _fail("deleted key still returned by GET /api/keys")
        _ok("keys delete via detail page")

        # 5) Account / password change entry -> Authing user center
        page.goto(f"{BASE_URL}/auth/account", wait_until="domcontentloaded")
        page.wait_for_url(re.compile(r"authing\.cn", re.I), timeout=TIMEOUT_MS)
        acct_html = page.content().lower()
        if not any(k in acct_html for k in ("密码", "password", "账户", "account", "安全")):
            _fail(f"Authing account page missing password/account UI; url={page.url}")
        _ok(f"account redirect opens Authing user center ({page.url[:80]})")

        # 6) Logout — clears ma3 session and Authing SSO (RP-initiated logout)
        page.goto(f"{BASE_URL}/auth/logout", wait_until="networkidle", timeout=TIMEOUT_MS)
        whoami_resp = context.request.get(f"{BASE_URL}/auth/whoami")
        if whoami_resp.status == 200:
            _fail("still authenticated after logout")
        page.goto(f"{BASE_URL}/ui/observatory/", wait_until="networkidle", timeout=TIMEOUT_MS)
        if "/auth/login" not in page.url and "authing" not in page.url.lower():
            _fail(f"observatory did not require login after logout; url={page.url}")
        if context.request.get(f"{BASE_URL}/auth/whoami").status == 200:
            _fail("whoami still 200 after logout and observatory redirect")
        _ok("logout clears session; observatory requires login again")

        browser.close()

    print("\nAll E2E checks passed.")


if __name__ == "__main__":
    main()
