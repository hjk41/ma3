# 接入 ma3 MCP（给 Agent 看）

> English: [connect.md](connect.md) · 完整指南: [agent-onboarding.zh.md](agent-onboarding.zh.md)

**读者**：用户说「帮我接入 ma3 / ma3.io 的 MCP」的任意 Agent——包括用户**还没注册**的情况。

**不要**编造 API key，**不要**默认 `ma3dev`。按下面顺序做。

## 0. 确定 Base URL（自行推断，不要追问）

| 用户说法 | 你应使用的 Base | 是否再问 URL |
|----------|-----------------|--------------|
| `ma3` / `ma3.io` /「接入 ma3」且**未**给其它主机 | `https://ma3.io` | **禁止**再问 URL |
| 明确说内网 / 自托管 / 自定义 host:port | 用户给出的 URL（含协议与端口） | 仅此时询问/确认 |

硬性规则：

- MCP 端点永远是 `{BASE}/mcp`（必须带路径 `/mcp`）。
- SaaS 用 **HTTPS** `https://ma3.io`——**禁止**臆造 `http://…:8000`，也禁止漏掉 `/mcp`。
- 用户已经说 ma3 / ma3.io 时，**不要**停下来问「ma3 地址是什么」。
- 唯一可以等人的环节是 **登录 / OAuth / 粘贴 API key**。其余（拉文档、写 MCP 配置、装 policy/skill、验证）自行完成。

下文 `{BASE}` 表示该 URL（无尾斜杠）。

## 1. 拉取完整接入文档

```bash
curl -fsSL "{BASE}/client/agent-onboarding.md"
```

中文全文：`{BASE}/client/agent-onboarding.zh.md`

其它免登录资源：

| URL | 用途 |
|-----|------|
| `{BASE}/client/connect.md` | 本短路径 |
| `{BASE}/client/manifest.json` | sync 用版本清单 |
| `{BASE}/client/templates/ma3-agent-policy.mdc` | 行为策略 |
| `{BASE}/mcp/info` | MCP 能力发现 |

## 2. 按 runtime 分支

### A. 交互式 IDE（Cursor、OpenCode 等）— 优先 OAuth

1. 用户若**还没有账号**：请其浏览器打开 `{BASE}/auth/login`（或 `{BASE}/ui/home/` 注册），完成显示名 setup。
2. MCP 配置**只写 URL**（不要 Key）。OpenCode：`~/.config/opencode/opencode.json` → `mcp.ma3 = { "type": "remote", "url": "{BASE}/mcp" }`，必要时再跑 `opencode mcp auth ma3`：

```json
{
  "mcpServers": {
    "ma3": {
      "url": "{BASE}/mcp"
    }
  }
}
```

3. 重启 / reload MCP。客户端应收到 `401` + `WWW-Authenticate`，弹窗登录，拿到 ma3 签发的 `ma3mcp_…`。
4. 用 `ma3_whoami` 验证（`via` 可能为 `mcp_oauth_token`）。
5. 再按 `agent-onboarding` §1–3 同步 policy/skill。

### B. CLI / 无头 Agent（Claude Code、Codex、Droid、Hermes、CI）— 必须 API Key

OAuth 需要浏览器会话，**不要**当成 CLI 主路径。

1. 请用户打开 `{BASE}/ui/keys/`（未登录先注册/登录）。
2. 创建 key（默认个人库 + Community writer），**立刻复制明文**贴给你。
3. 按 `agent-onboarding.zh.md` 对应章节配置 `X-API-Key`。
4. Bootstrap `~/.ma3` + `sync_ma3_client.sh sync`，再跑 `ma3_whoami` / `ma3_context` / dry-run `ma3_report`。

## 3. 给用户可复制的提示词

若用户不知道怎么吩咐你，让他粘贴：

```text
请帮我接入 {BASE} 的 ma3 MCP。
1) 先 GET {BASE}/client/connect.md，按我的 runtime 执行。
2) Base 已是 {BASE}：不要再问 URL，不要臆造 :8000；MCP 用 {BASE}/mcp。
3) 不要编造 API key。除登录/OAuth/贴 key 外自行完成配置与验证。
4) 若我还没注册，先让我打开 {BASE}/auth/login。
5) Cursor/IDE/OpenCode → OAuth（mcp 只配 url）。CLI/CI → 我去 {BASE}/ui/keys/ 创建 key 后贴给你。
```

## 4. 完成标准

- `ma3_whoami` 返回非匿名主体且有可写库
- 对应 runtime 已安装 policy/skill
- 可选：dry-run `ma3_report` 成功

完整说明与各 Agent 示例：`{BASE}/client/agent-onboarding.md`（中文 `.zh.md`）。
