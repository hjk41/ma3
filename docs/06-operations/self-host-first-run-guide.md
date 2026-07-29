# Self-host first-run guide — design

> Chinese version: [self-host-first-run-guide.zh.md](self-host-first-run-guide.zh.md)

> **Status**: Implemented  
> **Date**: 2026-07-28  
> **Scope**: Compose / self-host when **OIDC is off** and **`MA3_LOCAL_AUTH=1`** (default).  
> **Related**: [self-hosting.md](self-hosting.md), [ADR-015](../02-architecture/decisions/015-oidc-pluggable-selfhost-bootstrap.md)

---

## 1. Problem

Fresh self-host today is technically runnable, but the **human path is under-guided**:

| Gap | Today | Risk |
|-----|--------|------|
| First admin | Buried behind generic "Sign up / Sign in"; first registrant is admin only by convention | Operator creates a throwaway account first, then their real account has no Observatory |
| Landing copy | Still mixes SaaS Authing get-started with bootstrap/local alerts | Confused CTAs (MCP vs portal) |
| Dual credentials | Bootstrap API key + local portal coexist with little sequencing | People skip portal or skip MCP |
| After admin | No checklist for key mint / close registration / agent wire-up | Instance stays open-registration forever on LAN/public |
| Progress | No durable “setup done” signal | Wizard can’t disappear cleanly |

**Goal**: one **guided rail** from `./up.sh` → first admin → first API key → agent MCP → optional harden (close signup / later OIDC), without blocking power users who already know the paths.

---

## 2. Principles

1. **One primary path** for day-0 humans: create **admin** → use **portal**. MCP bootstrap key is a **parallel** agent rail, not the first CTA.
2. **First local account = instance owner (admin)** — make that explicit in UI copy and redirects; never bury it.
3. **Checklist, not a modal jail** — skippable after admin exists; unfinished steps show a dismissible but reappearing banner until marked done or auto-cleared.
4. **State from DB, not only cookies** — “has admin?” / “setup complete?” must survive browsers; cookies only store “dismissed for this browser”.
5. **OIDC supersedes** — when `oidc_configured`, this wizard is off (existing Authing/OIDC journey).
6. **`MA3_LOCAL_AUTH=0`** — wizard off; keep bootstrap-only pages (current 503 explain).

---

## 3. Setup states

Detect with existing data (no new product tables required for v1; optional `instance_setup` row later).

| State | Condition | Operator feeling |
|-------|-----------|------------------|
| **A — Needs owner** | `local_auth_enabled` ∧ `count(local_accounts)=0` | “Create the admin account” |
| **B — Guided ramp** | ≥1 local account ∧ setup checklist incomplete | “Finish wiring agents / harden” |
| **C — Steady** | Checklist complete **or** admin dismissed permanently | Normal landing / portal |

**Checklist items (state B)** — all optional except those marked required for “complete”:

| ID | Item | Required for “complete”? | How to detect “done” |
|----|------|--------------------------|----------------------|
| C1 | Create admin (already true in B) | yes (gate into B) | `count(local_accounts)≥1` |
| C2 | Sign in as admin (session) | no | session present + `is_admin` |
| C3 | Mint at least one **non-bootstrap** API key for the admin principal | **yes** | `api_keys` for admin `principal_id` excluding bootstrap principal if distinct |
| C4 | Close open registration (recommended on non-loopback) | recommended | `MA3_LOCAL_AUTH_OPEN_REGISTRATION=0` **or** admin clicked “I’ll keep open” (ack) |
| C5 | Connect an agent (MCP smoke) | soft | Optional: admin clicked “I’ve configured MCP” **or** first successful authenticated `ma3_whoami` from a non-browser UA (best-effort; v1 = manual ack) |

v1 completeness rule: **C1 + C3 + (C4 done or C4 explicitly skipped)**.

---

## 4. User journeys

### 4.1 Day-0 (state A)

```text
./up.sh → open MA3_PUBLIC_BASE_URL
        → /  and /ui/home/ redirect to /ui/setup/  (or render setup as home)
        → Step 1: Create admin account (username + password + display name)
        → POST /auth/register (same backend; UI framed as "Create admin")
        → auto sign-in → /ui/setup/?step=keys  (state B)
```

