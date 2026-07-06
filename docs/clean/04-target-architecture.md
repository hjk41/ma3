# 04 — 目标架构（v1 定稿）

> **已拍板**（ADR 001–009；原讨论过程见旧 `docs/design/03-design-review.md`）：
> - SaaS 多租户为首要形态；LAN = dev profile（同一 binary）
> - Agent 面 = **MCP + policy**，删除 `install.sh` / CLI plugin
> - 全部 library 默认 active 写入（后由 [16-library-write-buffer.md](16-library-write-buffer.md) 增加 buffered 窗口）
> - 默认启用 vector，`MA3_DISABLE_EMBEDDINGS=1` 可关
> - Observatory（只读：cases、search、explain）；**仅产品管理员可访问**（见 [15-user-portal.md](15-user-portal.md)）
> - 版本语义 = `protocol_version` + `skill_bundle_version`（Scheme B）
> - org 表进 v1，单租户可隐式 default org；monorepo；eval 在 monorepo、非发布物

## 1. 系统上下文

> 产品角色与价值主张见 [`PITCH.md`](../pitch/PITCH.md) §为谁而建、§维护分层。

```text
┌─────────────────┐
│ Agent 贡献者     │── MCP ──► 查 / 写 verified 知识
└─────────────────┘
┌─────────────────┐
│ Agent 维护者     │── MCP ──► 日常治理（可审计，可人纠偏）
└─────────────────┘
┌─────────────────┐
│ 人 — 用户        │── 用户门户 /ui/me/* ──► 库权限、贡献、投票、API keys
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

## 2. 模块划分（`code/`）

```text
ma3/
├── docs/
├── code/
│   ├── server/
│   │   ├── mcp/              # tools, payloads, server block
│   │   ├── domain/           # org, library, case, record, relation
│   │   ├── search/           # fts + vector (disable flag)
│   │   ├── auth/             # OIDC (Authing), api_keys, library_acl
│   │   ├── ui/               # 用户门户 + Observatory (admin)
│   │   └── admin/            # doctor, metrics, key mgmt
│   ├── client/               # HTTP bundle：manifest、policy、sync 脚本（无 ma3 CLI）
│   └── deploy/
│       ├── profile-saas/     # 首要
│       └── profile-lan/      # dev / 自建
└── eval/                     # 非 v1 发布物
```

**v1 core 包含**：org、library ACL、OIDC（Authing）、vector search、用户门户、Observatory（admin）。  
**v1 core 不包含**：billing 完整 UI、seat 计费、LTP bootstrap、v1 legacy REST agent 面、CLI/`install.sh`。

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

**不 ship**：`client/install.sh`、CLI 子命令、仓库内平行 `AGENTS.md` 副本、各 agent runtime 的路径预设（改由 agent 填 `ma3-client.env`）。

### 3.2 Onboarding（agent 侧，一次性）

```text
（人）浏览器 /ui/keys/ 自助创建 API key（见 13-self-service-onboarding.md）
curl env 模板 → ~/.ma3/ma3-client.env（编辑 MA3_BASE_URL、policy 安装注释）
curl sync 脚本 → ~/.ma3/bin + ~/.ma3/lib
sync_ma3_client.sh sync  →  ~/.ma3/ma3-client.json + policy + mcp-tools 缓存
配置 MCP（runtime 自有格式，X-API-Key）+ 按 env 注释复制 policy 到 runtime
```

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

## 4. MCP tools

| Tool | 职责 |
|------|------|
| `ma3_context` | 读（含作者本人 buffered） |
| `ma3_case` | case 展开 |
| `ma3_report` | 写（`report_kind` + buffer 语义见 [10](10-write-audit-and-delete.md)、[16](16-library-write-buffer.md)） |
| `ma3_validate` | dry-run |
| `ma3_doctor` / `ma3_whoami` | 诊断 |
| `ma3_list_my_writes` | 本人写入审计列表 |
| `ma3_delete_record` | owner 删除本人 record |
| `ma3_publish_record` | 作者提前发布 buffered record |
| `ma3_feedback` | 投票（每 principal 一票） |
| `ma3_list_drafts` / `ma3_review_record` | **维护者 Agent** / 人（UI v1.1） |

> `ma3_search_explain` 已**删除**、`ma3_context.include_explain` 已**移除**——排序分解只经内部 / Observatory 暴露（[12-search-ranking.md](12-search-ranking.md)，防刷榜）。

## 5. 数据模型

```text
organizations
  └── libraries (org_id NOT NULL; visibility public|org|private; write_buffer_hours)
        └── cases
              └── records (status: active | buffered | draft | invalid | trashed)
                    └── relations
