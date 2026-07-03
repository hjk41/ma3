# 04 — 目标架构（v1 定稿 · 2026-07-01）

> **已拍板**（见 `03-design-review.md` §F、`docs/adr/`）：
> - Q1 = **B**（SaaS 多租户为首要形态；LAN = dev profile）
> - Q4 = **MCP + policy**，删除 `install.sh` / CLI plugin
> - Q5 = **全部 library 默认 active**
> - Q9 = **默认启用 vector**，`MA3_DISABLE_EMBEDDINGS=1` 可关
> - Q11 = **Observatory**（只读：cases、search、explain）
> - Q6 = **B**（`protocol_version` + `skill_bundle_version`，未单独讨论，沿用 review 倾向）
> - Q7 = **A**（agent 仅 MCP；人用的 REST/UI 保留）
> - Q3 = **B**（org 表进 v1，单租户可隐式 default org）
> - Q8 = **A**（monorepo）；Q10 = deploy profiles；Q12 = **B**（eval 在 monorepo，非发布物）

## 1. 系统上下文

> 产品角色与价值主张见 [`PITCH.md`](PITCH.md) §为谁而建、§维护分层。

```text
┌─────────────────┐
│ Agent 贡献者     │── MCP ──► 查 / 写 verified 知识
└─────────────────┘
┌─────────────────┐
│ Agent 维护者     │── MCP ──► 日常治理（可审计，可人纠偏）
└─────────────────┘
┌─────────────────┐
│ 人 — 维护者      │── Observatory ──► 监督、纠偏、隐私/价值观裁量
└─────────────────┘
┌─────────────────┐
│ 组织 — 管理者    │── Admin（v1.1+ 完整 UI）──► 成员、订阅
└─────────────────┘
         │                    ┌──────────────────┐
         └───────────────────►│ ma3 server       │
                              │  MCP / UI / auth │
                              └────────┬─────────┘
                                       │ PostgreSQL + search (vector 默认)
```

**Dev profile**：与 SaaS **同一 binary**；本地/自建可用简化 auth，**不是**另一套产品。

## 2. 模块划分（`ma3_v1/code/`）

```text
ma3_v1/
├── docs/
├── code/
│   ├── server/
│   │   ├── mcp/              # tools, payloads, server block
│   │   ├── domain/           # org, library, case, record, relation
│   │   ├── search/           # fts + vector (disable flag)
│   │   ├── auth/             # OIDC verify, api_keys, library_acl
│   │   ├── ui/               # Observatory (read-only v1)
│   │   └── admin/            # doctor, metrics, key mgmt
│   ├── client/               # HTTP bundle：manifest、policy、sync 脚本（无 ma3 CLI）
│   └── deploy/
│       ├── profile-saas/     # 首要
│       └── profile-lan/      # dev / 自建
└── eval/                     # 非 v1 发布物，monorepo 内链接旧 harness
```

**v1 core 包含**：org、library ACL、OIDC、vector search、Observatory。  
**v1 core 不包含**：billing、seat 计费、LTP bootstrap、v1 legacy REST agent 面、CLI/`install.sh`。

## 3. Agent 契约（唯一路径）

### 3.1 HTTP 面（ADR-003 + ADR-009）

| 组件 | 说明 |
|------|------|
| `POST /mcp` | 全部 agent 读写 |
| `GET /client/manifest.json` | 双版本 + 全 bundle sha256/url + `sync_tooling_version` |
| `GET /client/templates/ma3-client.env.example` | **agent 自填**本地路径模板（非 per-runtime 预设） |
| `GET /client/scripts/sync_ma3_client.{sh,py}` | 同步入口（HTTP bootstrap，非 ma3 CLI） |
| `GET /client/lib/ma3_sync_core.py` | 同步核心（stdlib only） |
| `GET /client/templates/ma3-agent-policy.mdc` | 行为策略 bundle |
| `GET /client/agent-onboarding.md` | 接入步骤（操作真源） |
| `GET /client/mcp-tools.json` | MCP `tools/list` 快照 |

**删除**（v1 不 ship）：

- `client/install.sh`
- `client/skills/ma3/scripts/ma3_client.py` 及 CLI 子命令
- 仓库内平行 `AGENTS.md` 副本（LTP 运维段落迁入 `docs/deploy/profile-ltp.md`）
- repo 内 **各 agent runtime 的路径预设**（改由 agent 填 `ma3-client.env`）

### 3.2 Onboarding（agent 侧，一次性）