**Do not** show the long SaaS marketing landing as the first screen in state A. A short brand line is enough; the page is a **setup wizard**.

### 4.2 Ramp (state B)

Wizard / banner steps:

1. **API Key** — deep link `/ui/keys/` with highlight; copy one-liner for Cursor MCP (`MA3_BASE_URL`, `X-API-Key`).
2. **Optional: bootstrap key** — secondary card: “Agents can also use the bootstrap key from the container” + command snippet (not primary).
3. **Harden** — recommend closing registration; button "Close open registration" → either:
   - **v1**: show instructions to set env + restart, **or**
   - **v1.1**: persist `open_registration=false` in DB overriding env (preferred later).
4. **Done** — "Finish setup" → state C; landing returns to normal product home with local-auth CTA.

### 4.3 Returning visitor (state C)

Normal `/ui/home/` product landing; primary CTA = Sign in / Enter portal. No forced wizard.

### 4.4 Second human user

Register still works if open registration is on; copy warns "You are not the first user; no Observatory by default — contact the admin for elevation". Admin uses `/ui/observatory/local-users/`.

---

## 5. UI surfaces (implementation sketch)

| Surface | Role |
|---------|------|
| `GET /ui/setup/` | Wizard shell (state A/B). Auth: none for A; admin session preferred for B. |
| `GET /ui/home/` | If state A → **302** `/ui/setup/`. If B → home **plus** top checklist banner. If C → current landing (copy fixed for self-host). |
| `GET /` | Same as home (already redirects). |
| `/auth/register` | If state A → title/copy = **Create admin account**; hide "Already have an account? Sign in" or demote it. If B/C → normal register. |
| `/auth/login` | Unchanged; secondary from setup. |
| Portal `/ui/me/` | After first login from setup, soft banner until checklist complete. |
| Observatory | Unchanged ACL; setup links "Manage users" only when admin. |

### 5.1 Setup page wireframe (state A)

```text
[ ma3 self-host ]
Create admin account
This is the first user of this instance and will automatically get admin
privileges (Observatory, user management).

[ Username ]
[ Password ]
[ Display name (optional) ]

[ Create and enter ]

Secondary: Agent only? View the MCP bootstrap key → /mcp/info
```

### 5.2 Setup page wireframe (state B)

```text
This instance already has an admin. Finish the steps below for daily use:

☑ Admin account
☐ Issue an API Key        [Issue]
☐ Close open registration [Handle] / [Later]
☐ Configure Agent MCP     [View instructions]

[ Finish setup ]
```

---

## 6. Backend / config

### 6.1 Detection helpers

```text
setup_needs_owner()  := local_auth_enabled && count_local_accounts() == 0
setup_in_progress()  := local_auth_enabled && count_local_accounts() >= 1 && not setup_complete()
setup_complete()     := instance flag OR (has_admin_key && registration_ack)
```

### 6.2 Persistence

Table `instance_settings(key, value, updated_at)`:

| key | meaning |
|-----|---------|
| `setup_complete` | `0`/`1` — admin finished or auto conditions met |
| `setup_registration_ack` | `keep_open` when admin chose “decide later” |
| `local_registration_open` | `true`/`false` — **overrides** `MA3_LOCAL_AUTH_OPEN_REGISTRATION` when set |

Env remains the default when no DB value exists. Toggle from `/ui/setup/` or Observatory; no restart required.

### 6.3 Security

- State A register is open by design (empty instance).
- After first admin, keep current open-registration flag; wizard **pushes** closing it.
- Setup pages must not expose bootstrap plaintext in HTML; link to `/mcp/info` or authenticated reveal only.
- Same-origin on all POSTs (existing).

---

## 7. Copy / i18n

Replace self-host contradictions:

- `landing.getstarted.s1` Authing → self-host variants under `landing.selfhost.*` / `setup.*`.
- Alert `landing.local_auth_alert` → short; wizard owns the long explanation.
- Register strings when `setup_needs_owner`: `auth.local.register_admin_title`, etc.

Locales: `zh-CN` + `en-US` required.

---

