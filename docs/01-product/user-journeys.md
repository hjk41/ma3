# User Journeys

> Chinese version: [user-journeys.zh.md](user-journeys.zh.md)

## J1 — New individual developer: from zero to first write-back

```text
Discover ma3 → open /ui/keys/ in browser
  → Sign up / log in via Authing
  → /auth/callback: create principal + personal library
  → /ui/me/setup/: one-time display name setup
  → /ui/keys/: create key (personal + Community writer)
  → Copy key → configure agent MCP (X-API-Key)
  → ma3_whoami confirms both libraries
  → ma3_report (no library_id) → written to personal library
  → /ui/me/: overview shows "Recent contributions"
```

Details in [../05-agent/getting-started.md](../05-agent/getting-started.md).

## J2 — Contributor: view and manage own writes

```text
/ui/me/ → stat "Records" → /ui/me/writes/
  → sort/filter (e.g. "pending publish")
  → click record → /ui/records/{id}/
  → buffered: publish / edit / delete
  → active: read-only + vote
```

Write buffer semantics in [../03-backend/write-buffer.md](../03-backend/write-buffer.md).

## J3 — Agent: task loop (query → do → write back)

```text
Task starts → ma3_context(query)
  → adopt matching record → verify locally
  → ma3_validate (optional dry-run)
  → ma3_report → response status/buffer/publish_at
  → if buffered: policy tells user they can publish early in the portal
  → for wrong records ranked above the adopted answer → ma3_feedback downvote
```

## J4 — Product admin: global observability

```text
Log in → /ui/me/ (same as regular users)
  → top bar Observatory (admin only)
  → global Stats + enumeration + search explain
  → non-admin direct access → 403 + "Back to my home"
```

## J5 — Deleting a leaked API Key

```text
/ui/keys/ → identify key → delete (confirm)
  → MCP immediately returns 401
  → create new key → update agent config → delete old key (if still present)
```

Details in [../04-frontend/api-keys-ui-and-api.md](../04-frontend/api-keys-ui-and-api.md).

## Journeys reserved for v1.1

- **J6** Org admin invites members, creates org library
- **J7** Library admin manages grants, enumerates records in a library
- **J8** Upgrade to Pro/Team, read-only keys, quota alerts
