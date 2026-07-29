# Page Specification Index

> Chinese version: [page-specifications.zh.md](page-specifications.zh.md)

> Portal IA and global shell: see [information-architecture.md](information-architecture.md)  
> Permissions and role matrix: see [portal-permissions.md](portal-permissions.md)  
> Visual tokens: see [visual-design-system.md](visual-design-system.md)

Page specifications for each module are maintained in separate documents:

| Module | Document | Routes |
|------|------|------|
| User portal (overview / writes / votes / libraries) | [information-architecture.md](information-architecture.md) §3 | `/ui/me/*`, `/ui/libraries/*`, `/ui/records/*` |
| API Keys | [api-keys-ui-and-api.md](api-keys-ui-and-api.md) | `/ui/keys/*` |
| Display name registration | [display-name-registration.md](display-name-registration.md) | `/ui/me/setup/` |
| Observatory (admin) | [portal-permissions.md](portal-permissions.md) §3 | `/ui/observatory/*` |

## Common List Page Contract

The writes page (`/ui/me/writes/`) and votes page (`/ui/me/votes/`) share a **standard list shell**:

```text
.page-header (h1 + subtitle)
  → .filter-pills
  → .card > table.data (sortable columns)
  → [batch bar] (writes page only, buffered)
  → .list-footer (total + per_page + pagination)
```

**Query parameter allowlist**: `page`, `per_page` (10/25/50/100), `sort`, `dir`, module-specific filters (`status` / `vote`).

## Global Interaction Conventions

- Destructive actions: inline `<form>` + `confirm`; SSR, no modal framework
- Unauthorized URL access: 404 (does not leak existence); Observatory for non-admin: 403
- Empty state: `.empty` + CTA linking to onboarding / create key
- Same-origin: all mutating POSTs validate `Origin` / `Referer`

For detailed copy conventions, see [ui-copy-and-interactions.md](ui-copy-and-interactions.md) (to be completed).
