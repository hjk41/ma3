# ADR-009 — Client sync（Scheme B）：agent 自填 env + manifest 自更新

## 状态

Accepted（2026-07-01）

## 背景

ADR-003 定稿「MCP + policy，无 CLI」，但未规定：

1. **多 agent runtime**（Cursor、Codex、Claude Code、Droid…）各自 policy/MCP 路径不同，若在 repo 维护 per-runtime 预设无法扩展。
2. **两层客户端版本**：policy/onboarding（skill bundle）与 MCP `tools/list` schema（tool schema）升级节奏不同。
3. **sync 脚本本身**会随服务端演进；不能要求用户 clone repo 或手工替换脚本。

旧 repo 的 `install.sh` / `ma3_client.py` CLI 已删除；需要轻量、HTTP 可 bootstrap 的替代物。

## 决策

### 1. 不是 CLI，是 HTTP 提供的 sync 工具链

v1 **不恢复** `ma3_client.py` 子命令或 `install.sh`。提供：

| HTTP 路径 | 用途 |
|-----------|------|
| `GET /client/manifest.json` | 版本 + 全部 bundle 文件 sha256/url |
| `GET /client/templates/ma3-client.env.example` | **agent 自填**本地路径模板 |
| `GET /client/scripts/sync_ma3_client.{sh,py}` | 同步入口（stdlib + 薄 wrapper） |
| `GET /client/lib/ma3_sync_core.py` | 同步核心（stdlib only，可单独拷贝） |
| `GET /client/templates/ma3-agent-policy.mdc` | 行为策略 bundle |
| `GET /client/agent-onboarding.md` | 操作说明 |
| `GET /client/mcp-tools.json` | MCP tools/list 快照 |

实现：`code/client/lib/ma3_sync_core.py`（真源）；`server/app/services/client_sync.py` 仅测试适配 re-export。

### 2. Agent 自填 env，repo 不维护 runtime 预设

- 模板：`ma3-client.env.example`（HTTP 提供）
- Agent onboarding 时复制为 `~/.ma3/ma3-client.env` 并编辑：
  - `MA3_BASE_URL`
  - 安装目录（默认 `~/.ma3`）
  - bundle 落盘相对路径（`MA3_POLICY_REL` 等）
  - **注释示例**：如何把 policy 复制到 Cursor/Codex/Claude/Droid（由 agent 执行，非 ma3 硬编码）

`sync_ma3_client.sh` 启动时 **source 该 env**；各 runtime 差异留在 agent 侧一次性配置。

### 3. Scheme B — 本地 state 为版本真相源

| 本地文件 | 作用 |
|----------|------|
| `~/.ma3/ma3-client.env` | 路径与 base URL（agent 维护） |
| `~/.ma3/ma3-client.json` | 已同步版本 + 文件 sha256 + 标志 |
| `~/.ma3/policy/ma3-agent-policy.mdc` | skill bundle（需复制到 runtime） |
| `~/.ma3/mcp-tools.json` | tools/list 缓存 |

Agent **每次 MCP 调用**传：

- `client_version` ← state 的 `skill_bundle_version`
- `tool_schema_version` ← state 的 `tool_schema_version`

服务端在 `structuredContent.server` 返回：

- `policy_refresh_required`
- `mcp_reload_required`
- `client_update_required`（任一层 breaking → **禁止写路径**）

### 4. 同步与 tooling 自更新

```bash
bash ~/.ma3/bin/sync_ma3_client.sh sync   # 或 check（exit 2 = 有更新）
```

`sync` 流程：

1. `GET /client/manifest.json`
2. 若 manifest 中 scripts/lib 的 sha256 与本地不符 → 下载覆盖 `~/.ma3/bin`、`~/.ma3/lib`（**tooling self-update**）
3. 下载变更的 policy / onboarding / mcp-tools 到 `MA3_CLIENT_INSTALL_DIR`
4. 写入 `ma3-client.json`；若 `mcp_reload_required` → agent 在 IDE 内 reload MCP

Manifest 另含 `sync_tooling_version`（服务端 `settings.sync_tooling_version`），便于提示「同步工具本身已变」。

若 mid-run 更新了 tooling，stderr 提示 **再跑一次 sync**（当前进程可能仍执行旧脚本）。

### 5. 与 ADR-003 的关系

- ADR-003 禁止的是 **ma3 写路径 CLI**（report/context 等）和 **install.sh**。
- ADR-009 的 sync 脚本是 **只读 HTTP 拉取 + 本地文件写入**，不替代 MCP；无 ma3 服务端写权限。
- 最小 bootstrap 仍可用纯 `curl`（env 模板 + 三个脚本）；sync 是推荐路径。

## 后果

### 正面

- 支持任意 agent runtime，无需 ma3 repo 维护 N 套路径
- 双版本（skill + tool schema）可独立升级；MCP reload 与 policy 刷新分离
- 服务端发新 sync 脚本 → manifest hash 变 → agent 下次 sync 自动更新

### 负面

- MCP `tools/list` 缓存仍依赖 **IDE reload**；sync 无法替 Cursor 刷新 MCP 连接
- 首次 onboarding 步骤多于「只 curl policy」；需 agent 理解 env + 复制 policy
- `ma3_sync_core.py` 与 server 测试共用一份源码，部署时需保证 HTTP 提供的内容与 repo 一致

### 关联

- ADR-003（MCP-only agent 面）
- `04-target-architecture-draft.md` §3、§10
- `code/client/agent-onboarding.md`（操作真源）
- `code/eval/scenarios/agent-client-sync/`（Docker 多 agent 安装/升级测试）
- `tests/integration/test_client_sync.py`
