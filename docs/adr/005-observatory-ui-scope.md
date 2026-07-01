# ADR-005 — Observatory 只读 UI 进入 v1

## 状态

Accepted（2026-07-01）

## 背景

Q11：v1 是否需要 UI。**维护者**（人或 Agent）需「看库里有什么、为何命中」，与 P4 explainable search 一致。

## 决策

**v1 包含 Observatory（只读）**，路由 `/ui/observatory/*`：

| 页面 | 功能 |
|------|------|
| Overview | deploy banner、library 统计、doctor 摘要 |
| Cases | case 列表与详情 |
| Records | record 详情、relations |
| Search | 查询 + explain 面板（与 `ma3_search_explain` 同源逻辑） |

**v1 以只读浏览为主**；**人 — 维护者** 另有写动作（与 ADR-007/008 一致，对齐 Pitch §维护分层）：

| 写动作 | 说明 |
|--------|------|
| Mark record **invalid** | 纠正过时或错误条目 |
| **撤销 / 覆盖** Agent 维护者动作 | 恢复误标、误删 |
| 清除隐私 / 价值观不合规内容 | 最终裁量 |

**v1 不含：**

- 完整 review queue UI（draft 审批走 MCP 或 v1.1）
- Org/seat/billing 管理

Observatory 使用 OIDC session（SaaS）或 dev_auth 下的 **人 — 维护者** cookie/API（LAN profile）。**Agent — 维护者** 使用 library_maintainer/admin API key + MCP，不依赖 UI。

## 后果

### 正面

- 人类可验证 agent 写回与搜索行为
- 与 North Star「维护者能回答库里有什么」一致；Agent 可经 MCP 参与同等维护动作

### 负面

- 需维护 HTML/JS 或 server template 层
- 需 auth 与 library ACL 在 UI 路径复用

### 关联

- Q11=B
- 旧 `server/app/api/routes_ui.py` 部分可复用
