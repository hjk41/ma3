# Design Review — 13 Self-Service Onboarding

> **Reviewer**: Composer (design review subagent)  
> **Document**: [`13-self-service-onboarding.md`](13-self-service-onboarding.md)  
> **Ground truth checked**: `routes_auth.py`, `routes_ui.py`, `db.py`, `write_audit_service.py`, `mcp_tool_service.py`, `seed_personal_library_key.py`, `principal_service.py`, `session.py`, `main.py`, ADR-011, design-08 §4.2/§6, acceptance `v1-personal-developer-journey.md`, `05-doc-code-mapping.md`  
> **Date**: 2026-07-04

---

## 1. Verdict

**ACCEPT-WITH-NITS**

The design is implementable with the existing stack, respects the minimal-diff principle, and correctly scopes v1 to Observatory-session key issuance while deferring MCP key tools and entitlement coupling. Two doc-level inconsistencies must be fixed before implementation starts; nothing requires architectural rework.

---

## 2. Blocking issues (must fix before implementation)

### B1 — Auth callback snippet contradicts §9 “login must not fail on library errors”

§6.2 shows:

```python
principal = ensure_user_principal(user)
ensure_personal_library(principal["principal_id"], user.display_name)
```

§9 explicitly requires: *Authing callback 中 `ensure_personal_library` 抛异常 → **不阻断登录**（try/except + log）*.

An implementer following §6.2 alone will block login on any DB/transient failure during first library creation.

**Fix**: Update §6.2 to match §9, e.g.:

```python
principal = ensure_user_principal(user)
try:
    ensure_personal_library(principal["principal_id"], user.display_name)
except Exception:
    logger.exception("ensure_personal_library failed during auth callback for %s", principal["principal_id"])
```

Also note that today `routes_auth.py` L62 discards the return value of `ensure_user_principal`; the assignment to `principal` is required (design is correct; current code is not).

---

### B2 — Wireframe “复制” button has no feasible no-JS implementation

§6.4 states UI follows the no-JS SSR form pattern (same rationale as POST-for-revoke). §7 wireframe shows a **[复制]** button next to the plaintext key. Clipboard copy requires JavaScript; a `<button>` with no handler does nothing.

**Fix** (pick one and document in §6.4 / §7):

1. **Preferred (minimal)**: Render plaintext in a `<input readonly>` or `<textarea readonly>` with `onclick="this.select()"` and label it “选中后 Ctrl+C 复制” — one inline handler, no framework.
2. **Pure SSR**: Drop the button; use a styled `<code>` block + explicit “手动选中复制” copy. Remove `[复制]` from the wireframe.

Do not ship a dead button.

---

## 3. Non-blocking nits

1. **`key_prefix` length vs design-08**: design-08 §4.2 specifies 8 characters (`ma3k_abcd…`); this doc uses 12 (`plaintext[:12]`). Both work; pick one and add a one-line note in §5 cross-referencing design-08 so implementers do not second-guess.

2. **Concurrent-create error handling**: §6.1 `except Exception` after `ensure_library` is broader than needed. Prefer catching SQLite `IntegrityError` / Postgres unique-violation only, then re-`find_personal_library`; re-raise everything else unchanged.

3. **Integration test auth fixture underspecified**: §13 says “`resolve_session_user` monkeypatch” but there is no existing pattern in `tests/integration/`. Add a sentence naming the fixture approach: e.g. `monkeypatch.setattr(settings, "authing_enabled", True)` + stub `resolve_session_user` returning a `SessionUser`, and a separate case with `authing_configured=False` for the 503 test. Without this, Phase O2/O3 tests will stall on first PR.

4. **§10.1 test rename**: `test_explicit_new_requires_confirmation` in `test_write_audit_and_delete.py` will invert behavior. §13 mentions the regression; add an explicit bullet to **rewrite** that test (expect 200 + `confirmation=agent_judged`, not 400).

5. **`library_selection_reason` on dry-run / replay**: §10.2 lists three `mcp_tool_service.py` branches — confirm replay path (idempotency hit) also emits the reason, or note it inherits from stored audit metadata only.

