# ma3 多 Agent 接入指南

本文是 **唯一操作说明**。不需要 clone ma3 仓库，**不需要** 运行安装脚本或 CLI。
把本文 URL 交给各 agent，由 agent **自行**完成 MCP 连接和行为策略配置。

若用户只说「帮我接入 ma3 / ma3.io 的 MCP」（包括**尚未注册**），先拉短路径：`GET /client/connect.md`（中文：`connect.zh.md`）。

**策略模板（必读）**：`GET /client/templates/ma3-agent-policy.mdc`  
**短接入路径**：`GET /client/connect.md`  
**设计文档**：[docs/02-architecture/decisions/009-client-sync-scheme-b.md](../../docs/02-architecture/decisions/009-client-sync-scheme-b.md)、[docs/02-architecture/system-overview.md](../../docs/02-architecture/system-overview.md) §3、[016-mcp-oauth-plus-api-keys.md](../../docs/02-architecture/decisions/016-mcp-oauth-plus-api-keys.md)  
**示例 ma3 地址**：`https://ma3.io`（仅当用户点名其它主机时才替换）

> **ma3 v1（ADR-003）**：仅 **MCP + policy**。无 `install.sh`、无 `ma3_client.py`、无 CLI 插件。
> 客户端升级 = 读 MCP `server` 块 → curl 拉取 `/client/*` → 覆盖本地规则 → 重启 agent。

> **Scheme B**：本地真相源是 `~/.ma3/ma3-client.json`。路径由 **agent 自行填写**
> `~/.ma3/ma3-client.env`（模板：`GET /client/templates/ma3-client.env.example`），
> 同步命令：`bash ~/.ma3/bin/sync_ma3_client.sh sync`

---

## Agent 自检清单（给正在读本文的 agent）

若用户要求接入 ma3，请按顺序完成 **你所在运行时** 对应的小节，然后做 **接入验证**。

### 0. 确定 Base URL + 认证路径（必须先做）

**不要** 编造 API key，也 **不要** 假设 `ma3dev` 可用（仅部分 LAN dev 实例在 `MA3_DEV_AUTH=1` 时开放）。

用户说 ma3 / ma3.io 时 **不要再问 URL**，直接用 `https://ma3.io`；仅明确内网/自托管时才询问。MCP 永远是 `{BASE}/mcp`（禁止臆造 `:8000`）。再按 **runtime** 分支：

| Runtime | 认证 | 需要用户提供什么 |
|------|------|------|
| Cursor / OpenCode / 交互式 IDE MCP | **优先 OAuth** | 浏览器登录账号；MCP 可只配 **URL**（`{BASE}/mcp`） |
| CLI / CI / 无头（Claude Code、Codex、Droid、Hermes、脚本） | **必须 `X-API-Key`** | 门户 `{BASE}/ui/keys/` 签发的 writer key（`ma3k_…`） |

除登录 / OAuth / 粘贴 key 外，其余（文档、配置、policy/skill、验证）自行完成。

**若用户还没有账号：** 请其打开 `{MA3_BASE_URL}/auth/login`（或 `/ui/home/` 注册），完成显示名 setup，再继续。最短 agent 路径见 `{MA3_BASE_URL}/client/connect.md`。

**API Key 路径**（CLI / 用户更想用 key）：

1. 浏览器打开 `{MA3_BASE_URL}/ui/keys/`，注册/登录
2. 首次登录自动获得个人库；填 label 点「创建」
3. **立即复制**明文 key 并粘贴给你（或写入 `~/.ma3/ma3-client.env` / shell profile）
4. 默认授权：个人库 writer + Community Library（`lib_default`）writer

key 丢失或泄漏：回 `/ui/keys/` 撤销并重建。

**OAuth 路径**（Cursor / 交互式）：用户能登录门户后，MCP 只配 URL，完成弹窗登录。权限跟随门户 Layer-1 库授权——交互式使用不需要 API key。

### 1. 一次性 bootstrap

