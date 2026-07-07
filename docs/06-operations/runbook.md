# 运维 Runbook

> **状态**：待补充

## 常见操作（占位）

| 场景 | 步骤 | 文档 |
|------|------|------|
| 首次部署 Authing | 控制台 + env + 验证 curl | [deployment-authing.md](deployment-authing.md) |
| 添加产品管理员 | 更新 `MA3_AUTH_ADMIN_USERS` + 重启 | [authentication.md](../03-backend/authentication.md) |
| 用户无法登录 | 检查 callback URL、issuer、cookie | deployment-authing |
| MCP 401 | key 是否删除/过期；`ma3_doctor` | [getting-started.md](../05-agent/getting-started.md) |
| 搜索无 vector | `MA3_DISABLE_EMBEDDINGS`、HF 缓存 | [system-overview.md](../02-architecture/system-overview.md) |
| 启动失败 admin 白名单 | 设置 `MA3_AUTH_ADMIN_USERS` | portal-permissions |

## 待补充

- [ ] 发版步骤（rsync、migrate、restart、smoke test）
- [ ] 回滚 procedure
- [ ] 数据库 migration 执行与验证
- [ ] 日志位置与常用 grep
- [ ] 值班/on-call 联系人
