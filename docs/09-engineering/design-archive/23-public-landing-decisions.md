# 23 — Public Landing decision summary

> Chinese version: [23-public-landing-decisions.zh.md](23-public-landing-decisions.zh.md)

> Status: decided and implemented (product ratify 2026-07-06; review PASS-WITH-NITS).
> Compressed archive decision summary; not contractual. Implementation and later changes follow formal docs and code.

## Background in one sentence

Unauthenticated users hitting an intranet instance (`http://<intranet-host>/`) were 302'd straight to Authing login, with no page explaining what ma3 is / what it can do / current status / how to register — so a public default page was added.

## Decisions

- **Route semantics**: `/ui/home/` is the canonical public landing page; unauthenticated `GET /`, `/ui`, `/ui/` → 302 `/ui/home/` → 200; authenticated visits to those paths (including `/ui/home/`) → 302 `/ui/me/`. Supersedes design/15 §2.4 root-only unauthenticated behavior; rest of IA unchanged.
- **Page structure**: single-column `page-narrow`, six sections: Hero → Problem → What ma3 is (yes/no two-column contrast) → Agent workflow five steps → What you can do after register (3 feature cards) → Live status → Get started in three steps; no subnav, no duplicate page-header title.
- **Top bar**: minimal header (brand → `/ui/home/` + login + locale switcher); do not render full topnav; v1 top bar does not add a “Community library” link.
- **CTA hierarchy**: primary “Register / Log in” → `/auth/login?next=/ui/me/`; secondary “Browse community library” → `/ui/libraries/lib_default/` (anonymous Stats); “Agent onboarding docs” → `/client/agent-onboarding.md`.
- **Live status data**: reuse existing backend only (no new public API): service version, instance ID, deploy time + community library `lib_default` aggregates for cases / records / active.
- **Authing not configured (LAN dev) branch**: Hero CTA becomes “Enter portal” → `/ui/me/`, with an in-page alert for dev mode.
- **Security boundary**: instance ID / version may be public (same as healthz); do not show global principal counts, git_commit, record content snippets, or Draft counts.
- **i18n**: full `landing.*` for zh-CN / en-US (~35–45 keys); Chinese copy was the original drafting source for UI strings (docs default language is English).
- **Visual**: GitHub light single-column marketing style; reuse `.btn` / `.card` / `.grid.stats`; add `.landing-hero` / `.landing-section` / `.landing-flow` / `.feature-grid`; no new fonts, illustrations, JS animation, or chart libraries.

## Explicit non-goals / rejected

- v1 will not: marketing separate domain / blog / pricing page, anonymous record list browse (Stats-only), MCP playground embedded in landing, multi-instance federation stats, Contributors aggregate.
- Rejected: render `/` as 200 directly (chose canonical `/ui/home/` + thin 302); Community library link in top bar (v1); showing Draft counts.
- Review leftover nits (non-blocking): 375px mobile screenshot acceptance pending owner spot-check; `docs/04-frontend/information-architecture.md` sitemap needs `/ui/home/`; OG tags deferred to v1.1.

## Landing locations

- Code: `app/api/routes_portal.py` (`portal_root` / `portal_home` / `_render_public_landing`), `app/api/ui_theme.py` (`MA3_CSS` landing classes), `app/main.py` root redirect, `app/api/i18n/{zh-CN,en-US}.json`.
- Tests: `tests/integration/test_public_landing.py` (6 cases) + portal/i18n regression.
- Related docs: design/15 (root semantics supersede), design/22 (minimal header reuse), `docs/04-frontend/ui-i18n-design-gpt55.md`.

## Historical drafts

The following originals were compressed and removed:

- `23-public-landing-page-fable.md` (product design lock)
- `23-public-landing-review-fable.md` (implementation review, PASS-WITH-NITS)
- `23-public-landing-visual-fable.md` (visual source draft)
