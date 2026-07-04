# v1 Acceptance — Self-Service Onboarding (design/13)

- **Tester**: fable (QA acceptance)
- **Date**: 2026-07-04 (03:39–03:50 UTC)
- **Target**: 192.168.31.202, ma3 `http://127.0.0.1:8000`, `skill_bundle_version 1.5.1`, Postgres, Authing enabled (`features: [... "dev_auth", "authing"]`)
- **Scope**: design/13 §14 criteria A1–A10, executed WITHOUT a brand-new Authing browser account. Browser signup steps were replaced by API-level simulation: `db.upsert_user_principal` + `onboarding_service.ensure_personal_library` + `create_personal_dev_key` executed in the server venv on 202 — the exact functions the Authing callback and `/ui/keys` endpoints call.
- **Deploy tree note**: the running deployment root is `/home/hct/ma3_v1/` (code at `/home/hct/ma3_v1/code/server/`), not `/home/hct/ma3/` as literally written in §14 A10.

## Verdict

**PASS-WITH-NITS.** Everything automatable passed exactly per spec: idempotent personal-library creation, key issuance with correct prefix/grants, MCP dual-library access, headless `ma3_report` defaulting (`confirmation=agent_judged`, `library_selection_reason=default_owned_personal_library`), explicit `lib_default` routing, quota enforcement at 10, owner-only revoke with immediate MCP 401/-32001, cross-principal isolation, seed script in the deploy tree, and self-service docs. The 11 shipped onboarding tests pass on 202. Residual: the literal browser Authing signup (A1) and the UI form flow (parts of A3) were not exercised in a real browser; two data-hygiene nits noted below.

## Test principals / artifacts created

| Artifact | Value | End state |
|---|---|---|
| Principal 1 | `user:accept-onboard-1783136399` | kept (12 api_keys rows, **0 active**) |
| Personal lib 1 | `lib_personal_226e1656f855` ("AcceptOnboard1783136399 的个人库", private, kind=personal) | kept |
| Main key | `key_13a556c894c1` (`ma3k_0ce8de6…`, label `acceptance-key`) | revoked (A7) |
| Principal 2 (isolation) | `user:accept-isolation-probe` / `lib_personal_8bd65771f4b5` / `key_fb3875f748d8` | key revoked |
| Probe records | `vk_14de67faf957` (personal lib, A5), `vk_1d105a1d4ae4` (`lib_default`, A6) — tagged `acceptance-probe` | left in DB as evidence |

## A1–A10 mapping

