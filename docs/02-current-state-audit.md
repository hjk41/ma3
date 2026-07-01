# 02 — 现有 `ma3` 状态审计

审计日期：2026-07-01。目的：为 v1 redesign 提供事实基线，非贬低现有工作。

## 1. 仓库结构（实际）

```text
ma3/
├── server/          FastAPI：v1 routes + v2 + v3 auth + v4 + MCP + UI
├── client/          install.sh、skill、onboarding、templates
├── deploy/          LAN deploy、LTP（与 v4 文档「删除 LTP」矛盾）
├── eval/            agent 场景评测 harness
├── docs/            v2 / v3 / v3.1 / v4 设计文档（多版本并存）
└── AGENTS.md        运维 + MCP 契约（偏 LTP 生产）
```

**观察**：一个 monorepo 同时承载 **内部 LAN 实验**、**LTP 生产 playbook**、**v4 SaaS 设计**、**eval 框架**。

## 2. API / 版本层叠

| 层 | 路由示例 | 状态 |
|----|----------|------|
| v1 legacy | `/search`, `/records`, `/agent/ingest` | 仍在 main.py |
| v2 | `/v2/agent/context`, `/v2/cases`, `/v2/doctor` | MCP 底层依赖 |
| v3 auth | `/v3/auth/whoami`, legacy token 迁移 | 部分生产仍在用 |
| v4 | `/v4/*` org/library/key | schema 在 db.py；LAN 用 `MA3_API_VERSION=v4` + `MA3_DEV_AUTH=1` |
| MCP | `/mcp` JSON-RPC | **实际 agent 主路径** |

**问题**：v4 设计文档写「不兼容 v2/v3」，代码仍 **全部挂载**；默认 `MA3_API_VERSION=v4` 但 MCP 仍走 v2 workflow。

## 3. Agent 接入面（过多）

| 入口 | 用途 | 问题 |
|------|------|------|
| Remote MCP | 主路径 | ✓ |
| `ma3_client.py` CLI | healthz/warmup/self-update | CLIENT_VERSION=`0.4.0` ≠ server `4.0.0` |
| `install.sh` / `install.ps1` | 克隆 + skill 链接 | 与「仅 MCP onboarding」文档部分重复 |
| `client/docs/agent-onboarding.md` | 多 agent 配置 | 与 templates、eval templates 三份策略 |
| `~/.cursor/rules/ma3-agent-policy.mdc` | Cursor 行为 | 需 curl 安装，易 drift |
| `AGENTS.md` + `server/app/docs/agents.md` | 两份 agent 说明 | Base URL 替换逻辑分散 |
| `/client/manifest.json` | self-update | 刚扩展，尚未与 skill 版本统一 |

**问题**：**7+ 条 bootstrap 路径**，违反 P2「一条 agent 契约」。

## 4. 数据与搜索

| 项 | 实现 | 问题 |
|----|------|------|
| DB | PostgreSQL prod / SQLite test | ✓ |
| Case 模型 | v2 repositories | ✓ |
| FTS + embedding | PG index + sentence-transformers | HF 缓存路径曾错；需 offline |
| Search explain | v2 | ✓ |
| N+1 | v2 优化过 | 需 perf 回归 |

## 5. 部署形态（三套叙事）

| 叙事 | 文档 | 现实 |
|------|------|------|
| LTP + CephFS + dns-manager | AGENTS.md, v2 §11 | 生产 10.100.193.54 仍可能用 |
| v4 公有云 SaaS | docs/v4/* | **未作为唯一部署实现** |
| LAN 202 | deploy/DEPLOY_RUNBOOK.md | 当前实验主战场 |

**问题**：部署文档与 v4「删除 LTP/CephFS」冲突；新 agent 读 doc 会困惑。

## 6. 质量 / 写回

- MCP `ma3_report` → v2 ingest → case assignment：工作正常
- Feature `immediate_visibility`：record 立即可见
- `ma3_list_drafts` / `ma3_review_record`：MCP 有，但 agent 策略很少提
- 无 hook 自动 draft pipeline（agentmemory lessons 建议有）

## 7. 测试与 eval

- server: ~198 pytest
- eval/: Docker 场景 + agent 跑分 — **产品外圈**，但占 repo 体量不小

## 8. 近期补丁反映的系统性问题

| 事件 | 暴露的问题 |
|------|------------|
| HF 缓存目录不一致 | prewarm vs runtime env 未单一真源 |
| rsync `--delete` 删 data/ | deploy 脚本未 exclude 运行时数据 |
| Codex MCP 连不上 202 | 服务端 hung + agent 策略未强制 ma3_context retry |
| MCP server 块 | client/server 版本分裂已久 |
| 策略三份（cursor/user/template/eval） | 无单一 policy artifact |

## 9. 审计结论（给 redesign）

**保留的核心资产**：

- MCP Pydantic 单一真源 + `ma3_validate`
- Case/record/relation 模型 + explain
- doctor/healthz 身份面
- client onboarding 文档思路

**v1 应裁减或推迟**：

- v1 legacy REST 作为 agent 面
- v3/v4 与 v2 并行挂载（除非明确多租户 v1 目标）
- 多套 install/bootstrap
- LTP 与 SaaS 混在同一「默认架构」叙述

**v1 应重新定稿**：

- 唯一部署 reference（LAN？SaaS？两者 module 化）
- client_version 语义与单一 manifest
- draft vs active 默认行为
