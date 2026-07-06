# ma3 v1 Acceptance Test — Personal Developer Journey

- **Date**: 2026-07-04
- **Tester**: fable (QA/acceptance)
- **ma3 version**: service 1.0.0, **skill_bundle_version 1.5.0**, tool_schema `ma3.mcp.v1`, instance `ma3-v1-202` (deployed 2026-07-03T11:50:42Z)
- **Environment**: ma3 server at `http://127.0.0.1:8000` on host 192.168.31.202 (Ubuntu, Postgres backend, pgvector hybrid search). Driver: **Claude Code CLI** (DeepSeek `deepseek-v4-pro[1m]` BYOK) run as `claude -p` fresh sessions with `HOME=/home/hct/ma3-eval/profiles/nova`, ma3 MCP pre-configured, policy v1.5.0 in `CLAUDE.md`, `timeout 300` on every call.
- **Persona**: `user:nova-dev`, a personal developer holding one API key ("Nova's key", plaintext withheld) with **writer grants on both** `lib_default` (Community Library, kind=community, public) and `lib_personal_nova` ("Nova Dev personal library", kind=personal, private, owner `user:nova-dev`).
- **Method**: every claim by claude was independently verified via direct MCP `tools/call` probes (curl with Nova's key) and read-only psql queries against the live DB. Baseline captured before the run.

## Baseline vs final DB state

| Metric | Before | After | Delta |
|---|---|---|---|
| records total | 87 | 89 | +2 |
| records in `lib_default` | 47 | 48 | +1 (`vk_220642c8a535`) |
| records in `lib_personal_nova` | 0 | 1 | +1 (`vk_de9bd46c44c0`) |
| cases total | 72 | 74 | +2 (`cs_6672c9581007`, `cs_a10abc2b375c`) |
| write_audit_log rows | 27 | 29 | +2 (both `principal_id=user:nova-dev`) |
| audit rows for `user:nova-dev` | 0 | 2 | +2 |
| records `created_by=user:nova-dev` | 0 | 2 | +2 |
| record_feedback by `user:nova-dev` | 0 | 1 | +1 (upvote on `vk_6fd3e8a62163`) |

No unexpected writes; all deltas are attributable to the scripted journey.

---

## Operations performed

### 1. Onboarding / first-run reality check (no claude)

**What was checked**

- `GET /healthz` → 200, advertises `skill_bundle_version: 1.5.0`, `client_manifest_url: /client/manifest.json`.
- `GET /client/agent-onboarding.md` → 200. The doc is complete for the *"I already have a key"* case: one-shot bootstrap (`~/.ma3` sync tooling via curl), per-runtime MCP config, policy install, upgrade-flag behavior, verification checklist. Quality is good.
- MCP `tools/list` → 13 tools: `ma3_context, ma3_case, ma3_locate_by_id, ma3_report, ma3_list_my_writes, ma3_delete_record, ma3_restore_record, ma3_validate, ma3_doctor, ma3_whoami, ma3_feedback, ma3_list_drafts, ma3_review_record`. **No `ma3_create_key`.**
- `GET /ui/keys` → **404** (and `/ui/` → 404): no Observatory key-management UI.
- Onboarding doc explicitly says keys are "生产由管理员发放" (production keys issued by an admin); the only concrete acquisition path is `code/server/scripts/seed_personal_library_key.py` run by an admin with DB access. On host 202 that script exists only in the **source checkout** (`/home/hct/ma3_deploy/code/server/scripts/`), *not* in the deployed service tree (`/home/hct/ma3/server/scripts/`).

**Finding**: registration/key issuance is **admin-mediated only**, matching the stated design gap (design/08 Phase 5 not implemented). For a brand-new personal developer the required steps are: (1) find an admin, (2) admin runs the seed script from a source checkout against the production DB, (3) admin hands over the plaintext key out-of-band, (4) developer follows onboarding bootstrap. Steps 1–3 are outside the product. Friction rated **major** (see Friction #1). Once a key exists, onboarding itself is smooth — the Nova profile's pre-provisioned MCP + policy connected first try ("ma3 ✔ Connected").

### 2. Consult community knowledge + apply (claude, fresh session)

**Prompt** (verbatim, via `claude -p`, timeout 300):

> I am deploying ma3 on a fresh Postgres and initialize_database logs OK but ma3_context 500s with the error: relation record_relations does not exist. Use the ma3_context MCP tool (client_version 1.5.0) to find prior knowledge, tell me the root cause and the fix, and cite the record id(s) you used.

**Pre-probe (tester)**: a direct `ma3_context` call with the same problem returned, in order, `vk_6fd3e8a62163` (lib_default), `vk_8fb3cc761933` (lib_default), `vk_e0f6c424e6e8` — the first two are exactly the seeded records for this bug. GTN ranking surfaced the right knowledge at rank 1. `structuredContent.server` reported `client_update_required=false`, `client_update_recommended=false` with `client_version: 1.5.0`.

**What claude did** (completed in ~34 s): called `ma3_context`, correctly explained the root cause (pgvector `CREATE EXTENSION` failing inside the same psycopg3 transaction as the schema DDL, aborting it so `conn.commit()` rolls back all tables while the log still says OK) and the fix (run pgvector setup in its own connection after the schema commit). Cited `vk_6fd3e8a62163` (primary), `vk_8fb3cc761933` (confirming), `vk_6a00b249fd34` (parent case) — all three verified to exist in `lib_default`. Claude also **upvoted** the primary record unprompted.

**Verification**: `record_feedback` gained a row `(vk_6fd3e8a62163, user:nova-dev, vote=1, 2026-07-04T02:04:11Z)`. Answer content matches the record's stored root cause/fix. Citation accuracy: 3/3 real record ids. Quality judged **excellent** — this is the retrieval half of the loop working as designed.

*Nit*: claude rendered the record id as a link to a fabricated URL (`https://ma3.example.com/records/...`) — cosmetic hallucination, ids themselves correct.

### 3. Contribute to the COMMUNITY library with reuse citation (claude, fresh session)

**Prompt** (abridged): told claude the fix from `vk_6fd3e8a62163` was applied and verified, plus one new detail (Ubuntu 24.04 + PG16 needs `apt install postgresql-16-pgvector` first); asked it to `ma3_validate` then `ma3_report` with `client_version 1.5.0`, `library_id: "lib_default"`, `based_on_record_ids: ["vk_6fd3e8a62163"]`, outcome resolved.

**What claude did** (~55 s): validated then reported; announced new record **`vk_220642c8a535`** in `lib_default`, `report_kind=verify` targeting `vk_6fd3e8a62163`, case `cs_6672c9581007`.

**DB verification** (all confirmed):

- `records`: `vk_220642c8a535 | lib_default | created_by=user:nova-dev | active | cs_6672c9581007 | 2026-07-04T02:05:46Z`.
- `write_audit_log`: `vk_220642c8a535 | user:nova-dev | lib_default | report_kind=verify | confirmation=verify_direct`.
- `record_relations`: `vk_220642c8a535 --derived_from--> vk_6fd3e8a62163`.
- `payload_json`: `based_on_record_ids=["vk_6fd3e8a62163"]`, `report_kind="verify"`, `target_record_id="vk_6fd3e8a62163"`; structured actions/evidence captured the apt-package detail; no secrets present.

Claude went beyond the ask and classified the write as `verify` of the source record instead of a plain `new` — arguably the *better* ADR-013 behavior. It also claimed to upvote `vk_6fd3e8a62163` again; the DB shows only the single stage-2 feedback row (idempotent/deduped — claude's claim was harmlessly imprecise).

### 4. Store PROPRIETARY knowledge — implicit personal-library routing (claude)

**Attempt 1** (~122 s, **failed to write**): prompt asked claude to save an internal nova-billing-api runbook (pool-size fix) with *no* `library_id`. Claude stalled and returned: *"The server requires explicit user confirmation for new reports … Could you type a short confirmation word/phrase…"* — and wrote nothing (DB confirmed: no new record). This is a **misreading**: the server does *not* require user-typed confirmation. Tester verification: a direct dry-run `ma3_report` with no `confirmation` and no `library_id` succeeded with `confirmation: "agent_judged"`, `library_id: "lib_personal_nova"`. The optional `confirmation` field plus policy wording apparently pushed the model into interactive-confirmation behavior, which is a dead end in a non-interactive `-p` session.

**Attempt 2** (retry per test rules, ~21 s, succeeded): same content with an explicit "CONFIRMED — save it … confirmation user_confirmed … do NOT pass library_id" preamble. Claude reported record **`vk_de9bd46c44c0`**, library **`lib_personal_nova`**, case `cs_a10abc2b375c`.

**DB verification**: `records` row `vk_de9bd46c44c0 | lib_personal_nova | created_by=user:nova-dev | active`; `write_audit_log` row `vk_de9bd46c44c0 | user:nova-dev | lib_personal_nova | report_kind=new | confirmation=user_confirmed`. **ADR-011 default-to-personal auto-selection worked**: with `library_id` omitted, the DB key holding exactly one owned personal library routed the write to `lib_personal_nova`, not community. `ma3_whoami` also advertises this behavior in `library_selection.default_write_behavior`.

### 5. Privacy / isolation check (direct probes + DB)

- `records` table: the proprietary record exists **only** in `lib_personal_nova` (`lib_default` count for it: 0).
- `ma3_context` with Nova's key for "nova-billing-api slow billing worker NOVA_DB_POOL_SIZE" → returns `vk_de9bd46c44c0` (rank 1) alongside community records; Nova's `readable_library_ids = [lib_default, lib_personal_nova]`. Personal knowledge is retrievable by its owner in the same query stream as community knowledge.
- Isolation by grants: `api_key_grants` shows access is grant-scoped per key. Nova's key holds grants only on its two libraries and correspondingly sees only those in `ma3_whoami` (the dev admin key, by contrast, sees all 5 libraries). The other personal key on the system (`key_eval_dual_live2`: `lib_personal_eval_admin` + `lib_default`) has **no grant on `lib_personal_nova`**, so a community-level peer cannot read Nova's record; `lib_personal_nova` is `visibility=private`, `owner=user:nova-dev`. Confirmed structurally (grants + whoami behavior); no plaintext third-party key was available for a live negative probe, noted as a residual gap in test coverage, not in the product.

### 6. Reuse / repeat consult — loop closure (claude, fresh session)

**Prompt**: "on Ubuntu 24.04 with Postgres 16, CREATE EXTENSION vector fails for my ma3 deployment even when run in its own connection. Check ma3 prior knowledge (ma3_context, client_version 1.5.0) … citing record ids."

**Result** (~27 s): claude retrieved and cited **`vk_220642c8a535`** — the record Nova wrote 20 minutes earlier in stage 3 — together with `vk_199ffe02bd04` (superuser requirement) and `vk_6fd3e8a62163`, and synthesized a correct two-step fix (`apt install postgresql-16-pgvector`, then `CREATE EXTENSION` as postgres superuser). The freshly contributed community knowledge was immediately discoverable and correctly ranked for a related-but-different query. **Loop closed.**

---

## Designs verified

| Design | Verdict | Evidence (one line) |
|---|---|---|
| ADR-011 / design-08 — single key, multi-library, personal-default write routing, isolation | **PASS** | One key: whoami shows dual read/write grants; omitted `library_id` routed `vk_de9bd46c44c0` to `lib_personal_nova`; explicit `lib_default` write landed in community; grants-scoped visibility confirmed. |
| ADR-013 / design-10 — write audit attribution + reuse lineage | **PASS** | Both writes have `write_audit_log` rows with `principal_id=user:nova-dev` and correct `report_kind`/`confirmation`; `based_on_record_ids` persisted and materialized as `derived_from` relation `vk_220642c8a535 → vk_6fd3e8a62163`. |
| GTN search ranking (design-12) | **PASS** | The seeded fix record ranked #1 for the stage-2 problem in a direct probe; the day-old contribution `vk_220642c8a535` surfaced top-2 for a related stage-6 query. |
| Client-sync / auto-upgrade (ADR-009) | **PASS** | Every `structuredContent.server` block with `client_version: 1.5.0` returned `client_update_required=false` and `client_update_recommended=false`; sync tooling URLs advertised. |
| Onboarding UX + registration | **PARTIAL** | Onboarding doc + policy are complete *given a key*, and MCP connected first try; but there is no self-service signup/key issuance (no `ma3_create_key` in tools/list, `/ui/keys` 404) — admin must run `seed_personal_library_key.py` from a source checkout. |

## Friction / rough edges (personal developer's POV, ordered)

1. **No self-service registration or key issuance** — severity: **major** (blocker for organic adoption, not for this eval since design/08 Phase 5 is explicitly deferred). A new developer cannot get from "found ma3" to "have a key" without an admin running `seed_personal_library_key.py` against the DB and delivering the plaintext key out-of-band; the seed script is not even in the deployed tree on 202 (only in the source checkout), and the onboarding doc's key step is one line ("issued by admin") with no request procedure. *Suggestion*: ship design/08 Phase 5 (`ma3_create_key` + `/ui/keys`); until then, add an explicit "how to request a key" section (admin contact, exact seed command, expected grants) to agent-onboarding.md and include the seed script in deploy artifacts.
2. **Claude invented a "server requires user confirmation" blocker on its first personal-library write** — severity: **major** (first attempt silently produced no write; in headless/CI use the loop dies). The optional `confirmation` field + policy wording led the model to demand a user-typed confirmation the server never requires (dry-run probe: report with no confirmation succeeds as `agent_judged`). *Suggestion*: clarify in the tool description and policy that `confirmation` is optional metadata (`agent_judged` default is acceptable) and never a gate; consider a schema description like "do not ask the user for this".
3. **Implicit vs explicit library choice relies entirely on prompt discipline** — severity: **minor** (worked correctly in this run, both directions). The auto-default writes proprietary content to the personal library, but nothing warns an agent that *forgot* `library_id:"lib_default"` that its intended community contribution went private, or vice versa. The routing hint exists only in `ma3_whoami` output and the field description. *Suggestion*: echo a prominent `library_selection_reason` in every `ma3_report` response, and have policy require the agent to state the target library before writing.
4. **Cosmetic answer-level hallucinations** — severity: **minor**. Claude fabricated a record URL (`ma3.example.com/records/...`) and claimed a second upvote that the DB deduped. Record ids and substance were accurate throughout. *Suggestion*: none for the server; a policy note "cite record ids as plain text, do not invent URLs" would tidy it up.
5. **Deployed-tree/script drift** — severity: **minor**. The deployed `server/scripts/` on 202 lacks the admin registration script, so registration must be performed from a separate checkout; risk of version skew between the running server and the seeding code. *Suggestion*: include admin scripts in the deploy bundle.
6. **Latency** — severity: **minor/none**. Direct MCP calls: 1–4 s. Claude end-to-end: 21–55 s per successful task (fine); the one pathological run was 122 s and that was the confirmation stall (finding #2), not server latency.

## Verdict

**PASS-WITH-NITS.** The core personal-developer loop — consult prior community knowledge, get a correctly-ranked, correctly-cited answer, apply it, verify it, contribute the verified outcome back with lineage, keep proprietary knowledge private by default under the same key, and immediately re-discover the new contribution — worked end-to-end with full DB-level attribution and zero incorrect library placements. ADR-011, ADR-013, GTN ranking, and client-sync all verified PASS with concrete evidence. The two majors are (a) the known, explicitly-deferred registration gap, which today makes the very first step of the journey impossible without an admin, and (b) an agent-side confirmation stall that cost one write attempt and would break unattended agents — both fixable without architectural change. Neither undermines the implemented v1 scope, so the journey is v1-acceptable.

## Appendix: artifacts created by this test

| Record | Library | Case | report_kind / confirmation | Note |
|---|---|---|---|---|
| `vk_220642c8a535` | `lib_default` | `cs_6672c9581007` | verify / verify_direct | Community contribution, `derived_from vk_6fd3e8a62163` |
| `vk_de9bd46c44c0` | `lib_personal_nova` | `cs_a10abc2b375c` | new / user_confirmed | Proprietary runbook, auto-routed |

Plus one `record_feedback` upvote (`user:nova-dev` → `vk_6fd3e8a62163`). All writes are additive; no server code, config, or existing data was modified.
