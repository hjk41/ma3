# 法律文档索引（Legal）

> **English note**: This folder contains draft legal documents for the ma3 project
> (Terms of Service, Privacy Policy, Data Retention & Deletion). They are written
> in Chinese as the primary language. **All documents here are drafts and have NOT
> been reviewed by a lawyer.** They describe the project's actual current behavior
> honestly (best-effort support, no SLA yet) and must be legally reviewed before
> being presented as binding contracts.

> **状态：草案（draft）。未经律师审阅，不构成法律意见；正式商用前须法务审核。**

## 文档列表

| 文档 | 内容 |
|------|------|
| [terms-of-service.md](terms-of-service.md) | 服务条款：服务范围、账户与 API Key、内容与知识记录的权利义务、免责声明 |
| [privacy-policy.md](privacy-policy.md) | 隐私政策：收集哪些数据、如何使用、第三方（如 OIDC/Authing）、自托管实例的责任划分 |
| [data-retention-and-deletion.md](data-retention-and-deletion.md) | 数据保留与删除：记录删除（ADR-013）、审计日志、备份、下架（takedown）流程 |

## 适用范围与责任划分（重要）

- **ma3.io（官方 SaaS）**：由 ma3 维护者运营，本目录文档直接适用。
- **自托管（self-host）实例**：运营者（operator）是其实例数据的**数据控制者**，
  须自行对其用户承担合规义务；本目录文档仅可作为模板参考，ma3 项目与维护者
  不对第三方自托管实例的数据处理行为负责。

## 现状的诚实声明

- 当前所有档位（含付费）支持均为 **best-effort，无正式 SLA**（正式 SLA 计划 v1.1+）。
- 记录所有者可自助删除自己的记录（见 [ADR-013](../../02-architecture/decisions/013-write-confirmation-audit-delete.md)）。
- 维护者下架（takedown）流程**尚未自动化**：通过维护者 GitHub 个人资料页所列邮箱联系
  （参见仓库根 [SECURITY.md](../../../SECURITY.md)）。
- 本项目**不声称**已通过 GDPR 或任何合规认证。
