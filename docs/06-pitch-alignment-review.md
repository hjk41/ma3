# 06 — 设计 ↔ Pitch 对齐检查

> **产品语义真源**：[`PITCH.md`](PITCH.md)（用户/投资人向）  
> **实现真源**：本文档族 + [`04-target-architecture-draft.md`](04-target-architecture-draft.md) + [`docs/adr/`](adr/)  
> 检查日期：2026-07-01（按用户修订后的 Pitch 复核）

---

## 结论摘要

| 维度 | 状态 |
|------|------|
| 定位（跨 Agent、站在肩膀上） | ✅ 已对齐 |
| 角色模型（贡献者 / 维护者 Agent / 人维护者 / 管理者） | ✅ 已对齐（本次补全 01、04） |
| 维护分层（Agent 提效 + 人可问责） | ✅ 已对齐 |
| 写回默认 active + 治理缓解 | ✅ 已对齐（本次更新 ADR-002、01 质量模型） |
| Agent 契约 MCP-only | ✅ 已对齐（本次修正 00 P2） |
| 商业模式与公共库 | ✅ 已对齐 |
| 成功标准「立即复用」 | ✅ 已对齐（本次修正 00） |

**可开工**：设计文档与 Pitch 语义一致；剩余项为实施期细节（见 §待跟踪）。

---

## Pitch 要点 → 设计落点

| Pitch 要点 | 设计落点 |
|------------|----------|
| 跨 Agent verified knowledge 网络 | 00 一句话；01 问题陈述；P0 |
| 贡献 / 复用 / 治理 三动作 | 01 agent 循环；04 §6 写入路径 |
| 维护者 Agent 日常维护 | ADR-008 §2；04 §9；MCP maintainer 工具 |
| 人与团队维护者最终裁量、纠偏、隐私/价值观 | ADR-008 §3；04 §9；Observatory 写动作 |
| 组织管理者 ≠ 知识库维护者 | ADR-008 术语表；Pitch 商业模式节 |
| 公共库 / 平台生态 | ADR-001 SaaS；04 数据模型 org→library |
| 不是 session 记忆 / 不是封闭 wiki | 00 明确不做；01 非目标 |
| Human backstop | P0c；ADR-008 |
| Hook 本地、不上送（Pitch 未写，设计保留） | ADR-006；04 §6.1 |

---

## 本次修正的不一致

1. **00-vision P2** 仍写「CLI fallback」→ 改为 MCP-only（ADR-003）  
2. **00 成功标准** 仍提 CLI、未写人维护者纠偏 → 与 Pitch 对齐  
3. **01 质量模型** 仍写「待讨论 Q5」→ 改为 active 默认 + 维护分层  
4. **01 角色表** 缺组织管理者、平台生态 → 补全  
5. **04 数据模型** ACL 缺 `library_maintainer` → 补全  
6. **04 架构图** 仅 Human → 补 Agent 维护者分层  
7. **ADR-002 缓解** 仅写「人工 invalid」→ 补维护者 Agent + 人纠偏  
8. **ADR-005** 「只读」与 ADR-007/008 人维护者写动作 → 注明例外  

---

## 待跟踪（不阻塞设计定稿）

| 项 | 说明 |
|----|------|
| `library_maintainer` vs `library_admin` 细粒度 | v1 可先 admin=人、maintainer=Agent，实现时再定 |
| 撤销 Agent 维护者动作的 API | v1 最小：op log 可见 + 人 mark active/invalid |
| Case 总结 / 标注 MCP | Pitch 隐含 v1.1+，ADR-008 已标 |
| `docs/deploy/profile-*.md` | 未写，实施前补 |
| `code/server` | ✅ v1 骨架可跑（MCP + SQLite + client + Observatory stub） |
| 02-audit / 05-mapping | 含旧实现映射，**故意保留**供迁移参考，非产品语义 |

---

## 文档阅读顺序（对内）

1. **PITCH.md** — 产品是什么  
2. **00-vision.md** — 原则与成功标准  
3. **01-problem-statement.md** — 角色与对象  
4. **04-target-architecture-draft.md** — 实现架构  
5. **adr/** — 逐项决策依据  
