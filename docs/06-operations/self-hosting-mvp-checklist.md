# Self-Hosting MVP Rework Checklist

> Chinese version: [self-hosting-mvp-checklist.zh.md](self-hosting-mvp-checklist.zh.md)

> **Goal**: a stranger can, on a clean machine, using docs + Compose, get a usable private ma3 (MCP read/write) running in **≤1 hour**, and the default configuration must not expose the instance as a public backdoor.  
> **Non-goals (not in MVP)**: federated public libraries, Stripe, enterprise SAML, multi-node HA, official Community sync.  
> **Status anchors**: Apache-2.0 already in place; `deploy/deploy.sh` targets "our own remotes"; the main Auth path is still tied to Authing; no official server Compose.

---

## Decided (2026-07-20)

| # | Topic | Decision |
|---|------|------|
| 1 | Auth | **Decouple the IdP**: pluggable user-provided **OIDC**; **when OIDC is not configured**, default to a **local account portal** (`MA3_LOCAL_AUTH=1`) + **bootstrap key** (MCP); both run in parallel |
| 2 | Embeddings | Compose / self-hosting default **on** (`MA3_DISABLE_EMBEDDINGS` off by default; docs spell out HF cache and size) |
| 3 | Reverse proxy | **Not a hard prerequisite** (see explanation below); MVP defaults to direct LAN access; a reverse proxy + HTTPS is **recommended** for public internet / OIDC scenarios |
| 4 | Support | **No SLA**; GitHub Issues / Discussions **best-effort** |

### On "why a reverse proxy?" (explanation for decision 3)

**A reverse proxy is not an ma3 protocol requirement, nor a prerequisite for the bootstrap-key LAN mode.**

Uvicorn can listen on a port directly. Caddy/nginx keep coming up because they solve **exposure-surface and login-flow** problems, not MCP itself:

| Scenario | Reverse proxy needed? |
|------|------------|
| Local / LAN, bootstrap API key only, HTTP | **No**. Compose bound to `0.0.0.0:8000` or a host port is fine (mind the firewall) |
| Want the **OIDC login portal** | **Strongly recommended**. Most IdPs require an **HTTPS** callback URL and a stable domain; TLS termination at the proxy is easiest |
| Exposing the instance to the **public internet** | **Strongly recommended**. The proxy provides TLS, optional rate limiting / IP allowlists, and avoids exposing bare uvicorn + the admin surface directly |
| Access only via SSH tunnel | No proxy needed; equivalent to "for yourself only" |

Suggested MVP doc wording:

- Default path: "direct LAN access + bootstrap key" — zero reverse proxy  
- Advanced path: "public internet or OIDC → bring your own reverse proxy (example Caddyfile) + `MA3_PUBLIC_BASE_URL=https://…`"

---

## Definition of Done (Done = all checked)

- [x] `deploy/self-host` Compose + Dockerfile + initdb pgvector + up/verify (see [self-hosting.md](self-hosting.md))
- [x] **Without OIDC**: startup bootstrap → `MA3_BOOTSTRAP_KEY_FILE`; local portal `MA3_LOCAL_AUTH` (registration/login/Observatory user management)
- [x] **With OIDC**: `MA3_OIDC_*` (`MA3_AUTHING_*` compatibility aliases) + ADR-015 (local auth disabled in this case)
- [x] Authing demoted to just one OIDC configuration / path-compatible
- [x] Compose disables `MA3_DEV_AUTH` by default; embeddings on by default
- [x] Docs: Community semantics, reverse proxy non-mandatory, **no SLA**; root `SECURITY.md`
- [ ] End-to-end: actually run `./up.sh` + MCP report on a clean machine (manual check before release)
- [ ] Sweep intranet IP examples from historical docs (P0-E1, can run in parallel)

---

## P0 — Must Do

### A. Deliverable: one-command stack

| ID | Item | Output | Notes |
|----|----|------|------|
| A1 | Official `docker-compose.yml` (server + Postgres/pgvector) | `deploy/self-host/docker-compose.yml` | do not reuse the eval compose |
| A2 | Server `Dockerfile` (production-oriented) | `deploy/self-host/Dockerfile` etc. | |
| A3 | Self-hosting env template | `deploy/self-host/.env.example` | kept separate from the SSH `deploy.env.sample` |
| A4 | Entry scripts | `up.sh` + `verify.sh` | |
| A5 | Data volume conventions | volumes + docs | DB, **HF cache (embeddings on by default)** |
| A6 | (Optional) example Caddyfile | `deploy/self-host/Caddyfile.example` | public/OIDC advanced path; not a default dependency |

### B. Auth: pluggable OIDC + bootstrap by default

