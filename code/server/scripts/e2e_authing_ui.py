#!/usr/bin/env python3
"""Browser E2E: Observatory login, logout, Authing account (password change) page."""
from __future__ import annotations

import os
import re
import sys
import time

BASE_URL = os.environ.get("MA3_E2E_BASE_URL", "http://192.168.31.202:8000").rstrip("/")
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

        # 2) Login via Authing
        if "/auth/login" in page.url:
            page.goto(page.url, wait_until="domcontentloaded")
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

        # 4) Account / password change entry -> Authing user center
        page.goto(f"{BASE_URL}/auth/account", wait_until="domcontentloaded")
        page.wait_for_url(re.compile(r"authing\.cn", re.I), timeout=TIMEOUT_MS)
        acct_html = page.content().lower()
        if not any(k in acct_html for k in ("密码", "password", "账户", "account", "安全")):
            _fail(f"Authing account page missing password/account UI; url={page.url}")
        _ok(f"account redirect opens Authing user center ({page.url[:80]})")

        # 5) Logout
        page.goto(f"{BASE_URL}/auth/logout", wait_until="domcontentloaded")
        time.sleep(1)
        page.goto(f"{BASE_URL}/ui/observatory/", wait_until="domcontentloaded")
        if "/ui/observatory/" in page.url and "Observatory" in page.content():
            who = page.evaluate(
                """async (base) => {
                    const r = await fetch(base + '/auth/whoami', { credentials: 'include' });
                    return r.status;
                }""",
                BASE_URL,
            )
            if who == 200:
                _fail("still authenticated after logout")
        if "/auth/login" not in page.url and "authing" not in page.url.lower():
            # may still be on observatory shell but gated
            who = page.evaluate(
                """async (base) => {
                    const r = await fetch(base + '/auth/whoami', { credentials: 'include' });
                    return r.status;
                }""",
                BASE_URL,
            )
            if who == 200:
                _fail(f"logout did not clear session; url={page.url}")
        _ok("logout clears session; observatory requires login again")

        browser.close()

    print("\nAll E2E checks passed.")


if __name__ == "__main__":
    main()
