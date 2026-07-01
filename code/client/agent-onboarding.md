# ma3 多 Agent 接入指南

本文是 **唯一操作说明**。不需要 clone ma3 仓库，**不需要** 运行安装脚本或 CLI。
把本文 URL 交给各 agent，由 agent **自行**完成 MCP 连接和行为策略配置。

**策略模板（必读）**：`GET /client/templates/ma3-agent-policy.mdc`  
**设计文档**：`docs/adr/009-client-sync-scheme-b.md`、`docs/04-target-architecture-draft.md` §3  
**示例 ma3 地址**：`http://192.168.31.202:8000`（按你们环境替换）

> **ma3 v1（ADR-003）**：仅 **MCP + policy**。无 `install.sh`、无 `ma3_client.py`、无 CLI 插件。
> 客户端升级 = 读 MCP `server` 块 → curl 拉取 `/client/*` → 覆盖本地规则 → 重启 agent。

> **Scheme B**：本地真相源是 `~/.ma3/ma3-client.json`。路径由 **agent 自行填写**
> `~/.ma3/ma3-client.env`（模板：`GET /client/templates/ma3-client.env.example`），
> 同步命令：`bash ~/.ma3/bin/sync_ma3_client.sh sync`

---

## Agent 自检清单（给正在读本文的 agent）

若用户要求接入 ma3，请按顺序完成 **你所在运行时** 对应的小节，然后验证 MCP 工具可见。

1. 向用户确认或从上下文取得：
   - `MA3_BASE_URL`（如 `http://192.168.31.202:8000`）
   - `MA3_API_KEY`（writer 权限；LAN dev 实例常用 `ma3dev`，生产由管理员发放）
2. **一次性 bootstrap**（agent 填 env，ma3 不维护各 runtime 预设）：
   ```bash
   mkdir -p ~/.ma3/bin ~/.ma3/lib
   MA3_BASE_URL=http://192.168.31.202:8000
   curl -fsSL "$MA3_BASE_URL/client/templates/ma3-client.env.example" -o ~/.ma3/ma3-client.env
   # 编辑 ~/.ma3/ma3-client.env：MA3_BASE_URL、策略安装路径注释等
   curl -fsSL "$MA3_BASE_URL/client/scripts/sync_ma3_client.py" -o ~/.ma3/bin/sync_ma3_client.py
   curl -fsSL "$MA3_BASE_URL/client/lib/ma3_sync_core.py" -o ~/.ma3/lib/ma3_sync_core.py
   curl -fsSL "$MA3_BASE_URL/client/scripts/sync_ma3_client.sh" -o ~/.ma3/bin/sync_ma3_client.sh
   chmod +x ~/.ma3/bin/sync_ma3_client.sh
   bash ~/.ma3/bin/sync_ma3_client.sh sync
   ```
   之后每次 MCP 调用带上 `~/.ma3/ma3-client.json` 里的：
   - `client_version` ← `skill_bundle_version`
   - `tool_schema_version` ← `tool_schema_version`
3. 配置 **MCP**（见下方「各 Agent 配置」中你的那一节）
4. 配置 **行为策略**（sync 写入 `~/.ma3/policy/ma3-agent-policy.mdc`，再按 env 注释复制到你的 runtime）
5. 若 `mcp_reload_required` → reload MCP；否则重启 Cursor
6. 验证：`tools/list` 含 `ma3_context`、`ma3_report`、`ma3_validate`

**两层都必须做**：只有 MCP → 不一定会主动调用；只有策略 → 没有工具可调。

### 接入后的强制行为（策略 v2）

| 阶段 | 要求 |
|------|------|
| 每次 MCP 调用 | 带 **`client_version`** + **`tool_schema_version`**（读 `~/.ma3/ma3-client.json`） |
| 每次 MCP 响应 | 读 **`policy_refresh_required` / `mcp_reload_required` / `client_update_required`** |
| 任一 upgrade flag | 跑 **`sync_ma3_client.sh sync`**；MCP 变更则 reload MCP |
| 任务开始 | 非 trivial 工作 **第一个动作之一** 调 `ma3_context` |
| `ma3_context` 失败 | **重试 1 次**；仍失败则 **用一句话告知用户** ma3 不可用 |
| 任务结束 | 可复用结果 → **`ma3_validate` + `ma3_report`**（且 `client_update_required` 已为 false） |
| 收尾前 | 自检 checklist（见策略模板 §4） |

---

## MCP 响应里的 `server` 块（客户端升级 — 策略驱动）

**每个** MCP `tools/call` 的 `structuredContent` 都带顶层 `server` 字段，例如：

```json
{
  "cases": [],
  "server": {
    "service_version": "1.0.0",
    "skill_bundle_version": "1.0.0",
    "min_client_version": "1.0.0",
    "recommended_client_version": "1.0.0",
    "client_version_reported": true,
    "client_version": "0.0.1",
    "client_update_required": true,
    "client_update_recommended": true,
    "client_update_urls": [
      "/client/manifest.json",
      "/client/agent-onboarding.md",
      "/client/templates/ma3-agent-policy.mdc"
    ]
  }
}
```

**Agent 必须怎么做（方案 1 — 策略强制执行）：**