principals (OIDC user | api_key)
  └── library_grants / api_key_grants (reader | writer | maintainer)
```

- **maintainer**：Agent — 维护者（日常治理；可人撤销）
- **admin / 人 — 维护者**：覆盖 Agent 维护者；隐私/价值观最终删除权

单租户部署使用 **`org_default`**；公共 library 与团队 library **同一套模型**（Pitch：Community, not silo）。完整 ACL 模型见 [08-kb-access-and-org-isolation.md](08-kb-access-and-org-isolation.md)。

## 6. 写入路径与质量状态机

### 6.1 两条路径（ADR-002 + ADR-006）

```text
路径 A — Hook（可选，v1 可不实现）
  agent runtime hooks
    → 本地 draft candidate（JSON/SQLite，TTL）
    → 默认不上送 ma3

路径 B — ma3_report（v1 必达）
  agent 主动 MCP 写回 → ma3 服务端
    → new/supplement 且库 buffer>0 → status=buffered（write buffer 窗口）
    → verify/refute 或 buffer=0 → status=active
```

Hook **禁止**静默创建 active record 或默认 POST 到 ma3。

### 6.2 状态机（服务端 record）

```text
ma3_report ──► buffered  (new/supplement + 库 write_buffer_hours>0；期满/作者确认 → active)
            └──► active   (verify/refute 直达；buffer=0 库)
            └──► draft    (explicit visibility=draft only)
            └──► invalid  (review reject / admin)
