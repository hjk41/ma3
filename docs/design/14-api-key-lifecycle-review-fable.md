# Review: 14 — API Key Lifecycle Management

> **Reviewer**: fable
> **Date**: 2026-07-04
> **Doc reviewed**: `docs/design/14-api-key-lifecycle.md`
> **Code reviewed**: `code/server/app/api/routes_keys.py`, `code/server/app/storage/db.py`,
> `code/server/app/services/onboarding_service.py`, `code/server/app/services/api_key_service.py`,
> `code/server/tests/integration/test_self_service_onboarding.py`, `code/server/scripts/e2e_authing_ui.py`

## Verdict: PASS-WITH-NITS

The core decision (hard delete for v1, no audit cascade, keep `revoked_at` column for legacy
rows) is correct and verified against the code:

- `write_audit_log` has **no foreign key** to `api_keys` (`db.py` schema, ~line 292), so hard
  delete cannot break audit rows. The design's claim holds.
- `resolve_api_key` looks up by hash; a deleted row returns `None` and MCP auth fails with the
  existing `-32001`. No auth-path change needed.
- `count_active_api_keys` already uses `revoked_at IS NULL`, so hard-deleted rows free quota
  with zero changes. The quota SQL in §6 matches the existing function exactly.
- The delete-then-recreate story for grants/rotation keeps v1 small. Good call deferring
  grant edit and rotate.

No blocking issues. The nits below are contract discrepancies between the doc and the current
code that will bite the implementer mid-session if not resolved first. Each has a recommended
resolution so the implementer does not need to come back to product.

---

## Blocking Issues

None.

---

## Nits (resolve before/while implementing)

### N1. Overlong-label behavior is mis-stated for the JSON API

§5 validation table says label over 120 chars → `200`, truncate, "matching current behavior".
That is only true for the HTML form path (`normalize_key_label` truncates). The JSON path uses
`CreateKeyBody.label: Field(max_length=120)`, so FastAPI returns **`422`**, not a truncated
`200`.

**Resolution**: keep the Pydantic constraint. Document `POST /api/keys` and
`PATCH /api/keys/{key_id}` as returning `422` for labels over 120 chars; truncation applies to
the SSR form path only. Do not add truncation logic to the JSON routes.

### N2. Legacy soft-revoked rows: the filter location is unspecified

§8 says legacy revoked keys should "not show in `/ui/keys/` by default", and §5 says the list
response excludes deleted keys — but `db.list_api_keys_for_principal` currently returns **all**
rows including `revoked_at IS NOT NULL`. The doc's §6 "New DB Helpers" table lists only
`delete_api_key` and `update_api_key_label`, so an implementer following §6 literally would
ship a list that shows legacy revoked keys with no status badge and no delete button —
they would look active.

**Resolution**: add `AND revoked_at IS NULL` to `list_api_keys_for_principal` (one line;
the function is only called from the keys routes). Then drop `revoked_at` from
`_public_key_payload` and add `expires_at`, matching the §5 response shape. Also delete the
now-dead revoked-badge branch in `_render_keys_page` and `_render_key_value_cell`.

### N3. Stray 撤销 copy outside the routes being replaced

Acceptance criterion A2 says no `撤销`/`已撤销` remains, but two spots are outside the
revoke routes and easy to miss:

- `_render_key_value_cell` legacy hint: "旧 key 无存储副本，请**撤销**后重建…" → replace with
  the §7 copy ("…请创建新 key 后删除旧 key").
- `create_personal_dev_key` quota error: "active key limit reached; **revoke** an old key
  first" → "…delete an old key first" (§5 already specifies this string; the doc just doesn't
  say where it lives — it is in `onboarding_service.py`, not the routes file).

**Resolution**: `grep -rn '撤销\|revoke' code/server/app` as the last implementation step.

### N4. Delete helper sketch: simplify

The §6 sketch does SELECT → DELETE grants → DELETE key. The SELECT is redundant; delete the
key row first (with `principal_id` in the WHERE), check rowcount, and only then delete grants:

```python
def delete_api_key(key_id: str, *, principal_id: str) -> bool:
    with connect() as conn:
        cur = _execute(
            conn,
            "DELETE FROM api_keys WHERE key_id = ? AND principal_id = ?",
            (key_id, principal_id),
        )
        if not getattr(cur, "rowcount", 0):
            return False
        _execute(conn, "DELETE FROM api_key_grants WHERE key_id = ?", (key_id,))
    return True
```

Same transaction, one fewer round trip, no ownership-check/delete race.

### N5. UI delete of a missing key: pick one behavior

§8 says "Redirect back with no visible difference **or** show not found". Ambiguity makes the
test assertion arbitrary. **Resolution**: always `303` back to `/ui/keys/` regardless of
delete result (matches current `ui_keys_revoke`, which ignores the return value). The JSON
route is where `404` matters.

