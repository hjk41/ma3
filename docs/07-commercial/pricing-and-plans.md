# 定价与套餐（用户向摘要）

> 技术规格：[../03-backend/billing-and-quotas.md](../03-backend/billing-and-quotas.md)  
> 商业叙事：[pitch.md](../01-product/pitch.md)

## 三档套餐（v1 起点）

| | **Free** | **Pro** | **Team** |
|---|----------|---------|----------|
| 范围 | 个人 | 个人 | 组织 |
| 只读 key | ❌ | ✅ | ✅ |
| 个人库数 | 1 | 5 | — |
| org 库 | — | — | 10 |
| 记录总量 | 3,000 | 50,000 | 100,000（pooled） |
| 月 read units | 10,000 | 100,000 | 500,000 |
| seats | 1 | 1 | 5 |
| API keys | 10 | 50 | 200 |
| 防误删（deletion_protection） | ❌ | ❌ | ✅ |

## 计费原则

- **读**（`ma3_context` / `ma3_case`）计 read units；**写**（`ma3_report`）**不**惩罚
- 写 **Community 公共库**不占 writer 个人 storage quota
- 超 storage：该库**只读**（禁写，读不受影响）
- 超 read quota：429 + `Retry-After`

## v1 支付

- **无 Stripe**；`plan_code` 由平台管理员手工设置
- 升级 CTA 指向 `/ui/billing/`（Phase B4）

## 待补充

- [ ] 对外定价页文案
- [ ] Pro vs Team 包装说明
- [ ] Overage 商业策略
