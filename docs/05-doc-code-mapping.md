# 05 — 旧 repo → ma3_v1 映射

便于迁移时知道「保留 / 重写 / 丢弃」。

## Server

| 旧路径 | v1 处置 | 说明 |
|--------|---------|------|
| `server/app/services/mcp_tool_service.py` | **保留 refactor** | 核心 |
| `server/app/models/mcp_payloads.py` | **保留** | 单一真源 |
| `server/app/services/mcp_server_info.py` | **保留** | server block |
| `server/app/services/v2_*` | **合并 → domain/** | 去 v2 前缀 |
| `server/app/api/routes_v4.py` | **合并进 core** | org/library（Q1=B） |
| `server/app/api/routes_v3_auth.py` | **保留 refactor** | OIDC（SaaS profile） |
| `server/app/api/routes_records.py` 等 v1 | **丢弃 agent 面** | 维护者 API 可留 |
| `server/app/api/routes_ui.py` | **Observatory** | ADR-005 只读范围 |
| `server/app/storage/db.py` | **拆分 migration** | v4 schema 可选 |

## Client

| 路径 | v1 处置 |
|------|---------|
| `code/client/hooks/`（新） | **可选** — 示例 hook + 本地 candidate store（ADR-006） |
| `code/client/agent-onboarding.md` | **保留**，HTTP 真源（操作说明） |
| `code/client/templates/ma3-agent-policy.mdc` | **保留**，skill bundle |
| `code/client/templates/ma3-client.env.example` | **新增**，agent 自填路径模板（ADR-009） |
| `code/client/lib/ma3_sync_core.py` | **新增**，sync 核心（stdlib；server 测试 re-export） |
| `code/client/scripts/sync_ma3_client.{sh,py}` | **新增**，HTTP bootstrap sync（非 ma3 CLI） |
| `client/templates/MA3_AGENT_POLICY.md` | **合并进 mdc** 或 plain 导出 |
| `client/skills/ma3/SKILL.md` | **删除或极短 stub** → 指向 onboarding URL |
| `client/skills/ma3/scripts/ma3_client.py` | **删除**（ADR-003） |
| `client/install.sh` | **删除**（ADR-003） |
| `client/AGENTS.md` | **删除** → server HTTP 提供 |

**Agent 本地（非 repo，agent onboarding 创建）**

| 路径 | 说明 |
|------|------|
| `~/.ma3/ma3-client.env` | 自 env.example 复制并编辑 |
| `~/.ma3/ma3-client.json` | Scheme B 版本真相源 |
| `~/.ma3/bin/`、`~/.ma3/lib/` | sync 脚本与 core |
| `~/.ma3/policy/ma3-agent-policy.mdc` | bundle 落盘；再复制到各 runtime |

## Deploy

| 旧路径 | v1 处置 |
|--------|---------|
| `deploy/DEPLOY_RUNBOOK.md` | **迁入** `docs/deploy/profile-lan.md` |
| `deploy/deploy_ma3_local.sh` | **保留**（exclude data；vector 默认） |
| `deploy/ltp/*` | **legacy 文档**，非 v1 core |
| `deploy/prewarm_embedding_model.sh` | **保留** |

## Docs

| 旧路径 | v1 处置 |
|--------|---------|
| `docs/v2/overall-design.md` | **吸收** → 00-vision |
| `docs/v4/org-and-access-overall-design.md` | **搁置** 至 SaaS 模块 |
| `docs/agentmemory-*` | **参考** ADR hook/draft |
| `AGENTS.md` | **拆分**：MCP 契约进 server doc，LTP 进 profile-ltp |

## Eval

| 旧路径 | v1 处置 |
|--------|---------|
| `eval/*` | **不迁入 code/**；README 链接即可 |

## 测试

| 旧路径 | v1 处置 |
|--------|---------|
| `server/tests/unit/test_mcp_schema_alignment.py` | **必须保留** |
| `server/tests/e2e/test_remote_mcp.py` | **保留 + server block** |
| 其余 e2e | 按裁剪后路由重写 |
