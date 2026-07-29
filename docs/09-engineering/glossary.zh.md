# 术语表（Glossary）

| 术语 | 含义 |
|------|------|
| **Agent** | 通过 MCP 调用 ma3 的 AI 客户端（Cursor、Claude Code 等） |
| **Principal** | 身份主体，如 `user:{authing_sub}` |
| **Principal ID** | 永久内部标识；设置页只读展示 |
| **Display name** | 用户可见昵称；setup 一次性设定，全局唯一（不区分大小写） |
| **Library** | 知识库边界；含 visibility、ACL、write_buffer_hours |
| **Personal library** | `kind=personal`；名 `{display_name} 的个人库` |
| **Community Library** | `lib_default`；public |
| **Case** | 同一问题线程的容器 |
| **Record** | 一条可验证经验；status: active/buffered/draft/invalid/trashed |
| **Entitlement** | Layer 1：principal **被允许**接触哪些 library |
| **Key grant** | Layer 2：某 API key 对 library 的 reader/writer 能力 |
| **Stats** | 库聚合数字（case/record 计数）；普通用户可见 |
| **Enumerate** | record/case **列表** browse；仅库 admin / 产品 admin |
| **Mutate** | 改状态、删、授权、导出 |
| **Write buffer** | 写后发布前窗口；status=buffered；仅作者可见 |
| **Draft** | maintainer 审核队列；与 buffer 互斥 |
| **confirmation** | 写前审计元数据；**非门禁**；缺省 agent_judged |
| **Observatory** | 产品管理员全局只读 UI |
| **GTN** | Gate-Then-Nudge 搜索排序方案 |
| **Read unit** | 计费读用量；`ma3_context`/`ma3_case` 成功响应计量 |
| **MCP** | Model Context Protocol；ma3 Agent 唯一数据面 |

## 已废止用语（文档中勿再使用）

| 废止 | 替代 |
|------|------|
| 撤销 / revoked（用户 UI） | **删除** |
| Libraries（顶栏） | **库** |
| 我的贡献 / 我的投票（subnav） | 顶栏 **记录 / 投票** |
| 概览页 Principal ID + 复制 | settings 只读 |
| ma3_search_explain | 内部 / Observatory only |