1. **每次** MCP 调用都带 `client_version`（未同步过可用 `"0.0.0"`，服务端会标为 stale）。
2. 读 `structuredContent.server`：
   - `client_update_required: true` → **停止写路径**；按 `client_update_urls` curl 覆盖本地策略；告知用户重启；用新 `skill_bundle_version` 重试直到 required 为 false
   - `client_update_recommended: true` → 写回前刷新 policy，或一句话提醒用户
3. **升级方式（推荐 sync；脚本会自更新）**：
   ```bash
   bash ~/.ma3/bin/sync_ma3_client.sh sync
   # 若 stderr 提示 tooling updated，再跑一次 sync
   # 然后按 ~/.ma3/ma3-client.env 里的 MA3_POLICY_* 注释复制策略到 runtime
   ```
4. sync 会更新 `~/.ma3/ma3-client.json`；MCP schema 变更时 reload MCP。

MCP `initialize` 的 `serverInfo` 也含 `min_client_version` / `recommended_client_version`，可在会话开始时快速比对。

---

## 目标行为

| 时机 | 动作 |
|------|------|
| 非简单任务开始前 | **`ma3_context`** + **`client_version`** |
| MCP 响应 | 检查 **`structuredContent.server`** 升级标志 |
| `client_update_required` | 刷新 policy → 重启 → 再写 |
| 根因/部署/可复用修复 | **`ma3_validate`** → **`ma3_report`**（required 已为 false） |
| 收尾前 | 自检 checklist（策略 §4） |

始终使用 `redaction_mode: auto`，不要写入 secrets、私钥、订阅 URL、大段原始日志。

策略细节以 `/client/templates/ma3-agent-policy.mdc` 为准。

---

## 各 Agent 配置

### Cursor

**MCP** — 创建或编辑 `~/.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "ma3": {
      "url": "http://192.168.31.202:8000/mcp",
      "headers": {
        "X-API-Key": "ma3dev"
      }
    }
  }
}
```

可选：用 `${env:MA3_BASE_URL}`、`${env:MA3_API_KEY}` 代替字面量。

**行为策略** — 推荐安装 Cursor 规则（always apply）：

```bash
mkdir -p ~/.cursor/rules
curl -fsSL http://192.168.31.202:8000/client/templates/ma3-agent-policy.mdc \
  -o ~/.cursor/rules/ma3-agent-policy.mdc
```

**重启** Cursor → **Settings → Tools & MCP** 确认 `ma3` 已连接。

---

### Claude Code

```bash
claude mcp remove ma3 2>/dev/null || true
claude mcp add --scope user --transport http ma3 \
  "http://192.168.31.202:8000/mcp" \
  --header "X-API-Key: ma3dev"
```

行为策略：把 `/client/templates/ma3-agent-policy.mdc` 正文写入 `~/.claude/CLAUDE.md`。

---

### Factory Droid

`~/.factory/mcp.json`：

```json
{
  "mcpServers": {
    "ma3": {
      "type": "http",
      "url": "http://192.168.31.202:8000/mcp",
      "headers": { "X-API-Key": "ma3dev" },
      "disabled": false
    }
  }
}
```

行为策略：写入 `~/.factory/AGENTS.md`。

---

### OpenAI Codex

`~/.codex/config.toml`：

```toml
[mcp_servers.ma3]
url = "http://192.168.31.202:8000/mcp"
enabled = true

[mcp_servers.ma3.http_headers]
X-API-Key = "ma3dev"
```

行为策略：写入 `~/.codex/model_instructions.md`。

---

### Hermes Agent

```yaml
mcp_servers:
  ma3:
    url: "http://192.168.31.202:8000/mcp"
    headers:
      X-API-Key: "ma3dev"
```

已打开的 session 执行 **`/reload-mcp`**，或重启 Hermes。

---

## API Key

- **`ma3_context`**：匿名或 reader key 即可
- **`ma3_report`**：需要 writer key（LAN dev：`ma3dev`）
- 生产环境向管理员索取

---

## 验证

```bash
curl -sf http://192.168.31.202:8000/healthz
curl -sf http://192.168.31.202:8000/client/manifest.json | jq .skill_bundle_version
curl -sf -H "X-API-Key: ma3dev" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  http://192.168.31.202:8000/mcp | jq '.result.tools[].name'
```

---

## 故障排查

| 现象 | 处理 |
|------|------|
| 有 MCP 但不主动调用 | 策略未写入 `~/.cursor/rules/ma3-agent-policy.mdc` 或等价全局 instructions |
| Agent 从不写回 ma3 | 检查策略 mandatory report；writer key；是否被 `client_update_required` 阻塞 |
| `client_update_required` 一直 true | curl 刷新 policy；把 `client_version` 改为 manifest 的 `skill_bundle_version` |
| `ma3_context` 超时 | `curl $MA3_BASE_URL/healthz` |
| `ma3_report` 401/403 | 检查 API key |

---

## 给用户的简短说明

> 打开 `http://<ma3-host>:8000/client/agent-onboarding.md`，让 agent 按文档配置 MCP 和策略；
> 提供 ma3 地址和 API key 即可。无需 clone 仓库，无需安装 CLI。
