# Pricing and Plans (User-Facing Summary)

> Chinese version: [pricing-and-plans.zh.md](pricing-and-plans.zh.md)

> Technical spec: [../03-backend/billing-and-quotas.md](../03-backend/billing-and-quotas.md)
> Commercial narrative: [pitch.md](../01-product/pitch.md)

## Three plan tiers (v1 starting point)

| | **Free** | **Pro** | **Team** |
|---|----------|---------|----------|
| Scope | Personal | Personal | Organization |
| Read-only keys | ❌ | ✅ | ✅ |
| Personal libraries | 1 | 5 | — |
| Org libraries | — | — | 10 |
| Total records | 3,000 | 50,000 | 100,000 (pooled) |
| Monthly read units | 10,000 | 100,000 | 500,000 |
| Seats | 1 | 1 | 5 |
| API keys | 10 | 50 | 200 |
| Deletion protection (`deletion_protection`) | ❌ | ❌ | ✅ |
| Support | best-effort | best-effort | best-effort (formal SLA planned for v1.1+) |

## Billing principles

- **Reads** (`ma3_context` / `ma3_case`) count toward read units; **writes** (`ma3_report`) are **not** penalized
- Writing to the **public Community library** does not consume the writer's personal storage quota
- Over storage quota: the library becomes **read-only** (writes blocked, reads unaffected)
- Over read quota: 429 + `Retry-After`

## v1 payments

- **No Stripe**; `plan_code` is set manually by a platform administrator
- Upgrade CTA points to `/ui/billing/` (Phase B4)

## To be added

- [ ] Public pricing page copy
- [ ] Pro vs Team packaging explanation
- [ ] Overage business policy
