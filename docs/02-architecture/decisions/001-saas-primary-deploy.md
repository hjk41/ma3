# ADR-001 — SaaS 多租户为 v1 首要部署形态

## 状态

Accepted（2026-07-01）

## 背景

旧 repo 同时承载 LAN 实验、LTP 内网、v4 SaaS 文档，auth 与数据模型缠在一起。Q1 需选定 default 形态以定稿架构。

## 决策

- **v1 首要形态 = B：多租户 SaaS**（org + library + OIDC + library keys）
- **LAN / 自建 = dev profile**（`MA3_DEV_AUTH=1`），与 SaaS **同一 server binary**，不是 fork
- org 表 **进入 v1**（Q3=B）：library 必须挂 `org_id`；单节点部署使用 implicit `org_default`

## 后果

### 正面

- 与 v4 设计文档一致，避免二次迁移
- 202 等 LAN 环境成为真实 dev 测试床，而非「另一套 ma3」
- auth、ACL、Observatory 边界可写清

### 负面

- v1 实现量大于「纯 LAN core」
- 需在 profile-lan 文档中强调：dev_auth 不可用于公网 SaaS

### 关联

- Q1=B, Q3=B
- [deployment.md](../../06-operations/deployment.md) — SaaS profile（待补全 profile-saas 细节）
- [authorization-and-libraries.md](../../03-backend/authorization-and-libraries.md) — org 与 ACL 设计真源