| # | Criterion | Result | Evidence |
|---|---|---|---|
| A1 | Browser `/ui/keys/` → Authing signup → callback; new `principals` row | **PARTIAL** | Automatable half verified: `GET /ui/keys/` (no session) → `302 /auth/login?next=/ui/keys/` (not 404); `GET /auth/login?next=/ui/keys/` → 302 to `https://ma3.authing.cn/oidc/auth?...redirect_uri=http://192.168.31.202:8000/auth/callback&state=...`; `GET /api/keys` (no session) → 401 JSON `{"detail":"authentication required"}`. Principal creation simulated with `db.upsert_user_principal(sso_user=..., display_name=...)` → `principals` row `(user:accept-onboard-1783136399, kind=user)` confirmed by psql. Actual Authing account creation + callback round-trip **not** run (needs a browser + fresh account). |
| A2 | Exactly 1 `kind=personal` library per owner; re-login doesn't duplicate | **PASS** (simulated) | `ensure_personal_library` called twice → same `lib_personal_226e1656f855` (`IDEMPOTENT_SAME_ID: True`); psql `count(*)=1` for `kind='personal' AND owner_principal_id='user:accept-onboard-1783136399'`. DB also enforces it structurally: unique partial index `idx_libraries_personal_owner ON libraries(owner_principal_id) WHERE kind='personal'`. Deterministic id matches design (`lib_personal_` + sha256 prefix). |
| A3 | Key create: `ma3k_` plaintext once; `api_keys` 1 row with `key_prefix`; 2 writer grants | **PASS** (service layer) / UI render PARTIAL | `create_personal_dev_key` returned `plaintext_key=ma3k_0ce8de6c115f4c205a4e19485fa08c22`, `key_prefix=ma3k_0ce8de6` (= plaintext[:12]). psql: `api_keys` 1 row (key_prefix populated, created_by=principal), `api_key_grants` exactly 2 rows: `lib_personal_226e1656f855/writer` + `lib_default/writer`. The one-time UI render ("refresh loses plaintext") not exercised in a browser; covered by shipped integration tests (see A-tests below). |
| A4 | `tools/list` OK; `ma3_whoami` dual libs | **PASS** | With the new key over `POST /mcp` (X-API-Key): `tools/list` returns 13 tools (and correctly **no** `ma3_create_key` — deferred to v1.1 per D2). `ma3_whoami`: `via=db_api_key`, `readable_library_ids` = `writable_library_ids` = `[lib_default, lib_personal_226e1656f855]`, `library_selection.default_write_behavior` present. `client_update_required=false` throughout. |
| A5 | Headless `ma3_report` (no `library_id`, no `confirmation`) | **PASS** | One-shot success: `vk_14de67faf957` persisted, `library_id=lib_personal_226e1656f855`, `confirmation="agent_judged"`, `library_selection_reason="default_owned_personal_library"`. Audit: `write_audit_log` row `wa_50b1ab569659` with correct principal_id, api_key_id=`key_13a556c894c1`, report_kind=new, confirmation=agent_judged. `records.created_by` correct. |
| A6 | `ma3_report` explicit `lib_default` | **PASS** | `vk_1d105a1d4ae4` persisted in `lib_default`, `library_selection_reason="explicit_library_id"`; audit row `wa_341fa36b38b7` attribution correct. |
| A7 | Revoke → MCP 401/-32001 | **PASS** | `db.revoke_api_key(key_13a556c894c1, principal_id=owner)` → True (second call → False, idempotent-safe). Immediate `ma3_whoami` with the revoked plaintext → JSON-RPC error `-32001 "Invalid credentials: the X-API-Key is unknown, revoked, or expired"`, `data.status_code=401`. Wrong-principal revoke of someone else's key → `False` (no effect; owner-only semantics confirmed). |
| A8 | Quota: 11th key rejected at limit 10 | **PASS** | `settings.max_keys_per_principal=10`. Filled from 1→10 active; 11th → `HTTPException 400 "active key limit reached; revoke an old key first"`. After revoking one filler, creation succeeds again. All fillers revoked afterwards. |
| A9 | Isolation: another account's key can't see the new personal lib | **PASS** | Second principal `user:accept-isolation-probe` + own key: `ma3_whoami` readable = `[lib_default, lib_personal_8bd65771f4b5]` only; `ma3_case cs_97fb2372199c` (principal 1's personal-lib case) → `-32601 case not found` (404, no existence leak); `ma3_context` search phrased to match the A5 probe returned the public A6 record (`vk_1d105a1d4ae4`, expected — it's in lib_default) but **not** the personal `vk_14de67faf957`. |
| A10 | Seed script in deploy tree | **PASS** | `ls /home/hct/ma3_v1/code/server/scripts/` → `seed_personal_library_key.py` (plus `e2e_authing_ui.py`, `migrate_legacy_pg.py`). Admin fallback available on the deployed host without a source checkout. |

**A-tests spot-check (task item 3)**: on 202, `pytest tests/unit/test_onboarding_service.py tests/integration/test_self_service_onboarding.py` → **11 passed** in 2.46s (covers the UI/session paths not automatable here: 302/401 without session, plaintext-once, list-without-plaintext, 503 when Authing unconfigured).

**Docs (§11.1)**: deployed `client/agent-onboarding.md` contains the self-service section — `/ui/keys/` referenced at L221/L228 and the "给用户的简短说明" at L260 ("在 `/ui/keys/` 自助创建 API key … 无需 clone 仓库").

