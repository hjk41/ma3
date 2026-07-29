# 角色与用户画像（Personas）

> **状态**：草案 — 需产品补充场景故事与优先级

## 角色一览

| 角色 | 身份判定 | 核心目标 | 主要界面 |
|------|----------|----------|----------|
| **个人开发者（贡献者）** | Authing 用户 + personal library + API key | 自助接入 Agent；写回经验；管理自己的 key 与贡献 | 用户门户 `/ui/me/*`、API Keys |
| **Agent（贡献者）** | 持 `X-API-Key` 的 MCP 客户端 | 任务前 `ma3_context`；任务后 `ma3_report`；可解释失败并重试 | MCP + policy |
| **Agent（维护者）** | key 含 maintainer grant | 标记 invalid、审 draft、整理 case | MCP `ma3_review_record` 等 |
| **人 — 知识库维护者** | 库 admin / org admin / 产品 admin | 监督 Agent 维护者；清除隐私/价值观不合规内容 | 门户（有限）+ Observatory |
| **组织管理员** | `org_members.role=admin` | 成员、org 库、visibility（v1.1 UI） | `/ui/orgs/*`（v1.1） |
| **产品管理员** | `MA3_AUTH_ADMIN_USERS` | 全局健康度、枚举、运营 | Observatory |
| **匿名访客** | 无 session | 浏览 Community Library **Stats only** | `/ui/libraries/lib_default/` |

## 角色叠加

- 产品管理员 **同时是** 普通用户；Observatory 是额外能力，不替代门户。
- `is_admin` **不自动授予** org/库业务管理权（全局观测与业务管理分离）。

## 待补充

- [ ] 各角色典型一天 / 典型任务（用户故事）
- [ ] 免费 vs 付费 persona 差异（Pro/Team）
- [ ] B2B 团队 onboarding persona（v1.1）