```text
curl env 模板 → ~/.ma3/ma3-client.env（编辑 MA3_BASE_URL、policy 安装注释）
curl sync 脚本 → ~/.ma3/bin + ~/.ma3/lib
sync_ma3_client.sh sync  →  ~/.ma3/ma3-client.json + policy + mcp-tools 缓存
配置 MCP（runtime 自有格式）+ 按 env 注释复制 policy 到 runtime
```

细节见 `code/client/agent-onboarding.md` 与 ADR-009。

### 3.3 运行时版本上报（Scheme B）

Agent **每次** MCP `tools/call` 传：

- `client_version` = 本地 state 的 `skill_bundle_version`
- `tool_schema_version` = 本地 state 的 `tool_schema_version`

本地真相源：`~/.ma3/ma3-client.json`（路径可在 env 中覆盖）。

每 MCP 响应 `structuredContent.server` 含升级标志：

| 标志 | 含义 |
|------|------|
| `policy_refresh_required` | policy/onboarding 落后 → sync + 复制 policy |
| `mcp_reload_required` | MCP schema 落后 → sync + **IDE reload MCP** |
| `client_update_required` | 任一层 breaking → sync + reload；**停止 ma3_report 等写路径** |

推荐升级：`bash ~/.ma3/bin/sync_ma3_client.sh sync`（manifest 驱动；含 **sync 脚本自更新**）。

### 3.4 与旧描述的差异

- 不仅 `curl policy.mdc`：需 state 文件 + 双版本字段 + 可选 sync 工具链。
- `client_version` 仍映射 skill bundle；**另增** `tool_schema_version` 映射 MCP payload 代际。

## 4. MCP tools（不变集合）

| Tool | 职责 |
|------|------|
| `ma3_context` | 读 |
| `ma3_case` | case 展开 |
| `ma3_report` | 写（**默认 active**） |
| `ma3_validate` | dry-run |
| `ma3_doctor` / `ma3_whoami` | 诊断 |
| `ma3_list_drafts` / `ma3_review_record` | **维护者 Agent** / 人（UI v1.1） |

`ma3_report` 成功响应（active 默认）：

```json
{
  "persisted": true,
  "record_id": "vk_…",
  "status": "active",
  "case_assignment": { "case_id": "cs_…", "mode": "auto" }
}
```

可选 **`status=draft`**：仅当 payload 显式 `visibility=draft` 或 library 策略覆盖（v1 默认不覆盖）。

## 5. 数据模型

```text
organizations
  └── libraries (org_id NOT NULL)
        └── cases
              └── records (status: active | draft | invalid)
                    └── relations
principals (OIDC user | api_key)
  └── library_grants (reader | writer | library_maintainer | library_admin)
```

- **`library_maintainer`**：Agent — 维护者（日常治理；可人撤销）  
- **`library_admin`**：人 — 维护者（覆盖 Agent 维护者；隐私/价值观最终删除权）

单租户部署使用 **`org_default`**；UI/API 可隐藏 org 切换。公共 library 与团队 library **同一套模型**（Pitch：Community, not silo）。

## 6. 写入路径与质量状态机

### 6.1 两条路径（ADR-002 + ADR-006）

```text
路径 A — Hook（可选，v1 可不实现）
  agent runtime hooks
    → 本地 draft candidate（JSON/SQLite，TTL）
    → 默认不上送 ma3

路径 B — ma3_report（v1 必达）
  agent 主动 MCP 写回
    → ma3 服务端
    → status=active（默认）
```

Hook **禁止**静默创建 active record 或默认 POST 到 ma3。

### 6.2 状态机（服务端 record）

```text
ma3_report ──► active   (default)
            └──► draft  (explicit visibility=draft only)
            └──► invalid (review reject / admin)
```

**风险与缓解**（ADR-002 + ADR-008，对齐 Pitch §维护分层）：

- 搜索污染 → ranking 降权；**维护者 Agent** 日常扫描；**人 — 维护者** mark invalid / 纠偏
- Agent 误写 → policy 强制写前校验 + 自动脱敏
- 隐私 / 价值观 → **人 — 维护者** 最终清除
- hook 误采集 → 本地留存，仅 promote 后进库（ADR-006）

## 7. 搜索 / Embedding

| 模式 | 配置 | 用途 |
|------|------|------|
| **Default** | vector + FTS | 生产 / SaaS / 完整 LAN |
| **Minimal** | `MA3_DISABLE_EMBEDDINGS=1` | 无 GPU、无 HF 网络 |

部署规范（两 profile 共享）：

- prewarm → `HF_HOME/.../hub/`
- 生产：`HF_HUB_OFFLINE=1`
- rsync **exclude** `data/`, `.venv`

