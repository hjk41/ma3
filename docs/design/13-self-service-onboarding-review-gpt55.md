# Review: 13 — Self-Service Onboarding

## 1. Verdict

**ACCEPT-WITH-NITS**

The design is directionally right and implements the smallest useful v1 slice: Authing-backed human session creates a DB API key, the agent data path continues to require `X-API-Key`, and MCP key creation is intentionally deferred. I would not reject the design, but two details should be fixed before implementation because they affect security and the core "exactly one personal library" invariant.

## 2. Blocking Issues

1. **Session-backed key creation/revocation needs explicit CSRF or Origin protection.**

   The design correctly says `/api/keys` and `/ui/keys/` must use the Authing browser session and must not accept `X-API-Key`. However, these are high-impact cookie-authenticated POSTs that mint or revoke API credentials. Current session cookies are `HttpOnly` and `SameSite=Lax`, and existing Observatory form POSTs are low-risk feedback actions with no CSRF token pattern. That is not enough to leave implicit for key issuance.

   **Concrete fix:** specify one mandatory defense in `routes_keys.py`: either per-session CSRF tokens embedded in the server-rendered key forms and required on JSON/form POSTs, or strict `Origin`/`Referer` validation against `public_base_url` / request base URL for all state-changing key routes. Add integration tests for cross-origin or missing-token `POST /api/keys`, `POST /ui/keys/create`, and revoke. Keep the current rule that no anonymous `ma3_ui_session` fallback can create keys.

2. **Personal-library idempotency should be enforced by the database, not only by `find_personal_library()`.**

   The design relies on "find by `(kind='personal', owner_principal_id)` first, then create deterministic id, catch PK conflict and re-find." That handles two new concurrent first logins for the same principal, but the current `libraries` table has only `id` as a primary key and no uniqueness on personal ownership. Existing or future seed/admin paths can still create multiple personal libraries with different ids for the same owner, and `ORDER BY id LIMIT 1` would silently pick one. That conflicts with the acceptance check requiring exactly one `kind=personal, owner_principal_id=user:<sub>` row.

   **Concrete fix:** add an idempotency invariant to the design and migration: a unique index/constraint for personal libraries by owner, for example a partial unique index on `(owner_principal_id)` where `kind='personal' AND owner_principal_id IS NOT NULL` on Postgres, with the SQLite equivalent used in tests. Before creating the index, detect duplicate existing personal libraries and fail migration with a clear operator message or document a deterministic cleanup/backfill step. Then make `find_personal_library()` treat duplicate rows as an invariant violation rather than silently choosing one.

## 3. Non-Blocking Nits

1. **Make the deploy-bundle requirement executable.** The design says the 202 deploy bundle must include `server/scripts/seed_personal_library_key.py`, but it does not name the packaging/deploy file that must change. Add the exact deploy profile or bundle manifest path and a test/check command so this does not get lost as a documentation-only requirement.

2. **Clarify the `confirmation` behavior change in tests and compatibility notes.** The current implementation intentionally 400s when callers explicitly set `report_kind=new|supplement` without `confirmation`; the design changes that to default `agent_judged`. I agree with the change, but it should update the integration test comments and add a regression case for explicit `report_kind=new` with omitted `confirmation`, plus a case proving invalid explicit confirmations still fail.

3. **Specify label validation for created keys.** `POST /api/keys` only accepts `label`, but the design should bound and normalize it: trim whitespace, default empty to `agent-key`, cap length, and reject/control-strip newlines. The UI should continue to HTML-escape labels.

4. **Be precise about `key_prefix`.** "明文前 12 字符" is usable for display, but it reveals only about seven hex characters after `ma3k_`. That is probably fine as a non-secret identifier, but the design should state it is not used for authentication, may collide, and UI/API must not rely on it as a key id.

5. **Audit key-management events consistently.** The design mentions application logs for create/revoke. It should specify the exact fields to log and forbid plaintext/hash logging: `principal_id`, `key_id`, `key_prefix`, grants, action, result, and timestamp are enough.

6. **Authing-disabled behavior should be covered for both REST and UI.** The design states 503 for `/ui/keys/` and `/api/keys`; add tests for `GET /api/keys`, `POST /api/keys`, and all UI entry points, not just one route.

## 4. What I Agree With

1. **Deferring MCP key creation in v1 is the right security boundary.** A leaked agent key should not be able to mint more keys, and the entitlement/subset rules needed for safe MCP key issuance are outside this v1 slice. Human session-only issuance is a good conservative choice.

2. **The personal-dev grant template is appropriately small.** Fixed writer grants on the owned personal library plus `lib_default` match the seed script and the acceptance persona. Avoiding custom grant UI keeps v1 away from entitlement and org complexity.

3. **The quick fixes address the observed journey failures directly.** Defaulting omitted `confirmation` to `agent_judged` and returning `library_selection_reason` target the two agent-facing stalls from the acceptance run without changing the main write-routing model.

## 5. Scope Check

Yes, the v1 slice is appropriately minimal. It closes the major "new developer cannot get a key" gap with Authing login, automatic personal library provisioning, a simple key UI, and documentation/deploy updates. It deliberately avoids org membership, custom grants, billing, entitlement services, and MCP key-management tools.

The only scope pressure I would accept before implementation is the two blockers above: CSRF/origin protection is part of making session-only key creation safe, and a uniqueness invariant is part of making "first login creates exactly one personal library" true. Everything else can stay in v1.1 or later.