active ──► trashed (仅 deletion_protection 库软删) ──► 到期 purge
```

**风险与缓解**（ADR-002 + ADR-008）：

- 搜索污染 → write buffer + ranking（[12](12-search-ranking.md)）+ **维护者 Agent** 日常扫描 + **人 — 维护者** mark invalid
- Agent 误写 → policy 强制写前校验 + buffer 窗口内作者可撤回（[16](16-library-write-buffer.md)）
- 隐私 / 价值观 → **人 — 维护者** 最终清除
- hook 误采集 → 本地留存，仅 promote 后进库（ADR-006）

## 7. 搜索 / Embedding

| 模式 | 配置 | 用途 |
|------|------|------|
| **Default** | vector + FTS | 生产 / SaaS / 完整 LAN |
| **Minimal** | `MA3_DISABLE_EMBEDDINGS=1` | 无 GPU、无 HF 网络（**仍走统一 GTN 排序管线**，见 [12](12-search-ranking.md)） |

部署规范（两 profile 共享）：

- prewarm → `HF_HOME/.../hub/`
- 生产：`HF_HUB_OFFLINE=1`
- rsync **exclude** `data/`, `.venv`

## 8. Auth

### profile-saas（首要）

- OIDC：Authing 社交登录（ADR-010）；session 用于 UI（门户 + Observatory + key 管理）
- API keys：`ma3k_…` per principal + per-library grants；MCP 数据路径**只认 `X-API-Key`**（[08](08-kb-access-and-org-isolation.md)）
- Admin：`MA3_AUTH_ADMIN_USERS`；**Authing 启用且 admin 白名单为空 → 拒绝启动**（[15](15-user-portal.md)）
- break-glass：`MA3_DEV_AUTH=1` + `MA3_DEV_API_KEY`（LAN only）

### profile-lan（dev）

- `MA3_DEV_AUTH=1`：单 writer key，跳过 OIDC
- 其余与 saas core 同代码路径

## 9. Web UI（v1 范围）

两个面：

1. **用户门户 `/ui/me/*` 等**（默认落地）— 以 principal 为中心：库权限、贡献、投票、API keys。规格见 [15-user-portal.md](15-user-portal.md) + [22-user-portal-ui-layout.md](22-user-portal-ui-layout.md)。
2. **Observatory `/ui/observatory/*`**（仅 `is_admin`，非 admin → **403**）— 全局 Stats + 枚举、search explain 面板（内部）、deploy banner。

**不包含 v1**：Review queue 完整工作流 UI（draft 审批走 MCP `ma3_review_record`，v1.1 UI）、org/seat/billing 管理页。

**v1 治理写路径（ADR-007 + ADR-008）**：

- **Agent — 维护者**：MCP 日常维护（invalid / review）；动作可审计、**可被人撤销**
- **人 — 维护者**：Observatory + 更高权限 — mark invalid、纠偏 Agent 维护者、清除隐私/价值观不合规内容
- v1.1+：维护者 Agent 动作队列、人审工作台、library policy 模板

## 10. 版本语义（Scheme B）

| 字段 | 含义 |
|------|------|
| `service_version` | 服务端 release |
| `skill_bundle_version` | manifest 内 policy + onboarding 集合 |
| `sync_tooling_version` | sync 脚本/lib 集合（`scripts/*` + `lib/*`） |
| `protocol_version` | MCP JSON-RPC |
| `tool_schema_version` | Ma3*Payload / `tools/list` 代际 |

Agent 上报（每次 MCP 调用）：`client_version` → 对齐 `skill_bundle_version`；`tool_schema_version` → 对齐 manifest。本地 state（默认 `~/.ma3/ma3-client.json`）记录上次 sync 的版本与各文件 sha256。

**升级路径**：MCP `server` 标志 → `sync_ma3_client.sh sync` → 必要时 IDE reload MCP → 写路径前确认 `client_update_required: false`（ADR-009）。

## 11. 部署文档真源

`docs/deploy/`：

| 文件 | 优先级 |
|------|--------|
| `profile-common.md` | HF cache、healthz、env |
| `profile-saas.md` | **首要** |
| `profile-lan.md` | dev / 202 |
| `profile-ltp.md` | legacy，非 v1 core |

## 12. ADR 索引

| ADR | 主题 | 状态 |
|-----|------|------|
| [001](../adr/001-saas-primary-deploy.md) | SaaS 首要 | Accepted |
| [002](../adr/002-active-default-writes.md) | 写回默认 active | Accepted |
| [003](../adr/003-mcp-only-agent-surface.md) | MCP + policy，无 CLI | Accepted |
| [004](../adr/004-vector-default-optional-off.md) | Vector 默认开 | Accepted |
| [005](../adr/005-observatory-ui-scope.md) | Observatory 范围 | Accepted |
| [006](../adr/006-hook-candidates-local-first.md) | Hook 候选本地优先 | Accepted |
| [007](../adr/007-v1-milestones-and-observatory-governance.md) | 里程碑与 Observatory 治理 | Accepted |
| [008](../adr/008-maintainer-human-or-agent.md) | 维护者：人与 Agent | Accepted |
| [009](../adr/009-client-sync-scheme-b.md) | Client sync Scheme B | Accepted |
| [010](../adr/010-authing-social-login.md) | Authing 社交登录 | Accepted |
| [011](../adr/011-kb-access-and-org-isolation.md) | KB 访问与 org 隔离 | Accepted |
| [012](../adr/012-billing-and-quotas.md) | 付费套餐与配额 | Accepted |
| [013](../adr/013-write-confirmation-audit-delete.md) | 写入确认、审计、删除 | Accepted |
| [014](../adr/014-mcp-error-self-correction.md) | MCP 错误可自纠 | Accepted |
