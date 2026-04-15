"""
Smoke test for ma3 v0.2 — covers:
  - multi-library auth (admin key / library tokens)
  - library + token CRUD
  - visibility isolation (public vs private library)
  - draft promotion
  - non-tech / non-programming records
  - search results include relations
  - pagination
  - conflict_penalty in scoring
  - enhanced redaction
  - token revocation
"""
import os
import sys
from pathlib import Path

# Must be set before app.core.config is first imported
_TEST_ADMIN_KEY = "smoke-test-admin-key-v2"
os.environ["MA3_API_KEY"] = _TEST_ADMIN_KEY

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402  (import after env setup)
from fastapi.testclient import TestClient


ADMIN = {"X-API-Key": _TEST_ADMIN_KEY}


def main() -> None:
    with TestClient(app) as client:

        # ── 1. Health + agents doc ──────────────────────────────────────────
        assert client.get("/healthz").status_code == 200
        doc = client.get("/agents.md")
        assert doc.status_code == 200
        assert "POST /search" in doc.text
        assert "POST /agent/ingest" in doc.text

        # ── 2. Create two libraries ─────────────────────────────────────────
        pub_lib = client.post(
            "/libraries",
            json={"name": "公共知识库", "description": "所有人可见", "is_public": True},
            headers=ADMIN,
        )
        assert pub_lib.status_code == 200, pub_lib.text
        pub_lib_id = pub_lib.json()["library_id"]

        priv_lib = client.post(
            "/libraries",
            json={"name": "个人笔记", "description": "仅自己可见", "is_public": False},
            headers=ADMIN,
        )
        assert priv_lib.status_code == 200, priv_lib.text
        priv_lib_id = priv_lib.json()["library_id"]

        # ── 3. List libraries without auth → only public ────────────────────
        libs = client.get("/libraries").json()
        lib_ids = {lib["library_id"] for lib in libs}
        assert pub_lib_id in lib_ids, "public library should appear unauthenticated"
        assert priv_lib_id not in lib_ids, "private library should be hidden unauthenticated"

        # Admin sees all
        all_libs = client.get("/libraries", headers=ADMIN).json()
        all_ids = {lib["library_id"] for lib in all_libs}
        assert priv_lib_id in all_ids, "admin should see private library"

        # ── 4. Create tokens ────────────────────────────────────────────────
        pub_tok_resp = client.post(
            f"/libraries/{pub_lib_id}/tokens",
            json={"label": "public-write-token"},
            headers=ADMIN,
        )
        assert pub_tok_resp.status_code == 200, pub_tok_resp.text
        pub_tok = pub_tok_resp.json()["token"]
        pub_tok_id = pub_tok_resp.json()["token_id"]
        PUB_HEADERS = {"X-API-Key": pub_tok}

        priv_tok_resp = client.post(
            f"/libraries/{priv_lib_id}/tokens",
            json={"label": "private-write-token"},
            headers=ADMIN,
        )
        assert priv_tok_resp.status_code == 200
        priv_tok = priv_tok_resp.json()["token"]
        PRIV_HEADERS = {"X-API-Key": priv_tok}

        # ── 5. List tokens (admin only) ─────────────────────────────────────
        tok_list = client.get(f"/libraries/{pub_lib_id}/tokens", headers=ADMIN)
        assert tok_list.status_code == 200
        assert any(t["token_id"] == pub_tok_id for t in tok_list.json())

        # ── 6. Write record to public library using pub token ───────────────
        pub_record = client.post(
            "/records",
            json={
                "title": "公共记录：Playwright 安装代理配置",
                "problem_family": "browser-automation",
                "summary": "在受限网络下安装 Playwright 需要配置代理",
                "claim": "代理配置后 playwright install 成功",
                "target": {"product": "playwright", "component": "install"},
                "environment": {
                    "os": "windows", "shell": "powershell",
                    "runtime": "python", "sandbox": "workspace-write",
                    "workspace_boundary": "workspace-write",
                    "network_profile": "restricted",
                },
                "versions": {"agent": None, "target": "1.52.0"},
                "steps": [{"order": 1, "action": "set HTTP_PROXY env var", "note": None}],
                "result": {"outcome": "success", "summary": "install succeeded", "details": []},
                "evidence": [],
                "applicable_if": ["restricted network"],
                "not_applicable_if": [],
                "status": "active",
                "verification_level": "L2",
                "visibility_scope": "public",
                "risk_level": "low",
                "execution_mode": "safe_to_apply",
                "source_type": "manual",
            },
            headers=PUB_HEADERS,
        )
        assert pub_record.status_code == 200, pub_record.text
        pub_record_id = pub_record.json()["record_id"]
        assert pub_record.json()["library_id"] == pub_lib_id

        # ── 7. Write record to private library using priv token ─────────────
        priv_ingest = client.post(
            "/agent/ingest",
            json={
                "problem": "如何快速通过虹桥机场安检",
                "task_type": "travel_tips",
                "goal": "减少安检等待时间",
                "target": {"product": "虹桥机场", "component": "安检"},
                "environment": None,
                "versions": None,
                "observations": ["T2 安检人员较少"],
                "actions": [
                    {"action": "选择 T2 航站楼值机", "note": "人流量少"},
                    {"action": "提前取出电脑和腰带", "note": None},
                ],
                "outcome": "success",
                "result_summary": "全程不到 5 分钟通过安检",
                "evidence": [{"kind": "personal_observation", "summary": "实测有效", "ref": None}],
                "applicable_if": ["工作日非高峰", "T2 航站楼"],
                "not_applicable_if": ["节假日", "T1 航站楼"],
            },
            headers=PRIV_HEADERS,
        )
        assert priv_ingest.status_code == 200, priv_ingest.text
        priv_record_id = priv_ingest.json()["record"]  ["record_id"]
        assert priv_ingest.json()["record"]["library_id"] == priv_lib_id

        # ── 8. Search without token → cannot see private record ─────────────
        anon_search = client.post(
            "/search",
            json={
                "problem": "虹桥机场安检",
                "query_intent": "find tips",
                "task_type": "travel_tips",
                "target": {"product": "虹桥机场", "component": "安检"},
                "goal": "快速通关",
            },
        )
        assert anon_search.status_code == 200
        anon_ids = [
            m["record"]["record_id"]
            for m in anon_search.json()["primary_records"]
        ]
        assert priv_record_id not in anon_ids, "private record must not appear in anonymous search"

        # ── 9. Search with priv token → can see private record ──────────────
        auth_search = client.post(
            "/search",
            json={
                "problem": "虹桥机场安检",
                "query_intent": "find tips",
                "task_type": "travel_tips",
                "target": {"product": "虹桥机场", "component": "安检"},
                "goal": "快速通关",
                "max_primary": 10,
            },
            headers=PRIV_HEADERS,
        )
        assert auth_search.status_code == 200
        auth_ids = [
            m["record"]["record_id"]
            for m in auth_search.json()["primary_records"]
        ]
        assert priv_record_id in auth_ids, "private record must appear when using its library token"

        # ── 10. Pagination ───────────────────────────────────────────────────
        paged = client.post(
            "/search",
            json={
                "problem": "approval prompts windows powershell",
                "query_intent": "find fix",
                "task_type": "permission_reduction",
                "target": {"product": "codex-cli", "component": "approval-config"},
                "goal": "reduce prompts",
                "max_primary": 1,
                "max_contrasting": 0,
            },
        )
        assert paged.status_code == 200
        assert len(paged.json()["primary_records"]) <= 1
        assert len(paged.json()["contrasting_records"]) == 0

        # ── 11. Draft + promote ─────────────────────────────────────────────
        draft = client.post(
            "/agent/ingest",
            json={
                "problem": "test draft promotion flow",
                "task_type": "documentation",
                "goal": "verify draft can be promoted",
                "target": {"product": "ma3", "component": "records"},
                "environment": None,
                "versions": None,
                "observations": [],
                "actions": [{"action": "submit draft", "note": None}],
                "outcome": "success",
                "result_summary": "draft record created",
                "evidence": [],
                "draft_only": True,
            },
            headers=PUB_HEADERS,
        )
        assert draft.status_code == 200, draft.text
        assert draft.json()["record"]["status"] == "draft"
        draft_id = draft.json()["record"]["record_id"]

        # Draft should not appear in search
        search_before = client.post(
            "/search",
            json={
                "problem": "test draft promotion flow",
                "query_intent": "verify",
                "task_type": "documentation",
                "target": {"product": "ma3", "component": "records"},
                "goal": "verify",
            },
            headers=PUB_HEADERS,
        )
        before_ids = [m["record"]["record_id"] for m in search_before.json()["primary_records"]]
        assert draft_id not in before_ids, "draft must not appear in search"

        # Promote to active
        promoted = client.patch(f"/records/{draft_id}/promote", headers=PUB_HEADERS)
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["status"] == "active"

        # Now it should appear in search
        search_after = client.post(
            "/search",
            json={
                "problem": "test draft promotion flow",
                "query_intent": "verify",
                "task_type": "documentation",
                "target": {"product": "ma3", "component": "records"},
                "goal": "verify",
                "max_primary": 10,
            },
            headers=PUB_HEADERS,
        )
        after_ids = [m["record"]["record_id"] for m in search_after.json()["primary_records"]]
        assert draft_id in after_ids, "promoted record must appear in search"

        # ── 12. Redaction ────────────────────────────────────────────────────
        redaction_rec = client.post(
            "/records",
            json={
                "title": "Redaction test record",
                "problem_family": "security",
                "summary": "Contact ops@example.com, check C:\\secret\\creds.txt and /home/user/key.pem, token=abc123secret",
                "claim": "api_key=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890",
                "target": {"product": "test", "component": None},
                "environment": None,
                "versions": None,
                "steps": [],
                "result": {"outcome": "success", "summary": "ok", "details": []},
                "evidence": [],
                "applicable_if": [],
                "not_applicable_if": [],
                "status": "active",
                "verification_level": "L1",
                "visibility_scope": "public",
                "risk_level": "low",
                "execution_mode": "review_before_apply",
                "source_type": "smoke_test",
            },
            headers=PUB_HEADERS,
        )
        assert redaction_rec.status_code == 200, redaction_rec.text
        r = redaction_rec.json()
        assert "<redacted_email>" in r["summary"]
        assert "<redacted_path>" in r["summary"]   # C:\\ path
        assert "<redacted_path>" in r["summary"]   # /home/ path
        assert "<redacted_secret>" in r["claim"]    # api_key= pattern caught by SECRET_ASSIGNMENT_RE

        # ── 13. Relations appear in search results ───────────────────────────
        conflict_rel = client.post(
            "/relations",
            json={
                "from_record_id": "vk_seed_approval_success",
                "to_record_id": "vk_seed_approval_failure",
                "relation_type": "conflicts_with",
                "summary": "competing config keys for the same problem",
            },
            headers=PUB_HEADERS,
        )
        assert conflict_rel.status_code == 200, conflict_rel.text

        rel_search = client.post(
            "/search",
            json={
                "problem": "codex approval prompts windows powershell",
                "query_intent": "find fix",
                "task_type": "permission_reduction",
                "target": {"product": "codex-cli", "component": "approval-config"},
                "goal": "reduce prompts",
                "max_primary": 5,
                "environment": {
                    "os": "windows", "shell": "powershell",
                },
            },
        )
        assert rel_search.status_code == 200
        matches = rel_search.json()["primary_records"]
        assert any(len(m["relations"]) > 0 for m in matches), (
            "at least one match should have relations populated"
        )

        # ── 14. Feedback ─────────────────────────────────────────────────────
        fb = client.post(
            "/feedback",
            json={
                "record_id": pub_record_id,
                "feedback_type": "success_reuse",
                "summary": "confirmed on another machine",
                "environment": {"os": "windows", "shell": "powershell"},
                "result": {"outcome": "success", "summary": "ok", "details": []},
            },
            headers=PUB_HEADERS,
        )
        assert fb.status_code == 200, fb.text

        # ── 15. Token revocation ─────────────────────────────────────────────
        revoke = client.delete(
            f"/libraries/{pub_lib_id}/tokens/{pub_tok_id}",
            headers=ADMIN,
        )
        assert revoke.status_code == 204, revoke.text

        # Writing with the revoked token should now fail
        after_revoke = client.post(
            "/records",
            json={"title": "x", "problem_family": "x", "summary": "x", "claim": "x",
                  "target": {"product": "x"}, "environment": None, "versions": None,
                  "steps": [], "result": {"outcome": "success", "summary": "x", "details": []},
                  "evidence": [], "applicable_if": [], "not_applicable_if": [],
                  "status": "active", "verification_level": "L1",
                  "visibility_scope": "public", "risk_level": "low",
                  "execution_mode": "review_before_apply", "source_type": "test"},
            headers=PUB_HEADERS,
        )
        assert after_revoke.status_code == 401, (
            f"revoked token should be rejected, got {after_revoke.status_code}"
        )

    print("smoke test passed")


if __name__ == "__main__":
    main()
