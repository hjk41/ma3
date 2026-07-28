# 管理员指南

> **状态**：自托管操作以运维手册为准；本文保留 SaaS / Observatory 相关入口。

## 自托管实例管理员（推荐）

完整步骤（部署、Web/Agent 初始化、邀请成员、别名、MCP）：

→ **[self-host-admin-guide.md](../06-operations/self-host-admin-guide.md)**

技术细节：[self-hosting.md](../06-operations/self-hosting.md)、[api-overview.md](../03-backend/api-overview.md)。

## 产品管理员（Observatory）

| 能力 | 路径 | 说明 |
|------|------|------|
| 全局 Stats + 枚举 | `/ui/observatory/` | 本地 admin 或 `MA3_AUTH_ADMIN_USERS` |
| 本地账号 / 注册开关 | `/ui/observatory/local-users/` | self-host 常用 |
| 用户付费计划 | `/ui/observatory/users/` 或 `PATCH /api/admin/users/{id}/plan` | |
| Record 详情 | `/ui/records/{id}` | 与普通用户相同路由 |

## 平台运维（OIDC / 公网）

| 任务 | 参考 |
|------|------|
| 配置 OIDC / Authing | [self-hosting.md](../06-operations/self-hosting.md)、[deployment-authing.md](../06-operations/deployment-authing.md) |
| Admin 白名单 | `MA3_AUTH_ADMIN_USERS` |
| TLS 反代 | `deploy/self-host/Caddyfile.example` |

## 待补充（SaaS）

- [ ] Observatory 截图级 walkthrough
- [ ] 内容 moderation 流程（invalid、隐私删除）
- [ ] 用户 support 升级路径