### N6. Drop the 410 bridge entirely

§5 offers an optional `410 Gone` bridge for the revoke routes. ma3 has not launched publicly
and the only consumers are this repo's own UI, tests, and E2E script — all updated in the same
change. **Resolution**: delete `POST /api/keys/{key_id}/revoke`, `POST /ui/keys/{key_id}/revoke`,
and `db.revoke_api_key` (after confirming no admin/seed script calls it). No bridge.

### N7. Audit "Deleted key" rendering is a no-op for v1 — say so

§3's audit display table implies UI work, but no current view joins `write_audit_log` to
`api_keys` (`list_my_writes` joins libraries only and returns `api_key_id` as a raw string).
**Resolution**: mark the display table as guidance for a future audit view; v1 requires no
code change here. Keeps A6 testable as a pure DB assertion.

### N8. Rename is severable — treat it as commit 2

PATCH route + `/ui/keys/{key_id}/label` form + `update_api_key_label` helper + 3 tests + an
E2E step is roughly a third of the total work and is fully independent of delete. If the
session runs long, ship delete first; rename does not gate any acceptance criterion except
A11/A2-rename and can land separately.

---

## Test Gaps

The §9 matrix is good and mostly maps onto existing tests (the `authing_client` fixture and
`_ORIGIN` header pattern in `test_self_service_onboarding.py` cover the setup column). Gaps:

1. **No 422-label test.** Per N1, add `test_create_key_label_too_long_422` (JSON API,
   121-char label → `422`). The matrix currently implies truncation, which would fail.
2. **No legacy-revoked-row filtering test.** Per N2, add
   `test_legacy_revoked_key_hidden_from_list`: insert a key, call `db.revoke_api_key` (or set
   `revoked_at` directly if the function is removed), assert `GET /api/keys` and `/ui/keys/`
   omit it and quota does not count it.
3. **`test_delete_key_owner_only` needs a second session user.** The current fixture pins one
   `SessionUser`. Either parametrize the fixture or create the victim key via
   `db.insert_api_key` under a different `principal_id` — the latter is less churn.
4. **Existing tests to update, not just add**: `test_revoke_key_blocks_mcp` becomes
   `test_delete_key_blocks_mcp` (change the route call; assertions are otherwise identical);
   `test_create_key_with_custom_grants` already covers the matrix's
   `test_free_user_cannot_drop_community_writer` — rename or leave as is, don't duplicate.
5. **E2E**: the §9 Playwright extension is right, and the delete step has a side benefit —
   the current script creates `e2e-authing-key` on every run and never cleans up, so repeated
   runs accumulate keys toward quota on the test account. Have the E2E delete the key it
   created (the doc's rename→delete flow already does this; keep that ordering).
6. **Same-origin coverage for the new verbs**: one test that `DELETE /api/keys/{key_id}` and
   `PATCH` without `Origin`/`Referer` return `403`. `_assert_same_origin` skips only
   GET/HEAD/OPTIONS so the code path exists, but nothing exercises it for these methods.

---

## Acceptance Criteria Tweaks

- **A2**: scope to self-service surfaces and make it mechanical: "`grep` of
  `code/server/app` finds no `撤销`/`已撤销` in keys UI copy, and no `revoke` in
  user-facing strings" (N3 lists the two stragglers).
- **A6**: rephrase to a DB-level assertion: "after deleting a key that produced writes, the
  `write_audit_log` rows still exist with the original `api_key_id` string" — drop the
  "audit views render Deleted key" implication (N7).
- **A11 addition**: "`PATCH` with a label over 120 chars returns `422`" (N1).
- **New A13**: "Legacy rows with `revoked_at` set do not appear in `GET /api/keys` or
  `/ui/keys/` and do not count toward quota" (N2). This is the one migration-facing behavior
  and deserves its own criterion.
- **A12**: fine as optional, but note the E2E must delete the key it creates so repeated runs
  don't exhaust the test account's quota.

---

## One-Session Implementation Order

1. `db.py`: add `delete_api_key` (N4 shape), add `revoked_at IS NULL` filter to
   `list_api_keys_for_principal`, remove `revoke_api_key`.
2. `routes_keys.py`: replace revoke routes with `DELETE /api/keys/{key_id}` +
   `POST /ui/keys/{key_id}/delete`; update `_public_key_payload` (drop `revoked_at`, add
   `expires_at`); update button/copy; drop the status badge column.
3. `onboarding_service.py`: quota error copy (N3).
4. Tests: rename/adapt the two revoke tests, add the matrix rows and the gaps above.
5. Commit; then rename (PATCH + label form + tests) as a second commit if time allows (N8).
6. E2E extension last; it needs a deployed server and Authing secrets.
