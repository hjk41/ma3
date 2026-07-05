from __future__ import annotations


def test_top_nav_peer_sections(authing_portal_client):
    for path in ("/ui/me/", "/ui/libraries/", "/ui/me/writes/", "/ui/me/votes/", "/ui/keys/"):
        response = authing_portal_client.get(path)
        assert response.status_code == 200, path


def test_subnav_only_on_me_pages(authing_portal_client):
    me = authing_portal_client.get("/ui/me/")
    assert "概览" in me.text
    assert "设置" in me.text
    assert "我的贡献" not in me.text
    assert "我的投票" not in me.text

    writes = authing_portal_client.get("/ui/me/writes/")
    assert '<nav class="subnav-links">' not in writes.text

    votes = authing_portal_client.get("/ui/me/votes/")
    assert '<nav class="subnav-links">' not in votes.text


def test_libraries_page_title_is_chinese(authing_portal_client):
    response = authing_portal_client.get("/ui/libraries/")
    assert response.status_code == 200
    assert "<h1" in response.text and "库" in response.text
    assert "Libraries" not in response.text.split("<title>")[1].split("</title>")[0]
