# 页面规格索引

> 门户 IA 与全局壳见 [information-architecture.md](information-architecture.md)  
> 权限与角色矩阵见 [portal-permissions.md](portal-permissions.md)  
> 视觉 token 见 [visual-design-system.md](visual-design-system.md)

各模块页面规格分文档维护：

| 模块 | 文档 | 路由 |
|------|------|------|
| 用户门户（概览/记录/投票/库） | [information-architecture.md](information-architecture.md) §3 | `/ui/me/*`、`/ui/libraries/*`、`/ui/records/*` |
| API Keys | [api-keys-ui-and-api.md](api-keys-ui-and-api.md) | `/ui/keys/*` |
| 显示名注册 | [display-name-registration.md](display-name-registration.md) | `/ui/me/setup/` |
| Observatory（admin） | [portal-permissions.md](portal-permissions.md) §3 | `/ui/observatory/*` |

## 列表页通用契约

记录页（`/ui/me/writes/`）与投票页（`/ui/me/votes/`）共用 **标准列表壳**：

```text
.page-header (h1 + subtitle)
  → .filter-pills
  → .card > table.data (sortable columns)
  → [batch bar]（仅记录页 buffered）
  → .list-footer (total + per_page + pagination)
```

**Query 参数白名单**：`page`、`per_page`（10/25/50/100）、`sort`、`dir`、模块特有 filter（`status` / `vote`）。

## 全局交互约定

- 破坏性操作：行内 `<form>` + `confirm`；SSR，无 modal 框架
- 越权 URL：404（不泄露存在性）；Observatory 非 admin：403
- 空状态：`.empty` + CTA 链到 onboarding / 建 key
- Same-origin：所有 mutating POST 校验 `Origin` / `Referer`

详细文案规范见 [ui-copy-and-interactions.md](ui-copy-and-interactions.md)（待补充）。
