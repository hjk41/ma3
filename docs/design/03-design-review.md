# 03 — 设计 Review（待讨论）

> 本文从 **00-vision** 的 North Star 出发，对旧 repo 与 v4 草案做 critical review。
> 每一项 **Q** 需要产品负责人拍板后，才能定稿 `04-target-architecture-draft.md`。

---

## A. 产品边界

### Q1 — v1 的首要部署形态是什么？

| 选项 | 描述 | 影响 |
|------|------|------|
| **A** | **单租户 LAN/自建**（如 192.168.31.202） | 简化 auth；org/seat 整模块删除 |
| **B** | **多租户 SaaS**（v4 文档） | 必须 org/OIDC/席位；LAN 变 dev 模式 |
| **C** | **核心 + 插件**：core 单租户，tenant 包可选 | 代码分 `ma3-core` / `ma3-tenant` |

**Review 意见**：当前代码与文档 **C 口头上像、实现上不是** — v4 schema 与 dev_auth 缠在一起。v1 必须选一个 default，否则 auth、library、部署 doc 无法写清。

**倾向**：**A 为 v1 default，B 为 v1.1 模块**（除非你已决定马上对外 SaaS）。

---

### Q2 — ma3 与 agentmemory 的边界

| 选项 | 描述 |
|------|------|
| **A** | 严格 verified knowledge；hook 只产生 **draft candidate**，不自动 active |
| **B** | 半自动：高置信模板可 auto-active |
| **C** | 集成 agentmemory 作 session 层，ma3 只存 promote 后 record |

**Review 意见**：`docs/agentmemory-mechanism-lessons.md` 已明确不应把 tool trace 入库。

**拍板（ADR-006）**：hook 候选 **默认存本地**（draft candidate）；仅 `ma3_report` / promote 进 ma3。v1 可不实现 hook，边界已定。

---

### Q3 — Organization 是否进入 v1 数据模型？

v4 设计：library 必须挂 org。

| 选项 | 描述 |
|------|------|
| **A** | v1 无 org：单 implicit org 或 library-only |
| **B** | v1 有 org 表但单租户（为 SaaS 预埋） |
| **C** | v1 完整 v4 org + seat（工作量大） |

**Review 意见**：LAN 202 部署 **完全没用 org**；v4 migration 与 v2 case 搜索路径叠加复杂度高。

**倾向**：**A 或 B**；若选 B，所有 API 默认 `org_default`，UI 隐藏 org 概念。

---

## B. Agent 契约

### Q4 — 唯一 agent 接入路径应是什么？

**Review 意见**：现状 7+ 路径（见 02-audit §3）。North Star 要求 **MCP + 一条 policy**。

| v1 提案 | 保留 | 降级/删除 |
|---------|------|-----------|
| Remote MCP | ✓ 必须 | |
| `ma3_validate` | ✓ | |
| `client_version` + `server` block | ✓ | |
| `install.sh` 全量 clone | | 改为 **可选** `ma3_client.py` 仅 self-update |
| Codex skill 目录链接 | | 改为 policy.mdc + MCP 即可？ |
| 双份 AGENTS.md | | 合并为 **一个** `GET /v1/agent/guide` |

**待讨论**：是否 **完全删除** CLI plugin 路径，还是保留作 offline fallback（agentmemory shim 思路）？

---

### Q5 — 写回默认：draft 还是 immediate active？

旧 repo feature：`immediate_visibility`。

| 选项 | 风险 |
|------|------|
| **draft 默认** | agent 以为写入了但 search 不到 → 需明确响应 |
| **active 默认** | 垃圾 record 污染搜索 → 需 ranking 惩罚 + review 工具 |
| **library 级配置** | 灵活但 agent 难推理 |

**Review 意见**：verified knowledge 品牌与 **active 默认** 张力最大。MCP 已有 review tools，但 agent 策略未强制 review 文化。

**倾向**：**personal/dev library = active**；**shared/org library = draft**（或 risk_level 驱动）。

---

### Q6 — `client_version` 语义

现状：server `4.0.0`，client `0.4.0`，两套 semver。

| 选项 | 描述 |
|------|------|
| **A** | 统一为 **一套** `ma3_version`（server/client/skill 同号） |
| **B** | 分离：`protocol_version` + `skill_bundle_version` |
| **C** | 仅 manifest hash，不比 semver |

**Review 意见**：方案 B 已在 MCP 有 `protocol_version` / `tool_schema_version`，应扩展而非再发明 `0.4.0`。

**倾向**：**B** — deprecate CLIENT_VERSION `0.4.0`，manifest 报 `skill_bundle` git sha 或 semver aligned with server。

---

## C. 架构与代码

### Q7 — 是否砍掉 v1 legacy REST agent 面？

`/search`, `/agent/ingest` 仍挂载；MCP 内部调 v2。

| 选项 | 描述 |
|------|------|
| **A** | redesign **仅** MCP + 人用的 REST |
| **B** | 保留 legacy 只读 1 年 |
| **C** | 全保留 |

**倾向**：**A** for ma3_v1 code；旧 repo 可 B 过渡。

---

### Q8 — Monorepo 还是 multi-repo？

| 选项 | 描述 |
|------|------|
| **A** | 单 repo：`core/` `client/` `deploy/` `eval/` 清晰边界 |
| **B** | server repo + client repo |
| **C** | ma3_v1 新 repo，旧 repo archive |

