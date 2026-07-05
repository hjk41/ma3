from __future__ import annotations

from app.core.config import settings
from tests.helpers.mcp_client import McpClient

_EVIDENCE = [{"kind": "test", "summary": "votes portal test"}]
_ORIGIN = {"Origin": "http://testserver"}


def _seed_active_record(client, portal_user, monkeypatch) -> str:
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
    created = client.post("/api/keys", json={"label": "votes-test"}, headers=_ORIGIN)
    body = created.json()
    mcp = McpClient(client, api_key=body["plaintext_key"])
    report = mcp.structured(
        "ma3_report",
        {
            "problem": "votes list test record",
            "outcome": "resolved",
            "result_summary": "for votes portal test",
            "library_id": settings.default_library_id,
            "evidence": _EVIDENCE,
        },
    )
    return report["record_id"]


def test_votes_page_has_filter_and_footer(authing_portal_client):
    response = authing_portal_client.get("/ui/me/votes/")
    assert response.status_code == 200
    text = response.text
    assert "filter-pills" in text
    assert "list-footer" in text
    assert "投票" in text
    assert '<nav class="subnav-links">' not in text


def test_votes_after_feedback(authing_portal_client, portal_user, monkeypatch):
    record_id = _seed_active_record(authing_portal_client, portal_user, monkeypatch)
    vote = authing_portal_client.post(
        f"/ui/records/{record_id}/feedback?vote=up",
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert vote.status_code in {303, 302}
    page = authing_portal_client.get("/ui/me/votes/")
    assert page.status_code == 200
    assert "votes list test record" in page.text
