# 24 — Org & Library Management decision summary

> Chinese version: [24-org-library-management-decisions.zh.md](24-org-library-management-decisions.zh.md)

> Status: decided and implemented (product owner ratify 2026-07-06; GPT-5.5 ACCEPT-WITH-NITS and sonnet-5 REQUEST-CHANGES blocking items covered in ratify decisions).
> Compressed archive decision summary; not contractual. Formal docs, ADRs, and code win.

## Background in one sentence

On top of the v1 personal portal, v1.1 completes the human management loop for “org → library → grants → capacity”: org admins manage members and org libraries, library maintainers manage grants and in-library enumeration, users can see storage quotas; product admins (Observatory) do not participate in org business management.

## Decisions (ratified)

- **D1 = B**: Team library settings (including `write_buffer_hours`) are **editable by org admin**; personal libraries remain owner + product admin only. (Fixes sonnet-5 B1 team-library-no-owner dead-end.)
- **D2 = B**: Team org creation UI ships in **Phase O5** — `/ui/orgs/new/` + plan gate (Free → upgrade CTA; Pro → may create 1 team org); not a hard prerequisite for other v1.1 work.
- **D3 = B**: New org libraries default visibility **`private`**; choosing `org` / `public` requires secondary confirm with visibility explanation (adopt GPT-5.5 objection; reject original fable “default org”). `visibility=public` does not appear in the form (platform Community seed only).
- **D4 = B**: Library maintainers on `/records/` list can see buffered **metadata** (status, author, publish_at); **detail body open to author only** (other rows show “Pending publish”) — aligns with design/16 buffered 404 rules.
- **D5 = B**: Org library storage UI is **preview read-only** (usage numbers + tier table), **no billing enforcement**, deferred to billing Phase B3; only personal libraries show hard-limit progress bars.
- **D6 = B**: org admin → maintainer on all libraries in that org is declared **explicitly in `entitlement_service` code**, not only by hiding UI.
- **M1 (required for v1.1)**: Adding members supports **display-name prefix/substring search** + exact add; `user:…` prefix can search principals (covers former fable v1.2 defer).
- **M2 (required for v1.1)**: **Last-admin protection** — server rejects remove/demote of the last active admin (`403 last_org_admin`); UI disables the button in sync.
- **Permission model**: unauthorized deep links are always **404 (not 403)**; every SSR POST needs `_assert_same_origin` (CSRF); `entitlement_service` is the Phase O1 hard gate; UI routes must not merge ahead of the `org_members` migration.
- **Quantity quotas (ratified 2026-07-06)**: personal libraries Free 1 / Pro 5; team org libraries 10/org; creatable team orgs Free 0 / Pro 1; platform hard caps personal org 100 libraries, team org 1000 libraries, user 100 team orgs; over limit → `403 plan_library_limit_exceeded` / `403 platform_library_limit_exceeded`; Community `lib_default` never counted.
- **Schema**: extend `organizations` with `kind/owner_principal_id/billing_account_id`; add `org_members` (role admin|member, seat_status) and `library_grants` (reader|writer|maintainer); first-login bootstrap creates implicit personal org and backfills `libraries.org_id`.

## Explicit non-goals / rejected

- v1.1 will not: Stripe self-serve checkout, cross-org federation / library migration wizard, record-level fine RBAC, SPA rewrite, MCP `ma3_create_org`, invite links (v1.2), maintainer publishing someone else’s buffered record.
- Rejected: maintainer deleting others’ records (no, ADR-013); product admin managing arbitrary orgs (no, Observatory is observe-only); default org-library visibility `org` (changed to private); showing fake pooled storage limits for org libraries (while billing is unfinished, show preview / “contact admin”).
- No chart library: storage visualization uses pure CSS `.storage-meter` bars (≥80% warn, ≥100% full).

## Landing locations

- Code: `app/storage/db.py` (schema + helpers), `app/services/org_service.py` (member search, last-admin protection), `app/services/entitlement_service.py` (D6), `app/services/library_admin_service.py`, `app/services/library_quota_service.py` (quantity quotas), `app/api/routes_portal.py` (`/ui/orgs/*`, `/ui/libraries/{id}/{grants,records,storage}/`), `app/api/ui_theme.py` (`.org-card`, `.storage-meter`), i18n `portal.orgs.*`, etc.
- Tests: `tests/unit/test_org_service.py`, `tests/integration/test_org_library_portal.py` (acceptance O1–O10).
- Related docs: ADR-011, ADR-013, ADR-015, design/08 (KB access & org isolation), design/09 (billing & quotas), design/15, design/16 (write buffer), design/22.

## Historical drafts

The following originals were compressed and removed:

- `24-org-library-management-decisions-for-owner.md` (product ratify decision table; main source for this summary)
- `24-org-library-management-fable.md` (product/engineering design lock)
- `24-org-library-management-review-gpt55.md` (GPT-5.5 review, ACCEPT-WITH-NITS)
- `24-org-library-management-review-sonnet5.md` (sonnet-5 review, REQUEST-CHANGES → covered by decisions)
- `24-org-library-management-visual-fable.md` (visual design draft)
