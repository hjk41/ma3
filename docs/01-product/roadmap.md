# 产品路线图

> 与 [feature-index.md](feature-index.md) 对照；架构 North Star 见 [vision.md](vision.md)

## v1 core（当前交付范围）

| 域 | 能力 |
|----|------|
| Agent 面 | Remote MCP + policy + client sync（Scheme B） |
| 身份 | Authing 登录；API Key（DB grants）；display name setup |
| 知识 | Case/record/relation；active 默认写；write buffer；投票排序 |
| 门户 | `/ui/me/*` 默认落地；Stats≠Enumerate；记录/投票列表 |
| 管理 | Observatory（admin only，403）；启动校验 admin 白名单 |
| 部署 | profile-saas 首要；profile-lan dev |

## v1 明确不做

见 [../README.md](../README.md) §「v1 不做清单」。

## v1.1 候选

| 项 | 说明 |
|----|------|
| Org UI | `/ui/orgs/*`、成员、seat |
| 库管理 UI | `/ui/libraries/{id}/records/` 枚举、grants |
| MCP 签发 | `ma3_create_key` / `ma3_list_keys` |
| Billing 完整 enforcement | Stripe、quota 429、升级 UI |
| Entitlement resolver | 替换 v1 启发式 |
| URL 美化 | `/ui/records/`、`/ui/votes/` canonical |
| refute/verify 排序 bump | 持久化 target 关系后接入 GTN |

## v2+ 方向（未立项）

- 企业 SAML / SSO 扩展
- 跨 org 联邦搜索
- Hook 默认上送（仍违反当前 ADR-006，需重新决策）
- 完整 review queue UI