6. **UI CSS duplication**: “复用 routes_ui.py 的内联样式” implies copy-paste. Acceptable for v1 minimal diff; optional follow-up to extract a shared `_render_page_shell()` later (not in this slice).

7. **Nav discoverability**: Single “API Keys” link from Observatory is enough for v1; consider also linking back from `/ui/keys/` to `/ui/observatory/` in the banner (mirror record pages’ “返回概览”).

8. **Deploy path naming**: Acceptance A10 uses `/home/hct/ma3/server/scripts/` (deploy tree); source lives at `code/server/scripts/`. The design is correct for 202’s layout — add “(deploy tree, not source checkout)” once in §11.2 to avoid confusion.

9. **ADR-011 `prefix` vs `key_prefix`**: ADR-011 prose says `prefix`; implemented schema in design-08/code uses `key_prefix`. This doc correctly follows code; no action beyond awareness.

10. **`expires_at` mention in D3 intro vs §6.3 table**: D3 opening mentions optional `expires_at`; API table and UI omit it. Either drop from D3 or add “accepted in JSON, ignored in v1 UI” — trivial clarity.

---

## 4. What you agree with — top 3 strengths

1. **Idempotent personal library by `(kind, owner)` not deterministic id alone** — Correctly reuses seed-created libraries like `lib_personal_nova` without migration scripts or duplicate libraries. Verified against live DB shape (`owner_principal_id=user:nova-dev`). This is the highest-risk area and the design gets it right.

2. **D2 deferral of MCP key tools to v1.1** — Sound security reasoning: a leaked agent key must not be able to mint siblings before grant-subset validation exists. Observatory session as the sole v1 issuance path matches ADR-011 decision 2 and the actual bootstrap journey (human copies key into MCP config).

3. **Fixed personal-dev grant template** — Reusing `seed_personal_library_key.py`’s dual writer grants avoids Phase 3 entitlement UI/validation entirely while closing acceptance friction #1. Bundling friction #2/#3 as small, testable diffs in the same slice is pragmatic and evidence-backed from `v1-personal-developer-journey.md`.

---

## 5. Scope check — is the v1 slice appropriately minimal?

**Yes.** The v1 boundary is well drawn:

| In v1 (appropriate) | Correctly deferred |
|---------------------|-------------------|
| `ensure_personal_library` + lazy backfill | `ma3_create_key` / list / revoke MCP tools |
| `routes_keys.py` REST + SSR UI | Custom grants picker + entitlement checks |
| One additive column + four db helpers | Org member onboarding path |
| `max_keys_per_principal` env cap | Stripe / plan quotas (ADR-012) |
| confirmation default + `library_selection_reason` | `expires_at` UI, email verification, rate limits |
| agent-onboarding.md + deploy scripts bundle | Welcome redirect / first-run wizard |

**Module boundaries** align with `05-doc-code-mapping.md`: new `onboarding_service.py` + `routes_keys.py`, thin hooks in `routes_auth.py`, db helpers in `db.py`, friction fixes in existing write/MCP layers. No new tables, no entitlement service, no org service — consistent with “最小 diff”.

**Observatory / REST consistency** matches existing patterns:

- Session gate mirrors `routes_ui.py` (`resolve_session_user`, 401 JSON on `/api/*`, 302 on `/ui/*`).
- POST-not-DELETE for revoke matches feedback forms.
- 503 when Authing disabled is stricter than Observatory’s open read on LAN dev — **correct** for a key-issuance surface (§9 rightly rejects `ma3_ui_session` fallback).
- `main.py` router registration follows the same one-file-per-concern layout as `routes_auth`, `routes_ui`.

**Estimated diff size**: ~4 new/edited modules, one ALTER, one config field, policy/manifest bump — proportional to closing frictions #1–#3 and #5 without opening Phase 3/4 scope.

---

## Summary

| Item | Count |
|------|-------|
| Verdict | ACCEPT-WITH-NITS |
| Blocking issues | **2** |
| Non-blocking nits | 10 |

Safe to proceed to Phase O1 implementation after B1 and B2 are patched in the design doc.