| ID | Item | Output | Notes |
|----|----|------|------|
| B1 | **OIDC abstraction** (ADR) | `docs/02-architecture/decisions/0xx-oidc-provider.md` | config: issuer, client_id/secret, redirect; Authing = documented example |
| B2 | Decouple Authing-specific assumptions in code | `auth/` becomes a generic OIDC client | keep Authing env aliases as a compatibility layer (optional) |
| B3 | **No OIDC configured → bootstrap key mode** | at startup or via a `bootstrap_selfhost` command | create admin/principal + personal lib + writer key, print once to stdout; portal login can be disabled or show "OIDC not enabled" |
| B4 | Startup guardrails | config validation | without OIDC, do not require the Authing semantics of `MA3_AUTH_ADMIN_USERS`; public internet + `DEV_AUTH=1` still refuses to start |
| B5 | Self-hosting Auth docs | `self-hosting.md` | two sections: Bootstrap quickstart / bring your own OIDC (with Authing example) |

### C. Dependencies: Postgres / vector / embeddings (on by default)

| ID | Item | Output | Notes |
|----|----|------|------|
| C1 | Compose Postgres + pgvector | image + init | superuser `CREATE EXTENSION vector` |
| C2 | App role does not create extensions itself | init/runbook | |
| C3 | **Embeddings enabled by default** | `.env.example` does not set disable | docs: first-pull size, proxy, `HF_HOME/hub`, `HF_HUB_OFFLINE=1` afterwards; weak machines can disable explicitly |
| C4 | Fernet secret | `.env.example` | if lost, stored key plaintexts cannot be decrypted |

### D. Docs and Narrative

| ID | Item | Output | Notes |
|----|----|------|------|
| D1 | Dedicated self-hosting chapter | `docs/06-operations/self-hosting.md` | includes a "when do you need a reverse proxy" section (same as table above) |
| D2 | Self-hosting entry in README | root README | |
| D3 | Community semantics | D1 | self-hosted ≠ ma3.io |
| D4 | Support statement | README / D1 | **best-effort, no SLA** |
| D5 | Minimal acceptance checklist | verify scripts | both the bootstrap and OIDC paths |

### E. Repo Hygiene and Security Baseline

| ID | Item | Output | Notes |
|----|----|------|------|
| E1 | Clean intranet IP / host examples | docs and samples | |
| E2 | `SECURITY.md` | repo root | |
| E3 | Re-check secrets gitignore | | |
| E4 | Default network exposure policy | compose + docs | direct LAN access allowed by default; docs warn that public exposure must use TLS/reverse proxy or a firewall; **do not make the reverse proxy a hard dependency** |

---

## P1 — First Wave After Open-Sourcing

| ID | Item | Description |
|----|----|------|
| F2 | Backup / restore one-pager | `pg_dump` / volumes |
| F3 | Upgrade guide | server + migrate + Scheme B client |
| F4 | systemd example | for non-Docker users |
| F5 | CONTRIBUTING + issue templates | environment fingerprint includes auth mode (bootstrap / oidc) |
| F6 | Trademark note | |
| F7 | SQLite positioning | dev-only, or moved out of the main self-hosting docs |
| F8 | OIDC compatibility matrix | spot-check records for Keycloak / Authentik / Authing / Google |

---

## P2 — Can Be Deferred

| ID | Item |
|----|----|
| G1 | Federation / mirroring the official Community |
| G2 | Helm / K8s |
| G3 | HA |
| G4 | Pluggable embedding models |
| G5 | Productized "disable quotas" for self-hosting |

---

## Suggested Implementation Order (adjusted per decisions)

```text
Iteration 1 — can announce "experimental self-hosting"
  B1–B3 (OIDC abstraction skeleton + bootstrap default)
  A1–A5, C1–C4 (Compose + embeddings on)
  D1–D5, E1–E4
  A6 optional example reverse proxy config

Iteration 2 — "recommended self-hosting"
  B2/B5 polish multi-IdP
  F2–F5, F8

Iteration 3
  F6/F7, G* as needed
```

---

## Explicitly Not Doing (write into self-hosting docs)

- Self-hosted instances auto-connecting to ma3.io public knowledge  
- Account interoperability with the official instance  
- Community support SLA  
- Treating the internal `deploy/deploy.sh` (SSH push to our machines) as the community's main path — Compose is the externally promoted path  

---

## Decision Status

| # | Status |
|---|------|
| 1 Auth / OIDC / bootstrap | **decided** |
| 2 Embeddings on by default | **decided** |
| 3 Reverse proxy | **decided**: not mandatory; recommended for public/OIDC (see above) |
| 4 No SLA | **decided** |

Next: open issues per iteration 1 or start directly (suggested: B1 ADR + bootstrap command first, then Compose).
