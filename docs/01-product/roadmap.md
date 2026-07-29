# Product Roadmap

> Chinese version: [roadmap.zh.md](roadmap.zh.md)

> Cross-reference with [feature-index.md](feature-index.md); architecture North Star in [vision.md](vision.md)

## v1 core (current delivery scope)

| Domain | Capability |
|----|------|
| Agent surface | Remote MCP + policy + client sync (Scheme B) |
| Identity | Authing login; API Key (DB grants); display name setup |
| Knowledge | Case/record/relation; active default writes; write buffer; vote-based ranking |
| Portal | `/ui/me/*` default landing; Stats ≠ Enumerate; record/vote lists |
| Admin | Observatory (admin only, 403); startup validation of admin allowlist |
| Deployment | profile-saas primary; profile-lan dev |

## Explicitly out of v1

See [../README.md](../README.md) § "v1 non-goals list".

## v1.1 candidates

| Item | Description |
|----|------|
| Org UI | `/ui/orgs/*`, members, seats |
| Library admin UI | `/ui/libraries/{id}/records/` enumeration, grants |
| MCP key issuance | `ma3_create_key` / `ma3_list_keys` |
| Full billing enforcement | Stripe, quota 429, upgrade UI |
| Entitlement resolver | Replace v1 heuristics |
| URL beautification | `/ui/records/`, `/ui/votes/` canonical |
| refute/verify ranking bump | Wire into GTN once target relations are persisted |

## v2+ directions (not committed)

- Enterprise SAML / SSO extensions
- Cross-org federated search
- Hook default upload (still violates current ADR-006; requires re-decision)
- Full review queue UI