**Review 意见**：eval harness 与 server 发布周期不同，**物理目录分离**至少要有（A 即可）。

---

### Q9 — Embedding / 搜索依赖

HF 模型部署 pain 已出现。

| 选项 | 描述 |
|------|------|
| **A** | FTS-only v1（无 vector） |
| **B** | Vector 可选，`MA3_DISABLE_EMBEDDINGS=1` 默认 LAN |
| **C** | Vector 必须，但 **bake model in image** + HF_HUB_OFFLINE |

**倾向**：**C for 完整体验，B for 最小 LAN** — v1 文档写清 two profiles。

---

## D. 运维与文档

### Q10 — 部署文档单一真源

现状：AGENTS.md（LTP）、DEPLOY.md、DEPLOY_RUNBOOK（LAN）、v4（云）。

**提案**：`ma3_v1/docs/deploy/` 下 **profiles**：

- `profile-lan.md`
- `profile-ltp.md`（legacy）
- `profile-saas.md`（future）

共享 `profile-common.md`（HF cache、ma3.env、healthz）。

---

### Q11 — UI（Knowledge Observatory）是否 v1 范围？

v2 §12 描述完整 UI；v4 也要 GitHub 风 UI。

| 选项 | 描述 |
|------|------|
| **A** | v1 无 UI，仅 doctor + 未来 minimal `/ui/overview` |
| **B** | 只读 observatory（cases + search explain） |
| **C** | 含 review queue 的完整 UI |

**倾向**：**B** 若你仍需要「人看库」；否则 **A** 最快。

---

### Q12 — eval/ 目录定位

| 选项 | 描述 |
|------|------|
| **A** | 移出 ma3_v1 core，独立 `ma3-eval` repo |
| **B** | 留在 monorepo 但非 v1 发布物 |
| **C** | v1 核心（agent 质量即产品） |

**倾向**：**B** — eval 有价值，但不应阻塞 v1 核心 schema 定稿。

---

## E. Review 汇总结论

### 严重问题（建议在写代码前解决）

1. **三重产品叙事**：LAN 实验 / LTP 内网 / v4 SaaS — 无 default
2. **Agent 接入面爆炸** — 违反 own North Star
3. **版本与 manifest 分裂** — 阻碍刚做的 server block
4. **质量模型未拍板** — draft vs active 影响 MCP 响应语义
5. **部署脚本不安全** — rsync delete 数据（已 patch exclude，需纳入 v1 deploy spec）

### 设计 strengths（v1 应继承）

1. MCP Pydantic 单一真源 + structured -32602
2. Case-centric knowledge + explain
3. `ma3_context` / `ma3_report` workflow 命名清晰
4. doctor 作为 deploy identity
5. agent-onboarding 文档化自助接入思路

### 建议的讨论顺序

1. **Q1**（部署/default 租户模型）→ 锁定 Q3、Q10
2. **Q5**（写回质量）→ 锁定 MCP 响应与 review
3. **Q4 + Q6**（agent 契约 + 版本）→ 锁定 client 包
4. **Q7、Q8、Q9**（代码裁减）→ 开始 `code/`

---

## 请你回复的模板

```text
Q1: A / B / C — 备注：…
Q2: A / B / C
Q3: …
…
Q12: …
额外约束：…
```

定稿后我会更新 `04-target-architecture-draft.md` 并开始 ADR。

---

## F. 产品负责人拍板（2026-07-01）

| 题 | 决定 | ADR |
|----|------|-----|
| **Q1** | **B** — SaaS 多租户首要；LAN = dev profile | [001](adr/001-saas-primary-deploy.md) |
| **Q2** | **A** — verified over raw；hook 候选本地 draft，不得自动 active / 默认上送 | [006](adr/006-hook-candidates-local-first.md) |
| **Q3** | **B** — org 表进 v1，`org_default` 单租户 | 001 |
| **Q4** | **MCP + policy**；删除 `install.sh`、CLI | [003](adr/003-mcp-only-agent-surface.md) |
| **Q5** | **全部 library 默认 active** | [002](adr/002-active-default-writes.md) |
| **Q6** | **B** — `skill_bundle_version` + `protocol_version`（沿用 review 倾向） | 04 §10 |
| **Q7** | **A** — agent 仅 MCP | 003 |
| **Q8** | **A** — monorepo | 04 §2 |
| **Q9** | **默认 vector**，`MA3_DISABLE_EMBEDDINGS=1` 可关 | [004](adr/004-vector-default-optional-off.md) |
| **Q10** | **profiles** — saas 首要，lan dev，ltp legacy | 04 §11 |
| **Q11** | **Observatory** 只读 | [005](adr/005-observatory-ui-scope.md) |
| **Q12** | **B** — eval 留 monorepo，非发布物 | 04 §2 |

**ADR-007（2026-07-01）**：Observatory **只读 + mark invalid**；首 deploy **202 :8001**；迁移 **并行新库，cutover 后迁**。

**ADR-008（2026-07-01）**：内容治理角色 **维护者（Maintainer）**（人/Agent）；**人与团队维护者** 对 **维护者 Agent 纠偏**，并清除隐私/价值观不合规内容；组织后台称 **管理者（Admin）**。

| 文档 | |
|------|--|
| [PITCH.md](PITCH.md) | 产品 pitch（对外/对内） |

**04-target-architecture-draft.md** 已按上表定稿。下一步：`docs/deploy/profile-*.md` → `code/` 骨架。