## 8. Docs / CLI alignment

| Touchpoint | Change |
|------------|--------|
| `deploy/self-host/up.sh` | On success, print: `Open http://…/ui/setup/ to create the admin account` (not only healthz). |
| `verify.sh` | Optional soft check: if local_auth and 0 accounts → warn “admin not created yet”. |
| [self-hosting.md](self-hosting.md) | Point day-0 at `/ui/setup/`; keep advanced OIDC section. |
| This design | Normative; Status = Implemented (I1–I4 + REST APIs). |

---

## 8.1 Agent APIs (no browser)

**MCP** = knowledge loop (`ma3_context` / `ma3_report` / `ma3_feedback` / …).  
**REST** = all other portal operations. Tables + full curl: [self-hosting.md](self-hosting.md#agent-surface-mcp--rest), [api-overview.md](../03-backend/api-overview.md).

| Flow | Endpoint |
|------|----------|
| Status | `GET /api/setup/status` |
| Create admin (+ optional API key) | `POST /api/auth/register` |
| Login → mint API key | `POST /api/auth/login` |
| Close / open registration | `PATCH /api/setup/registration` |
| Ack keep-open | `POST /api/setup/registration/ack` |
| Finish setup | `POST /api/setup/complete` |
| List / promote users | `GET/PATCH /api/local-users` |
| Me / keys | `GET /api/me`, `GET/POST /api/keys` |
| Org + members + library | `POST /api/orgs`, `…/members`, `…/libraries` |
| **Invite link** | `POST /api/orgs/{id}/invites` → share `invite_url`; register with `invite` auto-joins |
| Library grants | `POST /api/libraries/{id}/grants` |
| Knowledge | MCP tools (not REST) |

Bootstrap API key remains for MCP knowledge access only; a **user** API key (admin for setup/orgs) is required for management REST.

**Invite model:** org admin generates a one-time/limited link (`/auth/register?invite=…`). Signup with that token joins the org even if open registration is closed. Manual add-member and open-registration remain available.

---

## 9. Out of scope (v1)

- Full OIDC first-run wizard (separate).
- Migrating bootstrap principal into the first local admin (can document “optional link later”).
- Email verification / magic-link login (invite tokens cover org join without email).
- Forced password rotation.
- Auto-detect MCP client success without manual ack (nice-to-have).
- MCP tools that wrap setup/register/org admin (use REST; intentional).

---

## 10. Implementation phases

| Phase | Deliverable | Exit criteria |
|-------|-------------|---------------|
| **D0** | This doc + links from self-hosting.md | Review OK |
| **I1** | State A: home→setup, admin-framed register, post-register → setup step keys | Fresh compose: only path to portal is create admin |
| **I2** | State B checklist UI + C3 detection + complete/dismiss | Admin can finish ramp without reading markdown |
| **I3** | `instance_settings` + registration harden UX; up.sh message; i18n polish | Checklist survives refresh; docs match UI |
| **I4** | Tests: setup redirects, first user admin framing, checklist transitions | pytest green |
| **I5** | JSON `/api/auth/*`, `/api/setup/*`, `/api/local-users` | Agent curl day-0 without browser |
| **I6** | JSON `/api/me`, `/api/keys` (X-API-Key), `/api/orgs`, `/api/libraries`, `/api/admin` | Agent org+member+grant+MCP without browser |

---

## 11. Success metrics (qualitative)

- New operator can go from healthy `/healthz` to **admin session + API key** without reading ADR.
- Agent can go from healthy `/healthz` to **admin API key + org + member grant + MCP** via REST + MCP only.
- No accidental “second account is not admin” surprise when they followed the wizard (only one create-admin screen in state A).
- Landing no longer tells self-host users to "register with Authing".

---

## 12. Open questions (resolve at implement start)

1. **Registration close in-app (DB)** vs **env-only instructions** for I2/I3? → Prefer DB override (P1) if low cost. **Done (DB).**
2. Should `/mcp/info` stay public in state A? → **Yes**, secondary rail.
3. Root URL when state B and user logged out — show banner on public home or only after login? → Banner on home for admins after login; logged-out home shows "Sign in to continue setup" if `setup_in_progress`.
