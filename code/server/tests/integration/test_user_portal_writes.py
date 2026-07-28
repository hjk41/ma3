from __future__ import annotations

from app.core.config import settings
from app.storage import db
from tests.helpers.mcp_client import McpClient

_EVIDENCE = [{"kind": "test", "summary": "writes portal test"}]
_ORIGIN = {"Origin": "http://testserver"}


def _create_buffered_record(client, portal_user, monkeypatch) -> str:
    import app.api.routes_keys as routes_keys

    from app.auth.session import SessionUser

    user = SessionUser(
        principal_id=portal_user.principal_id,
        sub=portal_user.sub,
        display_name=portal_user.display_name,
        email=None,
        phone=None,
        is_admin=False,
    )

    def _patch_session(monkeypatch, u):
        import app.api.ui_session as ui_session
        import app.auth.session as session_mod
        import app.services.portal_actor_service as portal_actor_service

        resolver = lambda _req: u
        monkeypatch.setattr(session_mod, "resolve_session_user", resolver)
        monkeypatch.setattr(ui_session, "resolve_session_user", resolver)
        monkeypatch.setattr(portal_actor_service, "resolve_session_user", resolver)

    _patch_session(monkeypatch, user)
    monkeypatch.setattr(routes_keys, "resolve_session_user", lambda _req: user)
    db.set_library_write_buffer_hours(settings.default_library_id, 24)
    created = client.post("/api/keys", json={"label": "writes-test"}, headers=_ORIGIN)
    assert created.status_code == 200
    body = created.json()
    mcp = McpClient(client, api_key=body["plaintext_key"])
    report = mcp.structured(
        "ma3_report",
        {
            "problem": "writes list buffered row",
            "outcome": "resolved",
            "result_summary": "buffered for portal writes test",
            "evidence": _EVIDENCE,
        },
    )
    assert report["status"] == "buffered"
    return report["record_id"]


def test_writes_page_has_filter_sort_and_footer(authing_portal_client):
    response = authing_portal_client.get("/ui/me/writes/")
    assert response.status_code == 200
    text = response.text
    assert "filter-pills" in text
    assert "list-footer" in text
    assert "待发布" in text
    assert "已发布" in text
    assert "已删除" in text
    assert "共" in text and "条" in text
    assert "记录" in text
    assert '<nav class="subnav-links">' not in text


def test_writes_status_filter_buffered(authing_portal_client, portal_user, monkeypatch):
    record_id = _create_buffered_record(authing_portal_client, portal_user, monkeypatch)
    response = authing_portal_client.get("/ui/me/writes/?status=buffered")
    assert response.status_code == 200
    assert record_id in response.text
    assert "writes list buffered row" in response.text
    assert '<th><a href="' in response.text
    assert "sort=created_at" in response.text
    assert "&lt;a href=" not in response.text


def test_writes_batch_publish(authing_portal_client, portal_user, monkeypatch):
    record_id = _create_buffered_record(authing_portal_client, portal_user, monkeypatch)
    response = authing_portal_client.post(
        "/ui/me/writes/batch/",
        data={"action": "publish", "record_ids": record_id},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert response.status_code == 303
    from app.storage import db

    record = db.get_record(record_id)
    assert record is not None
    assert record.get("status") == "active"


def test_writes_batch_empty_selection_redirects_with_message(authing_portal_client):
    response = authing_portal_client.post(
        "/ui/me/writes/batch/",
        data={"action": "publish", "status": "buffered"},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    page = authing_portal_client.get(response.headers["location"])
    assert page.status_code == 200
    assert "请先选择至少一条记录" in page.text
    assert "invalid batch request" not in page.text


def test_writes_page_has_select_all_and_batch_script(authing_portal_client, portal_user, monkeypatch):
    _create_buffered_record(authing_portal_client, portal_user, monkeypatch)
    response = authing_portal_client.get("/ui/me/writes/?status=buffered")
    assert response.status_code == 200
    assert 'id="writes-select-all"' in response.text
    assert "writes-batch-error" in response.text


def test_writes_deleted_filter_shows_redacted_label(authing_portal_client, portal_user, monkeypatch):
    record_id = _create_buffered_record(authing_portal_client, portal_user, monkeypatch)
    publish = authing_portal_client.post(
        "/ui/me/writes/batch/",
        data={"action": "publish", "record_ids": record_id, "status": "buffered"},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert publish.status_code == 303
    delete = authing_portal_client.post(
        f"/ui/records/{record_id}/delete",
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert delete.status_code in {303, 307}
    response = authing_portal_client.get("/ui/me/writes/?status=deleted")
    assert response.status_code == 200
    assert "记录内容已完全删除，不可显示" in response.text
    assert "writes list buffered row" not in response.text


def test_stat_card_links_to_buffered_filter(authing_portal_client):
    response = authing_portal_client.get("/ui/me/")
    assert response.status_code == 200
    assert 'href="/ui/me/writes/?status=buffered"' in response.text or "status=buffered" in response.text
