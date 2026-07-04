# Review — 13-self-service-onboarding.md (sonnet-5)

> Reviewer: sonnet-5 (design reviewer)
> Scope: design/13 §1–§16 against ADR-011, design-08, design-10 (ADR-013), design-11 (ADR-014),
> acceptance/v1-personal-developer-journey.md, and the actual code in
> `code/server/app/{api,services,storage,core}` as of 2026-07-04.
> Method: every claim below was checked against the live source (line numbers cited), not just
> the design prose.

---

## 1. Verdict

**ACCEPT-WITH-NITS** — conditional on the 4 blocking issues below. The core idea (reuse
`ensure_library`/`insert_api_key`/`resolve_api_key`, personal-dev fixed grant template, no new
entitlement service) is sound and the v1/v1.1 cut is defensible. But one issue is a genuine
ADR conflict that needs an explicit decision (not a silent default), one is a **verified,
concrete test regression** the design doesn't acknowledge, and two are unaddressed edge cases
in exactly the categories (error handling, test coverage) the design otherwise handles well
elsewhere. None require a redesign; all four are fixable in the existing diff budget.

## 2. Blocking issues

### B1 — D3's auto-grant of `lib_default` writer contradicts ADR-011 Decision 2 / design-08 §5.1 without addressing the conflict

ADR-011 §1 decision 2 states explicitly:

> "公共 library（`lib_default`，`visibility=public`）**不自动**出现在 key 上；用户创建 key 时必须**显式勾选**该 library"

design-08 §5.1 repeats this. design-13's D3 (§3) makes the personal-dev key template grant
`lib_default` writer **unconditionally**, with **no checkbox and no UI acknowledgment** — the
only justification given is "与 `seed_personal_library_key.py` 默认行为完全一致." That parity
argument doesn't resolve the conflict: the seed script's default was accepted as an
**admin-mediated, one-off bootstrap shortcut** (case `cs_9f494e3df350` — admin runs it against
prod DB with informed deliberate intent). design-13 turns that shortcut into the **default,
zero-click outcome of anonymous self-service signup**, at unbounded scale — a materially
different risk profile from what ADR-011 decision 2 was written to prevent (surprise write
access to the public library without explicit consent).

