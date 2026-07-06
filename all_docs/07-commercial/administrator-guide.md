# 管理员指南

> **状态**：待补充 — 面向产品管理员与平台运维

## 产品管理员（Observatory）

| 能力 | 路径 | 说明 |
|------|------|------|
| 全局 Stats + 枚举 | `/ui/observatory/` | 需 `MA3_AUTH_ADMIN_USERS` |
| Record 详情（全局） | `/ui/records/{id}` | 与普通用户相同路由 |
| 非 admin 访问 | — | **403** |

## 平台运维

| 任务 | 参考 |
|------|------|
| 配置 Authing | [deployment-authing.md](../06-operations/deployment-authing.md) |
| 设置 admin 白名单 | `MA3_AUTH_ADMIN_USERS` |
| 改用户 plan | `PATCH /admin/billing_accounts/{id}`（Phase B4） |
| seed 兜底 key | `server/scripts/seed_personal_library_key.py` |

## 库 / org 管理（v1.1）

- org 成员、visibility、grants — UI 未交付；当前依赖 DB / 脚本

## 待补充

- [ ] Observatory 功能 walkthrough（截图级步骤）
- [ ] 手工升级 Free → Pro → Team 操作步骤
- [ ] 内容 moderation 流程（invalid、隐私删除）
- [ ] 用户 support 升级路径
