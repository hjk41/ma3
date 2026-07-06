from __future__ import annotations

from app.api.ui_i18n import catalog


def test_default_locale_is_zh_cn(authing_portal_client):
    response = authing_portal_client.get("/ui/me/")
    assert response.status_code == 200
    text = response.text
    assert '<html lang="zh-CN">' in text
    assert "我的主页" in text
    assert "库" in text
    assert "记录" in text
    assert "投票" in text
    assert "退出" in text


def test_query_param_switches_to_en_and_sets_cookie(authing_portal_client):
    response = authing_portal_client.get("/ui/me/?lang=en-US")
    assert response.status_code == 200
    text = response.text
    assert '<html lang="en-US">' in text
    assert "Home" in text
    assert "Libraries" in text
    assert "Records" in text
    assert "Votes" in text
    assert "Sign out" in text
    set_cookie = response.headers.get("set-cookie", "")
    assert "ma3_locale=en-US" in set_cookie


def test_cookie_persists_english_writes_page(authing_portal_client):
    client = authing_portal_client
    client.cookies.set("ma3_locale", "en-US")
    response = client.get("/ui/me/writes/")
    assert response.status_code == 200
    text = response.text
    assert '<html lang="en-US">' in text
    assert "Records" in text
    assert "All" in text
    assert "Published" in text
    assert "Pending" in text
    assert "Deleted" in text
    assert "Batch actions" in text
    assert "No records" in text


def test_query_overrides_cookie_to_zh_cn(authing_portal_client):
    client = authing_portal_client
    client.cookies.set("ma3_locale", "en-US")
    response = client.get("/ui/me/votes/?lang=zh-CN")
    assert response.status_code == 200
    text = response.text
    assert '<html lang="zh-CN">' in text
    assert "投票" in text
    assert "赞同" in text
    assert "反对" in text
    assert "ma3_locale=zh-CN" in response.headers.get("set-cookie", "")


def test_accept_language_fallback_english(authing_portal_client):
    response = authing_portal_client.get(
        "/ui/me/",
        headers={"Accept-Language": "en-US,en;q=0.8,zh-CN;q=0.5"},
    )
    assert response.status_code == 200
    assert '<html lang="en-US">' in response.text
    assert "Home" in response.text


def test_unsupported_locale_falls_back_to_zh_cn(authing_portal_client):
    response = authing_portal_client.get("/ui/me/?lang=fr-FR")
    assert response.status_code == 200
    assert '<html lang="zh-CN">' in response.text
    assert "ma3_locale=fr" not in response.headers.get("set-cookie", "").lower()


def test_keys_page_english(authing_portal_client):
    client = authing_portal_client
    client.cookies.set("ma3_locale", "en-US")
    response = client.get("/ui/keys/")
    assert response.status_code == 200
    text = response.text
    assert "Key management" in text
    assert "Create new key" in text
    assert "Personal library" in text


def test_switcher_back_to_chinese_updates_cookie(authing_portal_client):
    client = authing_portal_client
    client.cookies.set("ma3_locale", "en-US")
    en_page = client.get("/ui/me/")
    assert en_page.status_code == 200
    assert "Home" in en_page.text
    assert "lang=zh-CN" in en_page.text
    zh_page = client.get("/ui/me/?lang=zh-CN")
    assert zh_page.status_code == 200
    assert '<html lang="zh-CN">' in zh_page.text
    assert "我的主页" in zh_page.text
    assert "ma3_locale=zh-CN" in zh_page.headers.get("set-cookie", "")
    follow_up = client.get("/ui/me/")
    assert follow_up.status_code == 200
    assert "我的主页" in follow_up.text


def test_catalog_completeness():
    zh = catalog("zh-CN")
    en = catalog("en-US")
    assert set(zh) == set(en)
    for key in zh:
        assert isinstance(zh[key], str) and zh[key]
        assert isinstance(en[key], str) and en[key]


def test_phase1_pages_have_no_missing_key_markers(authing_portal_client):
    paths = [
        "/ui/me/",
        "/ui/me/settings/",
        "/ui/me/writes/",
        "/ui/me/votes/",
        "/ui/keys/",
        "/ui/me/?lang=en-US",
        "/ui/me/settings/?lang=en-US",
        "/ui/me/writes/?lang=en-US",
        "/ui/me/votes/?lang=en-US",
        "/ui/keys/?lang=en-US",
    ]
    for path in paths:
        response = authing_portal_client.get(path)
        assert response.status_code == 200, path
        assert "[[" not in response.text, path
