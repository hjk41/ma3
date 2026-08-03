"""Tier A Playwright portal smoke (local-auth). Cases P1–P12 per Fable design."""
from __future__ import annotations

import re

import pytest

pytestmark = pytest.mark.e2e


def test_p1_setup_gate_creates_owner(e2e_base_url: str, page, owner_creds: dict[str, str]) -> None:
    """P1: first visit hits setup; owner fixture already created admin."""
    page.goto(f"{e2e_base_url}/auth/logout", wait_until="domcontentloaded")
    page.goto(f"{e2e_base_url}/ui/me/", wait_until="domcontentloaded")
    # Owner exists → login gate, not setup
    assert "/auth/login" in page.url or "/ui/me/" in page.url
    page.goto(f"{e2e_base_url}/auth/login?next={e2e_base_url}/ui/me/", wait_until="domcontentloaded")
    form = page.locator('form[action$="/auth/login"]')
    form.locator('input[name="username"]').fill(owner_creds["username"])
    form.locator('input[name="password"]').fill(owner_creds["password"])
    form.locator('button[type="submit"]').click()
    page.wait_for_url("**/ui/me/**", timeout=15000)
    assert "E2E Owner" in page.content() or owner_creds["username"] in page.content().lower()


def test_p2_register_and_bad_password(e2e_base_url: str, page, owner_creds: dict[str, str]) -> None:
    """P2: wrong password re-renders HTML form (not JSON)."""
    page.goto(f"{e2e_base_url}/auth/logout", wait_until="domcontentloaded")
    page.goto(f"{e2e_base_url}/auth/login", wait_until="domcontentloaded")
    form = page.locator('form[action$="/auth/login"]')
    form.locator('input[name="username"]').fill(owner_creds["username"])
    form.locator('input[name="password"]').fill("wrong-password-xxx")
    form.locator('button[type="submit"]').click()
    page.wait_for_load_state("domcontentloaded")
    body = page.content()
    assert "<html" in body.lower()
    assert not body.strip().startswith("{")
    assert 'name="password"' in body or page.locator('form[action$="/auth/login"]').count() == 1
    assert "password" in body.lower() or "密码" in body or "错误" in body or "invalid" in body.lower()


def test_p3_dashboard_stat_cards(e2e_base_url: str, page, login_as, owner_creds: dict[str, str]) -> None:
    """P3: dashboard + Records card → writes."""
    login_as(owner_creds["username"], owner_creds["password"])
    page.goto(f"{e2e_base_url}/ui/me/", wait_until="domcontentloaded")
    html = page.content()
    assert "/ui/me/writes/" in html
    page.locator('a[href*="/ui/me/writes/"]').first.click()
    page.wait_for_url("**/ui/me/writes/**", timeout=15000)


def test_p4_nav_and_no_observatory_for_member(
    e2e_base_url: str, page, login_as, member_creds: dict[str, str]
) -> None:
    """P4: top nav present; non-admin has no Observatory link."""
    login_as(member_creds["username"], member_creds["password"])
    page.goto(f"{e2e_base_url}/ui/me/", wait_until="domcontentloaded")
    html = page.content()
    assert "/ui/libraries/" in html or "Libraries" in html or "库" in html
    assert "/ui/keys/" in html
    # Observatory may appear as text in docs; require no privileged nav href for member
    assert 'href="/ui/observatory/"' not in html and 'href="/ui/observatory"' not in html.replace(
        e2e_base_url, ""
    )


def test_p5_observatory_403_html(
    e2e_base_url: str, page, login_as, member_creds: dict[str, str]
) -> None:
    """P5: non-admin Observatory → HTML 403."""
    login_as(member_creds["username"], member_creds["password"])
    resp = page.goto(f"{e2e_base_url}/ui/observatory/", wait_until="domcontentloaded")
    assert resp is not None
    assert resp.status == 403 or "403" in page.content() or "Forbidden" in page.content() or "禁止" in page.content()
    assert "<html" in page.content().lower()


def test_p6_writes_sort_links(e2e_base_url: str, page, login_as, owner_creds: dict[str, str]) -> None:
    """P6: writes sort headers are real links."""
    login_as(owner_creds["username"], owner_creds["password"])
    page.goto(f"{e2e_base_url}/ui/me/writes/", wait_until="domcontentloaded")
    links = page.locator('a[href*="sort="], a[href*="order="], th a[href*="/ui/me/writes"]')
    # At least one sortable header link, or status filter links
    filters = page.locator('a[href*="status="]')
    assert links.count() + filters.count() >= 1
    target = filters.first if filters.count() else links.first
    href = target.get_attribute("href") or ""
    target.click()
    page.wait_for_load_state("domcontentloaded")
    assert "/ui/me/writes" in page.url
    assert "&lt;a" not in page.content()