## 8. Auth

### profile-saas（首要）

- OIDC：`MA3_AUTH_VERIFY_URL` 在线校验 JWT
- Library API keys：`ma3v4_…` per library
- Admin：`MA3_AUTH_ADMIN_USERS` + break-glass `MA3_API_KEY`

### profile-lan（dev）

- `MA3_DEV_AUTH=1`：单 writer key，跳过 OIDC
- 其余与 saas core 同代码路径

## 9. Observatory UI（v1 范围）

**包含**：

- Library / case 浏览
- Record 详情与 relation 图（只读）
- Search + **explain** 面板（内部排名分解，**不**经 MCP 暴露）
- Deploy banner（healthz 身份）

**不包含 v1**：

- Review queue 完整工作流 UI（draft 审批走 MCP `ma3_review_record`，v1.1 UI）
- Org/seat/billing 管理页

**v1 治理写路径（ADR-007 + ADR-008）**：

- **Agent — 维护者**：MCP 日常维护（invalid / review）；动作可审计、**可被人撤销**
- **人 — 维护者**：Observatory + 更高权限 — mark invalid、**纠偏 Agent 维护者**、清除 **隐私 / 价值观不合规** 内容
- v1.1+：维护者 Agent 动作队列、人审工作台、library policy 模板

Observatory 是人的社区窗口；Agent 维护者与 UI **共享 domain 逻辑**，不单独分叉。

路由：`/ui/observatory/*`；deploy banner 与 healthz 身份一致。

## 10. 版本语义（Q6 = B，Scheme B）

| 字段 | 含义 |
|------|------|
| `service_version` | 服务端 release |
| `skill_bundle_version` | manifest 内 policy + onboarding 集合 |
| `sync_tooling_version` | sync 脚本/lib 集合（`scripts/*` + `lib/*`） |
| `protocol_version` | MCP JSON-RPC |
| `tool_schema_version` | Ma3*Payload / `tools/list` 代际 |

Agent 上报（每次 MCP 调用）：

- `client_version` → 应对齐 `skill_bundle_version`
- `tool_schema_version` → 应对齐 manifest 的 `tool_schema_version`

本地 state（默认 `~/.ma3/ma3-client.json`）记录上次 sync 的版本与各文件 sha256。

废弃独立 `CLIENT_VERSION=0.4.0`；manifest 与 server semver **对齐 major**，skill bundle 与 tool schema 可独立 bump。

**升级路径**：MCP `server` 标志 → `sync_ma3_client.sh sync` → 必要时 IDE reload MCP → 写路径前确认 `client_update_required: false`（ADR-009）。

## 11. 部署文档真源

`docs/deploy/`：

| 文件 | 优先级 |
|------|--------|
| `profile-common.md` | HF cache、healthz、env |
| `profile-saas.md` | **首要** |
| `profile-lan.md` | dev / 202 |
| `profile-ltp.md` | legacy，非 v1 core |

## 12. 迁移路线

| 阶段 | 动作 |
|------|------|
| 0 | ✅ Pitch 定稿 + ADR 001–009 + 设计对齐（`06-pitch-alignment-review.md`） |
| 1 | dev 平行实例：SaaS core + MCP + vector（ADR-007） |
| 2 | Observatory：人 — 维护者浏览 + mark invalid + **纠偏 Agent 维护者**（op log） |
| 3 | cutover 前 migration script（新库，`org_default`） |
| 4 | SaaS staging（完整 OIDC）→ 公网 |

## 13. ADR 索引

| ADR | 主题 | 状态 |
|-----|------|------|
| [001](adr/001-saas-primary-deploy.md) | SaaS 首要 | Accepted |
| [002](adr/002-active-default-writes.md) | 写回默认 active | Accepted |
| [003](adr/003-mcp-only-agent-surface.md) | MCP + policy，无 CLI | Accepted |
| [004](adr/004-vector-default-optional-off.md) | Vector 默认开 | Accepted |
| [005](adr/005-observatory-ui-scope.md) | Observatory 范围 | Accepted |
| [006](adr/006-hook-candidates-local-first.md) | Hook 候选本地优先 | Accepted |
| [007](adr/007-v1-milestones-and-observatory-governance.md) | 里程碑与 Observatory 治理 | Accepted |
| [008](adr/008-maintainer-human-or-agent.md) | 维护者：人与 Agent | Accepted |
| [009](adr/009-client-sync-scheme-b.md) | Client sync Scheme B + env 自填 + tooling 自更新 | Accepted |