```bash
mkdir -p ~/.ma3/bin ~/.ma3/lib
export MA3_BASE_URL=https://ma3.io   # ma3.io 默认；仅自托管时改
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

### 2. 配置 MCP

见下方「各 Agent 配置」中你的那一节。

- **OAuth（Cursor / 交互式）：** MCP 只写 URL；收到挑战后完成浏览器登录。
- **API Key（CLI / CI）：** Header 使用用户提供的 `MA3_API_KEY`。

### 3. 配置行为策略 + Agent Skill

sync 写入：

- `~/.ma3/policy/ma3-agent-policy.mdc`（含 FIRST-ACTION GATE）
- `~/.ma3/skills/ma3/SKILL.md`

再按 env 注释把 **policy 与 skill** 都复制到你的 runtime。MCP 返回 `policy_refresh_required` 时重新 sync 并再复制两者。

### 4. 接入验证（必须完成）

MCP 连通后（OAuth token 或 API key），跑通读写，确认写入 **个人库**（`ma3_report` 不带 `library_id`）：

1. **`ma3_whoami`** — 确认 principal、可见库列表含个人库
2. **`ma3_context`** — 例如 `problem`: "ma3 onboarding connectivity test"，`target_product`: "ma3"，`task_type`: "onboarding"
3. **`ma3_validate`** — 对即将写入的 `ma3_report` payload 做 dry-run
4. **`ma3_report`** — 写入一条测试记录，例如：
   - `problem`: "ma3 onboarding connectivity test"
   - `outcome`: "resolved"
   - `result_summary`: "Agent completed onboarding: whoami, context, and personal-library write succeeded."
   - `task_type`: "onboarding"
   - `tags`: `["onboarding", "connectivity-test"]`
   - **不要** 传 `library_id`（默认个人库）
   - 可用 `idempotency_key` 避免重复接入时重复写入

任一步 401/403 → API Key 方案检查 `/ui/keys/`；OAuth 方案在 MCP 客户端重新登录，并确认门户 `/auth/login` 可用。  
`client_update_required: true` → 先 `sync_ma3_client.sh sync` 并 reload MCP，再继续验证。

### 5. 收尾

- 若 `mcp_reload_required` → reload MCP；否则重启 agent runtime
- 向用户汇报：whoami 身份、context 是否返回、report 的 `record_id`（若有）

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

**Cursor / 人类交互式 MCP 客户端推荐**：只配 MCP URL，走 **OAuth 弹窗登录**（MCP Authorization Spec）。权限与门户 Layer-1 库 entitlement 一致，交互使用无需 API key。

**Agent / CI / 无头运行时推荐**：继续使用 `/ui/keys/` 或自托管 bootstrap 的 `X-API-Key`。

以下 key 示例中的 `YOUR_MA3_API_KEY` 替换为用户在 `/ui/keys/` 创建并提供的明文 key。
也可用环境变量：`${env:MA3_API_KEY}`（Cursor）、shell 展开 `${MA3_API_KEY}`（Claude `mcp add` 前先 `export`）。

### Cursor

**MCP（OAuth，交互优先）** — 创建或编辑 `~/.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "ma3": {
      "url": "https://ma3.io/mcp"
    }
  }
}
```

Cursor 会发现 `/.well-known/oauth-protected-resource`，打开登录流并附带 ma3 签发的 access token。请确保浏览器能登录同一 ma3 主机（`/auth/login`）。

**MCP（API key，Agent/CI）**：

```json
{
  "mcpServers": {
    "ma3": {
      "url": "https://ma3.io/mcp",
      "headers": {
        "X-API-Key": "${env:MA3_API_KEY}"
      }
    }
  }
}
```

**行为策略** — 推荐安装 Cursor 规则（always apply），并安装 Agent Skill：

```bash
mkdir -p ~/.cursor/rules ~/.cursor/skills/ma3
curl -fsSL https://ma3.io/client/templates/ma3-agent-policy.mdc \
  -o ~/.cursor/rules/ma3-agent-policy.mdc
curl -fsSL https://ma3.io/client/skills/ma3/SKILL.md \
  -o ~/.cursor/skills/ma3/SKILL.md
```

**重启** Cursor → **Settings → Tools & MCP** 确认 `ma3` 已连接。

---

### OpenCode

**MCP（优先 OAuth）** — 编辑 `~/.config/opencode/opencode.json`（Windows：`%USERPROFILE%\.config\opencode\opencode.json`）：

```json
{
  "mcp": {
    "ma3": {
      "type": "remote",
      "url": "https://ma3.io/mcp"
    }
  }
}
```

然后认证：

```bash
opencode mcp auth ma3
```

按提示完成浏览器登录。用 `opencode mcp list` 确认 ma3 无 SSE/content-type 报错。

**MCP（API Key / 无头）**：

```bash
opencode mcp add ma3 --url https://ma3.io/mcp --header "X-API-Key=${MA3_API_KEY}"
```

行为策略：若 OpenCode 有全局 instructions/rules 路径则写入 `/client/templates/ma3-agent-policy.mdc`；否则保留在 sync 后的 `~/.ma3/policy/`。

---

### Claude Code

```bash
claude mcp remove ma3 2>/dev/null || true
export MA3_BASE_URL=https://ma3.io          # 按用户环境
export MA3_API_KEY=YOUR_MA3_API_KEY           # 用户从 /ui/keys/ 提供
claude mcp add --scope user --transport http ma3 \
  "${MA3_BASE_URL}/mcp" \
  --header "X-API-Key: ${MA3_API_KEY}"
