# 00 — 愿景

> **产品语义真源**：[`PITCH.md`](PITCH.md)  
> 本文档为对内设计原则与成功标准，与 Pitch 保持一致。

## 一句话

**ma3（马妈妈）是面向所有 Agent 的、可验证的跨 Agent 知识网络** — 让每一个 Agent 都能 **站在其它 Agent 的肩膀上**：动手前先查前人（前 Agent）经验，做完后把可复用结论写回，供 **下一个 Agent** 使用。

团队 / 公共 **library** 定义读写边界；产品本质是 **Agent 之间的知识累积与接力**，不限于单一组织。

## 核心问题

1. **Agent 重复造轮子**：同一部署、同一 bug、同一配置坑被 **不同 Agent、不同 session** 反复试错，前 Agent 的结论后 Agent 拿不到。
2. **接入与写回路径必须对 Agent 友好**：高频操作应一次远程调用完成，否则易漏写回。
3. **经验碎片化**：同一问题的多次尝试没有 case 级聚合，难以看到演化与冲突。
4. **不可解释**：维护者（人或 Agent）难以回答「为什么搜到这个」「库里到底有什么」。
5. **质量边界模糊**：运行日志、草稿、验证结论若混在同一抽象里，会污染可信知识。

## 设计原则

| # | 原则 | 含义 |
|---|------|------|
| P0 | **Agents stand on agents** | 后 Agent 复用前 Agent 的 verified 结论；跨 session、跨用户、跨产品 |
| P0b | **Community maintenance** | 维护者 Agent 日常维护；**人与团队维护者** 监督纠偏（含隐私、价值观） |
| P0c | **Human backstop** | 对维护者 Agent 可纠正；不合规内容 **由人最终清除** |
| P1 | **Verified over raw** | 存可复用的结论与证据，不是全量 tool trace |
| P2 | **Remote MCP first** | Agent 面仅 MCP + HTTP manifest/policy（无 CLI 插件链） |
| P3 | **Case over record** | Record 是原子；Case 是同一线程的演化容器 |
| P4 | **Explainable search** | 排名、过滤、冲突必须可诊断（explain / Observatory） |
| P5 | **Agent 执行，ma3 建议** | ma3 不替 Agent 改用户系统；Agent 负责验证与应用 |
| P6 | **Explicit quality states** | active / draft / invalid 等状态清晰 |
| P7 | **Schema 单一真源** | MCP inputSchema = 运行时校验 = 文档示例 |
| P8 | **Deploy identity** | healthz/doctor 暴露 version、commit、instance |

## 成功标准

- [ ] Agent 完成「查 → 做 → 写回」在 **MCP + 一条 policy** 内闭环，**无需** CLI 或手工 JSON
- [ ] 新 Agent 接入后 **立即** 能复用已有案例（Pitch：立即，非从零试错）
- [ ] **人与团队维护者** 能监督 **维护者 Agent**，纠偏并清除隐私/价值观不合规内容
- [ ] 团队能回答：库里有什么、为何推荐、哪些已过时
- [ ] 同一问题的多次 report 在 **case** 下可见演化
- [ ] doctor/whoami 能区分 auth、索引、版本、部署实例问题

## 明确不做

- 不是 Agent 全会话记忆库（≠ 全量 observe 流水线）
- 不是通用 RAG 文档库（≠ 个人笔记 / Confluence）
- 不是自动运维执行器（不替 Agent 改生产）
- 不是「每个 tool call 都入库」

## 架构 North Star（实现层）

**一个部署叙事、一套 Agent 契约、一条数据模型、一层 MCP 面。**

SaaS 多租户、Observatory、vector 搜索、维护者分层 — **v1 core**（见 04）。Billing 完整 UI、LTP legacy、eval harness — **非 v1 发布物或 v1.1+**。
