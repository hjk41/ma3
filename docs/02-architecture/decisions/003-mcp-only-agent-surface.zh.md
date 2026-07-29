# ADR-003 — Agent 仅 MCP + policy，删除 CLI 与 install.sh

## 状态

Accepted（2026-07-01），**客户端同步细节见 [ADR-009](009-client-sync-scheme-b.md)**

## 背景

North Star：「MCP + 一条 policy」。旧 repo 有 install.sh、ma3_client.py CLI、Codex skill 目录、多份 AGENTS.md，违反 P2。

## 决策

**Agent 接入核心保留：**

1. Remote MCP `POST /mcp`
2. `GET /client/manifest.json`
3. `GET /client/templates/ma3-agent-policy.mdc`
4. `GET /client/agent-onboarding.md`

**ADR-009 扩展（仍非 ma3 CLI）：**

5. `GET /client/templates/ma3-client.env.example` — agent 自填本地路径
6. `GET /client/scripts/sync_ma3_client.{sh,py}` + `GET /client/lib/ma3_sync_core.py` — manifest 驱动 sync / tooling 自更新
7. `GET /client/mcp-tools.json` — MCP tools 快照

**v1 删除 / 不迁移：**

- `client/install.sh`
- `client/skills/ma3/scripts/ma3_client.py` 及所有 CLI 子命令
- 仓库内供 agent 复制的平行 `AGENTS.md`（运维内容迁入 deploy docs）

**保留（非 agent 面）：**

- 维护者 REST（key 管理、health）
- Observatory UI
- `ma3_doctor` / `ma3_whoami` via MCP

无 **ma3 写路径** offline CLI；网络失败时 agent 跳过 ma3 并简短说明（policy 已有）。

客户端刷新走 **sync 脚本 + manifest**（ADR-009），或最小 bootstrap 纯 curl；二者均为只读 HTTP 拉取。

## 后果

### 正面

- 单一 MCP 写契约；server block + manifest 升级路径清晰
- 减少文档与代码 drift
- 多 runtime 由 agent 填 env，repo 不维护 N 套预设

### 负面

- 无法在无 HTTP 环境用 CLI 诊断（可用 curl 调 MCP 或 doctor HTTP 替代）
- 现有用户若依赖 install.sh 需改 onboarding（env 模板 + sync 或 curl policy）
- MCP schema 变更仍需 IDE 内 reload

### 关联

- Q4, Q7, P2
- [ADR-009](009-client-sync-scheme-b.md) client sync Scheme B
- `05-doc-code-mapping.md` client 节
