"""Portal SSR HTML invariants — hard gates against rendering regressions.

See docs/08-quality/acceptance/v1-user-portal-ui.md (R series).
"""

from __future__ import annotations

from app.core.config import settings
from tests.helpers.mcp_client import McpClient

_EVIDENCE = [{"kind": "test", "summary": "portal html regression"}]
_ORIGIN = {"Origin": "http://testserver"}


def _assert_sort_headers_are_links(html: str) -> None:
    assert "&lt;a href=" not in html, "escaped anchor in table header — render_table must not esc() HTML headers"
    assert '<th><a href="' in html, "expected clickable sort links in <th>"


def _seed_buffered_write(authing_portal_client, portal_user, monkeypatch) -> None:
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

        resolver = lambda _req: u
        monkeypatch.setattr(session_mod, "resolve_session_user", resolver)
        monkeypatch.setattr(ui_session, "resolve_session_user", resolver)

    _patch_session(monkeypatch, user)
    monkeypatch.setattr(routes_keys, "resolve_session_user", lambda _req: user)
    from app.storage import db

    db.set_library_write_buffer_hours(settings.default_library_id, 24)
    created = authing_portal_client.post("/api/keys", json={"label": "html-regression"}, headers=_ORIGIN)
    mcp = McpClient(authing_portal_client, api_key=created.json()["plaintext_key"])
    mcp.structured(
        "ma3_report",
        {
            "problem": "html regression buffered row",
            "outcome": "resolved",
            "result_summary": "for sort header test",
            "evidence": _EVIDENCE,
        },
    )


def _seed_voted_record(authing_portal_client, portal_user, monkeypatch) -> None:
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

        resolver = lambda _req: u
        monkeypatch.setattr(session_mod, "resolve_session_user", resolver)
        monkeypatch.setattr(ui_session, "resolve_session_user", resolver)

    _patch_session(monkeypatch, user)
    monkeypatch.setattr(routes_keys, "resolve_session_user", lambda _req: user)
    created = authing_portal_client.post("/api/keys", json={"label": "votes-html-regression"}, headers=_ORIGIN)
    mcp = McpClient(authing_portal_client, api_key=created.json()["plaintext_key"])
    report = mcp.structured(
        "ma3_report",
        {
            "problem": "html regression vote row",
            "outcome": "resolved",
            "result_summary": "for votes sort header test",
            "library_id": settings.default_library_id,
            "evidence": _EVIDENCE,
        },
    )
    authing_portal_client.post(
        f"/ui/records/{report['record_id']}/feedback?vote=up",
        headers=_ORIGIN,
        follow_redirects=False,
    )


def test_writes_sort_headers_are_links(authing_portal_client, portal_user, monkeypatch):
    _seed_buffered_write(authing_portal_client, portal_user, monkeypatch)
    response = authing_portal_client.get("/ui/me/writes/?status=buffered")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    _assert_sort_headers_are_links(response.text)
    assert "sort=created_at" in response.text


def test_votes_sort_headers_are_links(authing_portal_client, portal_user, monkeypatch):
    _seed_voted_record(authing_portal_client, portal_user, monkeypatch)
    response = authing_portal_client.get("/ui/me/votes/")
    assert response.status_code == 200
    _assert_sort_headers_are_links(response.text)
    assert "sort=updated_at" in response.text


def test_portal_form_errors_are_html_not_json(authing_portal_client):
    """Batch POST with empty selection must redirect to HTML, not return JSON body."""
    response = authing_portal_client.post(
        "/ui/me/writes/batch/",
        data={"action": "publish", "status": "buffered"},
        headers={"Origin": "http://testserver"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "请先选择至少一条记录" in response.text
    assert "invalid batch request" not in response.text
    assert response.text.strip().startswith("<!DOCTYPE html>")


def test_writes_page_includes_batch_guard_script(authing_portal_client):
    response = authing_portal_client.get("/ui/me/writes/")
    assert response.status_code == 200
    assert "writes-batch-error" in response.text
    assert "writes-select-all" in response.text or "暂无记录" in response.text