**Fix** — pick one, explicitly, in the design (don't leave it implicit):
1. Add a single pre-checked checkbox on the create-key form ("Include Community Library
   (write access)") so the explicit-grant requirement is satisfied literally, with near-zero
   added friction (§4/§7 wireframe already has room for this next to "授权（固定）"); or
2. Add an explicit decision note superseding ADR-011 decision 2 for the personal-dev tier only,
   with sign-off, so future readers don't find an unexplained contradiction between two "true
   source" documents.

### B2 — §10.1's confirmation fix breaks an existing, intentionally-designed test and the design's own test plan doesn't mention it

`code/server/tests/integration/test_write_audit_and_delete.py` L109–126,
`test_explicit_new_requires_confirmation`, currently asserts that `report_kind: "new"` **without**
`confirmation` is rejected. This isn't incidental — the file's own module docstring (L13–20)
documents it as a deliberate, previously-reviewed choice:

> "When a caller DOES set `report_kind` to `supplement`/`new` it must also send a valid
> `confirmation` (**opting into the judgment tree**)."

design-13 §10.1 proposes deleting exactly this branch
(`write_audit_service.py` L47–48, confirmed current), collapsing to
`confirmation = payload.confirmation or "agent_judged"` **unconditionally**. That is very
likely the *right* product call given friction #2's evidence (a headless agent stalled for
122s because of this exact behavior) — but the design:

- never mentions this test or its documented rationale ("opting into the judgment tree"),
- doesn't list updating/removing `test_explicit_new_requires_confirmation` (or its docstring)
  in §13's test plan,
- claims Phase O3 acceptance is "全 suite 绿" (§12), which is **not achievable** as scoped
  without touching this test.

**Fix**: add "update/delete `test_explicit_new_requires_confirmation` and revise the
`test_write_audit_and_delete.py` module docstring's 'opting into the judgment tree' rationale"
as an explicit §13/§12 line item. Trivial to fix, but must be said, or Phase O3 CI fails on day
one.

### B3 — `POST /ui/keys/create`'s "no PRG" pattern can silently mint duplicate keys on refresh/back

D4 explicitly rejects POST-redirect-GET ("**不做** POST-redirect-GET") because a redirect-to-GET
would lose the one-time plaintext. But rendering the success page as a direct POST response
means a page refresh (or hitting back then forward) can **resubmit the form**, calling
`create_personal_dev_key` again — silently minting an extra key that eats into the 10-key quota
(§9's own budget) with no indication to the user why they suddenly have an unfamiliar key in
the list. This is exactly the "error handling edge case" category the design otherwise covers
carefully (§9's table has 7 rows) but misses here.

**Fix** — keep the one-time-reveal property without literal PRG: mint a short-lived,
single-read server-side token at creation time (`{token: plaintext}`, TTL ~5 min, deleted on
first read), redirect to `GET /ui/keys/created/{token}` which renders the plaintext once and
invalidates the token; a refresh of that GET after first read shows "already viewed, key is
`ma3k_a1b2c3…`" instead of creating anything new. Small diff, keeps §9's quota story intact.

### B4 — No test coverage for the owner-only invariant on the new REST endpoints

D5 and §6.3's `POST /api/keys/{key_id}/revoke` row both state "非本人/不存在 → 404" (no
existence-oracle leak) — good, and consistent with ADR-014/design-11 §5's existence-oracle rule.
But §13's integration test list (items 1–7) never exercises this with **two different
principals**: nothing asserts that principal B's `POST /api/keys/{A's key_id}/revoke` 404s, or
that principal B's `GET /api/keys` never contains any of A's `key_id`s. Given this is a new,
security-relevant surface (unlike `ma3_list_my_writes`, which is already scoped to
`auth.principal.principal_id` and tested), it needs its own explicit two-principal test, the
same pattern already used elsewhere in the codebase (`test_write_audit_and_delete.py`'s
`b_writes` cross-principal check, L385).

**Fix**: add to §13 integration test list: "two sessions (A, B) via `resolve_session_user`
monkeypatch; B revoking A's `key_id` → 404; B's `GET /api/keys` excludes A's keys."

## 3. Non-blocking nits

1. **`explicit_kind` becomes dead code.** After B2's fix, `write_audit_service.py`'s
   `explicit_kind = payload.report_kind is not None` (L29) has no remaining reader — remove it
   in the same diff to avoid a lint warning.
2. **Two different, same-named concepts called "key_prefix".** `McpAuthContext.key_prefix`
   (`core/security.py` L151/L215) is already a *live, per-request* value derived from the raw
   presented credential (`raw[:4]…`, 4 chars) for `ma3_list_my_writes` display. design-13's new
   `api_keys.key_prefix` **column** (12 chars, stored at creation) is a different mechanism for
   a different UI (`GET /api/keys` listing, where the plaintext isn't available live). They
   don't conflict, but the shared name will confuse the next reader — consider naming the new
   column something distinguishable in code comments (e.g. "display prefix" vs "request
   prefix") even if the wire field stays `key_prefix`.
3. **Revoke-of-already-revoked is conflated with not-found/not-yours.** `db.revoke_api_key`'s
   `UPDATE ... WHERE revoked_at IS NULL` returns `False` both when the key isn't the caller's
   *and* when it's the caller's own key that's already revoked. §6.3 maps both to 404, which is
   correct for the existence-oracle case but odd UX for "I own this key, I already revoked it
   yesterday, why is revoke 404ing." Consider: caller-owned + already-revoked → 200
   `{"revoked": true, "already_revoked": true}` (idempotent success), true not-found/not-yours
   → 404.
4. **Quota doesn't exclude expired keys.** `count_active_api_keys` filters only
   `revoked_at IS NULL`; an expired-but-not-revoked key (via `expires_at`, plumbed but unused in
   v1 per §15) would still count against the 10-key quota. Not reachable in v1 since nothing
   sets `expires_at` yet, but worth a one-line note so v1.1 doesn't reintroduce this silently.
5. **`_default_writable_library`'s legacy branch can pick a library that isn't `lib_default`**
   (`sorted(writable)[0]` fallback when `lib_default` isn't in the legacy key's writable set),
   yet §10.2's table labels that whole branch `legacy_default_library`. Harmless (pre-existing
   behavior, not something design-13 introduces), but the reason string is slightly misleading
   for that fallback sub-case; a one-clause caveat in §10.2 would save future confusion.
6. **CSRF on the new POST forms.** `/api/keys`, `/ui/keys/create`, `/ui/keys/{id}/revoke` follow
   the existing cookie-session form pattern from `/ui/observatory` (no CSRF token,
   `SameSite=Lax` cookies only). `SameSite=Lax` already blocks cross-site POST cookie
   inclusion in modern browsers, so this is low risk and consistent with existing precedent —
   but key creation/revocation is higher-value than a feedback vote, so a one-line acknowledgment
   ("relies on SameSite=Lax, same as existing Observatory forms; no new CSRF token added") would
   preempt a future security-review nit.
7. **`display_name` fallback chain isn't mentioned but exists and is fine.**
   `_display_name_from_claims` (authing_client.py L118) already falls back through
   nickname→name→username→phone→email→sub, so "张三 的个人库" never degrades to "None 的个人库."
   Worth a one-line note in §6.1 so a future reader doesn't have to go check.
8. **`main.py` router registration isn't spelled out as a diff line**, only implied by "`main.py`
   注册 router" in §6.3's header. Trivial, but every other file in §12's phase breakdown gets an
   explicit bullet; `main.py`'s one-line `app.include_router(keys_router)` should too for
   diff-review completeness.

## 4. What I agree with (top 3 strengths)

1. **The idempotent-library-key design (D1) is verified correct against the actual concurrency
   semantics**, not just asserted. `ensure_library`'s bare INSERT will raise a PK-violation only
   after a concurrent committer has already landed the row (Postgres blocks the second inserter
   until the first's transaction resolves; SQLite serializes writers), so the
   `except Exception → re-find` fallback in `ensure_personal_library` is guaranteed to find a
   row on retry. Reusing `(kind='personal', owner_principal_id)` rather than the deterministic
   `library_id` as the idempotency key is exactly right — it's independently confirmed against
   live data (`lib_personal_nova`, `lib_personal_eval_admin`, both non-canonical seed-era ids)
   that this correctly backfills pre-existing personal libraries without any migration script.
2. **The design was checked against real line numbers, not just the prose in design-08.** The
   three `ma3_report` response-branch edits (§10.2) land at L447/~494/L536 in
   `mcp_tool_service.py` exactly as cited, and the `write_audit_service.py` L47–48 citation for
   the confirmation 400 is exact. The `library_selection_reason` → code-branch mapping
   (verify/refute, explicit `library_id`, single-personal-default, legacy/dev-bypass) maps
   1:1 onto `resolve_report_write_plan`'s actual four branches. This is the kind of grounding
   that makes a design trustworthy to implement from directly, and it's rare enough to call out
   as a strength.
3. **D2's refusal to ship `ma3_create_key` in v1 is the correct risk call, and the reasoning is
   the strongest part of the doc.** Deferring "new key grants ⊆ caller's entitlement" until
   Phase 3's entitlement service exists — rather than hand-rolling a weaker "⊆ caller's current
   key grants" check that would need to be re-verified later — avoids building a second,
   throwaway authorization model. Framing the human-in-the-loop UI step as *itself* the
   bootstrap solution (an agent starting from zero has no key to call `ma3_create_key` with
   anyway) is a good insight that a purely code-first design would likely have missed.

## 5. Scope check — is the v1 slice appropriately minimal?

**Yes, with the one caveat in B1.** The v1/v1.1 split (§1, §8, §12's "v1.1（缓期）" list) draws
the line in a defensible place:

- Deferring `ma3_create_key`/`ma3_list_keys`/`ma3_revoke_key` MCP tools to v1.1 is justified by
  B2's entitlement-subset dependency (D2) — genuinely blocked on Phase 3, not just deferred for
  convenience.
- Deferring custom-grants UI (checkbox picker, reader role) to v1.1 is reasonable *given* B1 is
  resolved — a fixed template is a legitimate v1 simplification as long as the one library it
  auto-grants without asking is explicitly sanctioned.
- Deferring org member paths (Phase 4) and Stripe (ADR-012) is clearly out of this slice's
  blast radius; no scope creep there.
- The single additive column (`api_keys.key_prefix`) plus 4 new db.py helpers plus one new
  service file plus one new routes file is a genuinely small, reviewable diff for what it
  delivers (closes friction #1 major + #2 major + #3 minor + #5 minor from the acceptance doc).
- One thing *arguably* missing from "minimal but complete": §15's open-questions table defers
  rate-limiting/anti-abuse on key creation entirely to v1.1, which is fine for the current LAN
  deployment (`192.168.31.202`) but should be called out as a **hard precondition for any wider
  deployment** rather than a generic "open question," since self-service + zero email
  verification + 10-key-per-principal quota is a fairly permissive default for anything
  internet-facing.

## Appendix — verification trail

- ADR-011, design-08, design-10 (ADR-013), design-11 (ADR-014), and
  acceptance/v1-personal-developer-journey.md read in full.
- Code read: `routes_auth.py`, `write_audit_service.py`, `mcp_payloads.py`,
  `principal_service.py`, `api_key_service.py`, `security.py`, `config.py`, `main.py`,
  `mcp_tool_service.py` (L430–560), `db.py` (helpers around L1290–1770), `session.py`,
  `authing_client.py`, `client/agent-onboarding.md` (L200–224),
  `client/templates/ma3-agent-policy.mdc` (§3), `tests/integration/test_write_audit_and_delete.py`.
- Prior ma3 knowledge consulted via `ma3_context` (cases `cs_9f494e3df350` — multi-library
  write-targeting slice already shipped/accepted; `cs_5b406cd402f3` — original design-08/ADR-011
  design record) confirmed the current `role`-based `api_key_grants` schema (not design-08's
  original `can_write`/`can_maintain` shape) is what's actually live, and design-13 correctly
  targets the live schema rather than the superseded one.