def test_p7_batch_empty_selection(e2e_base_url: str, page, login_as, owner_creds: dict[str, str]) -> None:
    """P7: empty batch submit → HTML redirect/message, not bare JSON."""
    login_as(owner_creds["username"], owner_creds["password"])
    page.goto(f"{e2e_base_url}/ui/me/writes/", wait_until="domcontentloaded")
    form = page.locator("#writes-batch-form, form[action*='/ui/me/writes/batch']")
    if form.count() == 0:
        pytest.skip("batch form not present on empty writes page")
    # Prefer a non-destructive action if present
    btn = form.locator('button[type="submit"]').first
    btn.click()
    page.wait_for_load_state("domcontentloaded")
    body = page.content()
    assert "<html" in body.lower()
    assert not body.strip().startswith("{")


def test_p8_key_lifecycle(e2e_base_url: str, page, login_as, owner_creds: dict[str, str]) -> None:
    """P8: create → detail ma3k_ + copy → rename → delete with confirm."""
    login_as(owner_creds["username"], owner_creds["password"])
    page.goto(f"{e2e_base_url}/ui/keys/", wait_until="domcontentloaded")
    label = "e2e-portal-key"
    page.locator('form[action$="/ui/keys/create"] input[name="label"]').fill(label)
    page.locator('form[action$="/ui/keys/create"] button[type="submit"]').click()
    page.wait_for_url(re.compile(r"/ui/keys/key_"), timeout=15000)
    html = page.content()
    assert "ma3k_" in html
    assert "ma3CopyFrom" in html
    renamed = label + "-renamed"
    page.locator('form[action$="/edit"] input[name="label"]').fill(renamed)
    grant = page.locator('form[action$="/edit"] select[name="grant_personal"]')
    if grant.count():
        grant.select_option(index=0)
    page.locator('form[action$="/edit"] button[type="submit"]').first.click()
    page.wait_for_load_state("domcontentloaded")
    assert renamed in page.content()
    page.on("dialog", lambda d: d.accept())
    page.locator(".danger-zone form button[type='submit'], .danger-zone button").first.click()
    page.wait_for_url(re.compile(r"/ui/keys/?$"), timeout=15000)
    assert renamed not in page.content()
    keys_api = page.evaluate(
        """async (base) => {
            const r = await fetch(base + '/api/keys', { credentials: 'include' });
            return r.json();
        }""",
        e2e_base_url,
    )
    assert not any(k.get("label") == renamed for k in keys_api.get("keys", []))


def test_p9_votes_page(e2e_base_url: str, page, login_as, owner_creds: dict[str, str]) -> None:
    login_as(owner_creds["username"], owner_creds["password"])
    page.goto(f"{e2e_base_url}/ui/me/votes/", wait_until="domcontentloaded")
    assert page.locator("body").count() == 1
    assert "vote" in page.content().lower() or "票" in page.content() or "filter" in page.content().lower() or "筛选" in page.content()


def test_p10_libraries_nav(e2e_base_url: str, page, login_as, owner_creds: dict[str, str]) -> None:
    login_as(owner_creds["username"], owner_creds["password"])
    page.goto(f"{e2e_base_url}/ui/libraries/", wait_until="domcontentloaded")
    link = page.locator('a[href*="/ui/libraries/"]').first
    if link.count() == 0:
        pytest.skip("no library links yet")
    href = link.get_attribute("href")
    assert href
    link.click()
    page.wait_for_load_state("domcontentloaded")
    assert "/ui/libraries/" in page.url


def test_p11_logout(e2e_base_url: str, page, login_as, owner_creds: dict[str, str]) -> None:
    login_as(owner_creds["username"], owner_creds["password"])
    assert page.request.get(f"{e2e_base_url}/auth/whoami").status == 200
    page.goto(f"{e2e_base_url}/auth/logout", wait_until="domcontentloaded")
    who = page.request.get(f"{e2e_base_url}/auth/whoami")
    assert who.status != 200
    page.goto(f"{e2e_base_url}/ui/me/", wait_until="domcontentloaded")
    assert "/auth/login" in page.url or "/ui/setup" in page.url


def test_p12_locale_switch(e2e_base_url: str, page, login_as, owner_creds: dict[str, str]) -> None:
    login_as(owner_creds["username"], owner_creds["password"])
    page.goto(f"{e2e_base_url}/ui/me/?lang=en-US", wait_until="domcontentloaded")
    assert page.locator("body").count() == 1
    en = page.content()
    page.goto(f"{e2e_base_url}/ui/me/?lang=zh-CN", wait_until="domcontentloaded")
    zh = page.content()
    assert page.locator("body").count() == 1
    # Pages should render without server error banners
    assert "Internal Server Error" not in en
    assert "Internal Server Error" not in zh
