# 28 — Fable fix design: OAuth dual-auth + onboarding review remediation

> Date: 2026-09-11. Author: Fable (design). Implementer: Composer.
> Basis: Fable acceptance review + Bugbot findings on ADR-016 OAuth and connect UX.
> Status: **design locked for immediate implementation** (owner asked to fix all listed items).

## 0. Verdict of prior review

**SHIP-WITH-FIXES** → this note turns the fix list into concrete decisions.

## 1. Scope (must fix)

| ID | Severity | Problem |
|----|----------|---------|
| U1 | P1 | Canonical public base / resource / challenge / PRM split when `MA3_PUBLIC_BASE_URL` unset |
| U2 | P2 | Portal paste / Cursor JSON ignore public base |
| E1 | P1 | OAuth Layer-1 projection includes API Key grants |
| K1 | P1 | PKCE verifier/challenge not RFC 7636-strict |
| R1 | P1 | `ma3k_` / `ma3mcp_` missing from auto-redaction |
| S1 | high | `/oauth/authorize` skips display-name setup |
| D1 | P2 | `dev_api_key` resolved before DB API key |

Out of scope for this patch (tracked, not blocking this remediation): ambient consent UI, OAuth token list UI, token/code GC job, full CIMD/DCR, zh.md in sync manifest.

## 2. Locked decisions

### U1 / U2 — Single canonical base resolver

Add `app.core.public_url`:

```text
resolve_public_base_url(request=None) →
  1) settings.public_base_url if set
  2) else request.base_url if request provided
  3) else http://127.0.0.1:8000

resolve_mcp_resource_url(request=None) → {base}/mcp
resolve_oauth_prm_url(request=None) → {base}/.well-known/oauth-protected-resource
```

Rules:

- PRM, AS metadata, authorize `resource` check, token endpoint `resource` check, and `WWW-Authenticate` **all** use the request-aware resolver.
- Portal `_base(request)` and paste-to-agent / Cursor JSON use the same helper (prefer configured public base over raw `request.base_url`).
- Token audience check at MCP resolve: token.resource must match an **acceptable resource set** for this request:
  - always include `resolve_mcp_resource_url(request)` when Request is available
  - always include `settings.mcp_resource_url()` when `public_base_url` is set
  - expand each candidate with localhost ↔ 127.0.0.1 ↔ `[::1]` host aliases (same scheme/port/path)
- When `public_base_url` is unset and no Request is available (rare unit path): fall back to settings default + localhost aliases only.

Do **not** require `MA3_PUBLIC_BASE_URL` for LAN OAuth in this patch; prefer request-derived consistency. Production should still set it for stable external URLs behind reverse proxies.

### E1 — Strict Layer-1 for OAuth (and portal entitlement enumeration)

Remove API Key grant walks from:

- `entitled_library_ids`
- `can_read_library`

`mcp_grants_for_principal` then truly projects Layer-1 only (personal owner, `library_grants`, org membership/visibility/admin, community defaults).

Layer-2 stays exclusively on `resolve_api_key` / DB key path.

Portal “My libraries” may stop listing libraries that were **only** reachable via a key; that is intentional (keys are not portal entitlements). Key prefixes may still annotate libraries the user also has Layer-1 access to.

### K1 — Strict PKCE

- `code_verifier`: `^[A-Za-z0-9\-._~]{43,128}$` (RFC 7636)
- `code_challenge` (S256): base64url without padding, length 43 (`[A-Za-z0-9_-]{43}`)
- Fail authorize with `invalid_request`; fail token with `invalid_grant`

### R1 — Redaction

Add patterns:

- `\bma3k_[A-Za-z0-9_-]{16,}\b` → `[REDACTED:api_key]`
- `\bma3mcp_[A-Za-z0-9_-]{16,}\b` → `[REDACTED:token]`
- keep legacy `ma3v4_`

### S1 — Setup gate on authorize

After session present, if `display_name_setup_required(principal)` → redirect `/ui/me/setup/?next=<original authorize URL>` (same next preservation pattern as portal). Do not issue codes until setup completes.

### D1 — Credential order

In `resolve_from_credential`: DB API key lookup **before** `dev_api_key`. Dev/env keys remain break-glass only when the plaintext is not a stored DB key. Update ADR-016 Decision 5 wording if it claimed otherwise.

## 3. Tests (acceptance)

| ID | Scenario |
|----|----------|
| T-U1a | `public_base_url=None`, request Host=LAN → PRM resource uses LAN; authorize with that resource succeeds |
| T-U1b | localhost vs 127.0.0.1 alias accepted for resource match |
| T-U1c | WWW-Authenticate metadata URL uses request base when public unset |
| T-E1 | Principal has key grant on private lib but no Layer-1 → OAuth whoami cannot read that lib; key whoami can |
| T-K1 | verifier len 42 / 129 / illegal char → token `invalid_grant`; challenge bad → authorize error |
| T-R1 | redact_text covers `ma3k_` and `ma3mcp_` |
| T-S1 | session without display name → authorize redirects to setup, not code |
| T-D1 | plaintext equals both DB key and `MA3_DEV_API_KEY` → resolves as `db_api_key` not admin bypass |

## 4. Doc sync (light)

- Amend ADR-016 Decision 5 order: DB key before env/dev; OAuth last.
- Note redirect allowlist reality (localhost + cursor/vscode schemes) if space — optional one-liner.
- authentication.md: OAuth needs consistent public base / Host; recommend `MA3_PUBLIC_BASE_URL` behind proxies.

## 5. Non-goals this patch

Consent screen, token revocation UI, code/token GC, CIMD, putting `.zh.md` into sync manifest.

## 6. GPT-5.6 follow-up patch (2026-09-11)

Accepted after request-changes:

1. Token endpoint now passes `expected_resource` + `request` into `exchange_authorization_code`; missing/wrong `resource` → `invalid_target`; bound resource must be acceptable for the token request Host.
2. Portal `list_entitled_libraries` role/access is Layer-1 only; `key_prefixes` remain annotation; key-only libs stay off the list.
3. `authentication.md` / `.zh.md` document production `MA3_PUBLIC_BASE_URL` + Host-spoof risk when unset.