## Friction closure vs v1-personal-developer-journey.md

| Friction | Status | Basis |
|---|---|---|
| #1 No self-service registration/key issuance (major) | **CLOSED** (modulo A1 browser residual) | `/ui/keys/` live (302→login, not 404); `/api/keys` REST live (401 without session); full issuance path produces a working dual-grant key with no admin involvement; onboarding doc rewritten to self-service. |
| #2 Confirmation stall on headless writes (major) | **CLOSED** | `ma3_report` with no `confirmation` (and no `report_kind` gymnastics) succeeded first try, defaulted to `agent_judged`, echoed in response and in `write_audit_log`. |
| #3 Silent library routing (minor) | **CLOSED** | `library_selection_reason` echoed on both writes: `default_owned_personal_library` / `explicit_library_id`, exactly per design §10.2 table. |
| #5 Deploy-tree script drift (minor) | **CLOSED** | `seed_personal_library_key.py` present in the deployed `code/server/scripts/`. |

## Nits / observations (non-blocking)

1. **A1 browser residual**: real Authing signup → callback → `ensure_personal_library` hook not exercised end-to-end. The callback hook code path is covered by integration test simulation and this run verified every function it calls, but a one-time manual browser pass (new Authing account) is still recommended to close A1 fully. The `/ui/observatory/` "API Keys" nav link (design §6.4) also couldn't be checked — observatory now 302s to login without a session.
2. **Orphan principal reference**: an unrelated actor created `user:accept-onboard-1783136524` at 03:42:05Z (key `key_600c1070a092` label `accept-live`, lib `lib_personal_d2510d1b9640`) during this run — it has an api_keys row and a personal library but **no `principals` row**, showing `create_personal_dev_key`/`ensure_personal_library` don't require (and no FK enforces) principal existence. Real UI/callback flows always create the principal first, so this is only reachable from script-level access, but a FK or an `ensure` inside the service would make it airtight. That key was not created by this test and was left untouched.
3. **Test-data residue**: probe records `vk_14de67faf957` (private) and `vk_1d105a1d4ae4` (in the public Community Library, tagged `acceptance-probe`) were left as evidence; the lib_default one can be deleted via `ma3_delete_record` if community-library hygiene matters.
4. **Doc path drift in §14 A10**: says `/home/hct/ma3/server/scripts/` but the deployment root on 202 is `/home/hct/ma3_v1/code/server/scripts/`. Worth fixing the design doc line.

## Operations log (condensed)

```text
curl 127.0.0.1:8000/healthz                                  → skill_bundle_version 1.5.1, features include authing
curl /ui/keys/ (no session)                                  → 302 /auth/login?next=/ui/keys/
curl /api/keys (no session)                                  → 401 {"detail":"authentication required"}
curl /auth/login?next=/ui/keys/                              → 302 https://ma3.authing.cn/oidc/auth?...
.venv python: upsert_user_principal + ensure_personal_library x2 + create_personal_dev_key
psql: libraries(1 row personal), principals(1), api_keys(1, key_prefix), api_key_grants(2 writer)
MCP tools/list → 13 tools (no ma3_create_key); ma3_whoami → dual libs, via=db_api_key
MCP ma3_report (implicit) → vk_14de67faf957 personal, agent_judged, default_owned_personal_library
MCP ma3_report (lib_default) → vk_1d105a1d4ae4, explicit_library_id
psql write_audit_log → 2 rows, correct principal/key/report_kind/confirmation
.venv python: quota fill 1→10, 11th → HTTPException 400; revoke → create OK again
2nd principal key: whoami own libs only; ma3_case cross → 404; ma3_context no personal leak
db.revoke_api_key(main) → True; MCP with revoked key → -32001 (401)
pytest onboarding unit+integration on 202 → 11 passed
ls ma3_v1/code/server/scripts/ → seed_personal_library_key.py present
grep ui/keys client/agent-onboarding.md → self-service section present
```