```

行为策略：把 `/client/templates/ma3-agent-policy.mdc` 正文写入 `~/.claude/CLAUDE.md`。

Agent Skill：

```bash
mkdir -p ~/.claude/skills/ma3
cp ~/.ma3/skills/ma3/SKILL.md ~/.claude/skills/ma3/SKILL.md
```

---

### Factory Droid

`~/.factory/mcp.json`：

```json
{
  "mcpServers": {
    "ma3": {
      "type": "http",
      "url": "https://ma3.io/mcp",
      "headers": { "X-API-Key": "YOUR_MA3_API_KEY" },
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
url = "https://ma3.io/mcp"
enabled = true

[mcp_servers.ma3.http_headers]
X-API-Key = "YOUR_MA3_API_KEY"
```

行为策略：写入 `~/.codex/model_instructions.md`。

---

### Hermes Agent

```yaml
mcp_servers:
  ma3:
    url: "https://ma3.io/mcp"
    headers:
      X-API-Key: "YOUR_MA3_API_KEY"
```

已打开的 session 执行 **`/reload-mcp`**，或重启 Hermes。

---

## API Key（自助获取）

1. 浏览器打开 `{MA3_BASE_URL}/ui/keys/`，用 Authing 注册/登录
2. 首次登录自动获得个人库；填 label 点「创建」
3. **立即复制**明文 key（只显示一次），交给 agent 填入 MCP `X-API-Key`
4. 默认授权：你的个人库 writer + Community Library writer
   - `ma3_report` 不带 `library_id` → 写入你的个人库
   - 写社区库 → 显式 `library_id: "lib_default"`
5. key 丢失/泄漏：回 `/ui/keys/` 撤销并重建

> **LAN dev 例外**：`MA3_DEV_AUTH=1` 的实例可用 `ma3dev` 作 break-glass；生产环境 **必须** 用门户 key。

---

## 验证

```bash
export MA3_BASE_URL=https://ma3.io
export MA3_API_KEY=YOUR_MA3_API_KEY   # 用户提供

curl -sf "$MA3_BASE_URL/healthz"
curl -sf "$MA3_BASE_URL/client/manifest.json" | jq .skill_bundle_version
curl -sf -H "X-API-Key: $MA3_API_KEY" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  "$MA3_BASE_URL/mcp" | jq '.result.tools[].name'
```

接入后由 agent 完成 **接入验证**（`ma3_whoami` → `ma3_context` → `ma3_validate` → `ma3_report` 写个人库）。

---

## 故障排查

| 现象 | 处理 |
|------|------|
| 有 MCP 但不主动调用 | 策略未写入 `~/.cursor/rules/ma3-agent-policy.mdc` 或等价全局 instructions |
| Agent 从不写回 ma3 | 检查策略 mandatory report；writer key；是否被 `client_update_required` 阻塞 |
| `client_update_required` 一直 true | curl 刷新 policy；把 `client_version` 改为 manifest 的 `skill_bundle_version` |
| `ma3_context` 超时 | `curl $MA3_BASE_URL/healthz` |
| `ma3_report` 401/403 | API key 无效/已撤销，或 OAuth token 缺失/过期 — 重新登录或重建 key |
| 用户尚未注册 | 引导至 `/auth/login`；随后 IDE 走 OAuth，CLI 走 `/ui/keys/` |
| CLI agent 卡在 OAuth | OAuth 需要浏览器 — 改用 `/ui/keys/` 的 `X-API-Key` |

---

## 给用户的简短说明

> 把下面这段贴给你的 agent（或打开 `{MA3_BASE_URL}/client/connect.md`）：
>
> *请帮我接入 `{MA3_BASE_URL}` 的 ma3 MCP。先 GET `{MA3_BASE_URL}/client/connect.md` 并按文档执行。不要编造 API key。Cursor/IDE → OAuth（只配 url）。CLI → 我去 `/ui/keys/` 创建 key 后贴给你。*
>
> 登录后，主页 `/ui/me/` 也会显示可复制的「贴给 agent」接入块。
> 无需 clone 仓库，无需安装 CLI。
