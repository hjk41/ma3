# agent-client-sync — Docker 多 Agent 安装/升级测试（真实 CLI）

> English default: [README.md](README.md)

**ma3 跑在 host（LAN 测试主机 `:8000`），Docker 只装 agent 二进制并测 sync。**

## 架构

```text
LAN host (维护者内网测试主机)
  ma3_v1 :8000          ← 真实服务；升级测试时 restart + MA3_SKILL_VERSION
  docker compose
    runner              ← Claude / Codex / Cursor / Droid 真实 CLI
      → MA3_BASE_URL=http://host.docker.internal:8000
      → 各 agent 独立 HOME（volume agent-homes）
```

原先 compose 里再跑一个 ma3 是为了 **隔离升级**（随意 bump skill version），但：
- 与 LAN host 上已部署实例重复
- 增加构建失败面（Docker 镜像层、proxy 等）
- 测的不是你实际在用的 ma3

**现方案**：升级阶段在 host 上 `restart_host_ma3.sh 2.0.0`，Docker 里 agent 再 sync；结束后 restore 回 `1.0.0`。

## 真实二进制（runner 镜像）

| Agent | 安装 |
|-------|------|
| Claude Code | `npm i -g @anthropic-ai/claude-code` |
| Codex | `npm i -g @openai/codex` |
| Cursor | `curl cursor.com/install` → `agent` / `cursor-agent` |
| Droid | host 二进制 bundle 或 factory installer |

## 在 LAN host 上跑

```bash
# 先部署（通用脚本 + 本地 LAN 配置，见 deploy/README.md）
./deploy/deploy.sh deploy/deploy.<lan>.env
# 再跑本 scenario
cd code/eval/scenarios/agent-client-sync && bash run.sh
```

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `MA3_HOST_MA3_URL` | `http://host.docker.internal:8000` | runner 访问 host ma3 |
| `MA3_RESTORE_VERSION` | `1.0.0` | 测试结束 restore 的 skill version |
| `MA3_DIR` | `~/ma3_deploy` | host ma3 路径（restart 脚本） |
