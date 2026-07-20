# 自托管 MVP 改造清单

> **目标**：陌生人能在一台干净机器上，用文档 + Compose，在 **≤1 小时** 内跑起可用的私有 ma3（MCP 读写），且默认配置不把实例暴露成公网后门。  
> **非目标（MVP 不做）**：联邦公共库、Stripe、企业 SAML、多机 HA、官方 Community 同步。  
> **现状锚点**：Apache-2.0 已有；`deploy/deploy.sh` 面向「我们自己的远端」；Auth 主路径仍绑 Authing；无官方 server Compose。

---

## 已拍板决策（2026-07-20）

| # | 议题 | 决策 |
|---|------|------|
| 1 | Auth | **解耦 IdP**：可接入用户自有 **OIDC**；**未配置 OIDC 时默认 bootstrap key**（无门户登录也能用 MCP） |
| 2 | Embeddings | Compose / 自托管默认 **开启**（`MA3_DISABLE_EMBEDDINGS` 默认关；文档写清 HF 缓存与体积） |
| 3 | 反代 | **不是硬性前提**（见下文说明）；MVP 默认局域网可直连；公网 / OIDC 场景**推荐**反代 + HTTPS |
| 4 | 支持 | **无 SLA**；GitHub Issues / Discussion **best-effort** |

### 关于「为什么需要反代？」（决策 3 说明）

**反代不是 ma3 协议要求，也不是 bootstrap-key 局域网模式的前置条件。**

Uvicorn 可以直接监听端口。之所以常提 Caddy/nginx，是因为它们解决的是**暴露面与登录流**问题，不是 MCP 本身：

| 场景 | 要不要反代 |
|------|------------|
| 本机 / 局域网，只用 bootstrap API key，HTTP | **不需要**。Compose 绑 `0.0.0.0:8000` 或宿主机端口即可（注意防火墙） |
| 要上 **OIDC 登录门户** | **强烈建议**。多数 IdP 要求 **HTTPS** 回调 URL，并要有稳定域名；反代做 TLS 终止最省事 |
| 把实例挂到**公网** | **强烈建议**。反代提供 TLS、可选限流/IP 允许列表，避免把裸 uvicorn + 管理面直接暴露 |
| 仅 SSH 隧道访问 | 可不反代；等价于「只给自己用」 |

MVP 文档写法建议：

- 默认路径：「局域网直连 + bootstrap key」——零反代  
- 进阶路径：「公网或 OIDC → 自备反代（示例 Caddyfile）+ `MA3_PUBLIC_BASE_URL=https://…`」

---

## 验收定义（Done = 全部勾上）

- [x] `deploy/self-host` Compose + Dockerfile + initdb pgvector + up/verify（见 [self-hosting.md](self-hosting.md)）
- [x] **无 OIDC**：startup bootstrap → `MA3_BOOTSTRAP_KEY_FILE`
- [x] **有 OIDC**：`MA3_OIDC_*`（`MA3_AUTHING_*` 兼容别名）+ ADR-015
- [x] Authing 降级为一种 OIDC 配置 / 路径兼容
- [x] Compose 默认关闭 `MA3_DEV_AUTH`；embeddings 默认开
- [x] 文档：Community 语义、反代非硬性、**无 SLA**；根目录 `SECURITY.md`
- [ ] 端到端：在干净机器上实跑 `./up.sh` + MCP report（发布前人工勾）
- [ ] 清扫历史文档中的内网 IP 样例（P0-E1，可并行）

---

## P0 — 必须做

### A. 交付物：一键栈

| ID | 项 | 产出 | 备注 |
|----|----|------|------|
| A1 | 官方 `docker-compose.yml`（server + Postgres/pgvector） | `deploy/self-host/docker-compose.yml` | 勿复用 eval compose |
| A2 | Server `Dockerfile`（生产向） | `deploy/self-host/Dockerfile` 等 | |
| A3 | 自托管 env 模板 | `deploy/self-host/.env.example` | 与 SSH 用 `deploy.env.sample` 分开 |
| A4 | 入口脚本 | `up.sh` + `verify.sh` | |
| A5 | 数据卷约定 | volumes + 文档 | DB、**HF cache（默认开 embeddings）** |
| A6 | （可选）示例 Caddyfile | `deploy/self-host/Caddyfile.example` | 公网/OIDC 进阶；非默认依赖 |

### B. Auth：OIDC 可插拔 + 默认 bootstrap

| ID | 项 | 产出 | 备注 |
|----|----|------|------|
| B1 | **OIDC 抽象**（ADR） | `docs/02-architecture/decisions/0xx-oidc-provider.md` | 配置：issuer、client_id/secret、redirect；Authing = 文档示例 |
| B2 | 代码解耦 Authing 专用假设 | `auth/` 改为通用 OIDC 客户端 | 保留 Authing env 别名作兼容层（可选） |
| B3 | **未配置 OIDC → bootstrap key 模式** | 启动或 `bootstrap_selfhost` 命令 | 创建 admin/principal + personal lib + writer key，stdout 打印一次；门户登录可禁用或显示「未启用 OIDC」 |
| B4 | 启动护栏 | config 校验 | 无 OIDC 时不要求 `MA3_AUTH_ADMIN_USERS` 的 Authing 语义；公网 + `DEV_AUTH=1` 仍拒启 |
| B5 | 自托管 Auth 文档 | `self-hosting.md` | 两节：Bootstrap 快速开始 / 接入自有 OIDC（含 Authing 示例） |

### C. 依赖：Postgres / vector / embeddings（默认开）

| ID | 项 | 产出 | 备注 |
|----|----|------|------|
| C1 | Compose Postgres + pgvector | 镜像 + init | 超户 `CREATE EXTENSION vector` |
| C2 | App 角色不自建 extension | init/runbook | |
| C3 | **默认启用 embeddings** | `.env.example` 不设 disable | 文档：首次拉取体积、代理、`HF_HOME/hub`、可事后 `HF_HUB_OFFLINE=1`；弱机器可显式关闭 |
| C4 | Fernet 密钥 | `.env.example` | 丢失则无法解密已存 key plaintext |

### D. 文档与叙事

| ID | 项 | 产出 | 备注 |
|----|----|------|------|
| D1 | Self-hosting 专章 | `docs/06-operations/self-hosting.md` | 含反代「何时需要」一节（同上表） |
| D2 | README 自托管入口 | 根 README | |
| D3 | Community 语义 | D1 | 自建 ≠ ma3.io |
| D4 | 支持声明 | README / D1 | **Best-effort，无 SLA** |
| D5 | 最小验收清单 | verify 脚本 | bootstrap 与 OIDC 两条路径 |

### E. 仓库卫生与安全基线

| ID | 项 | 产出 | 备注 |
|----|----|------|------|
| E1 | 清内网 IP / 主机样例 | 文档与 sample | |
| E2 | `SECURITY.md` | 根目录 | |
| E3 | secrets gitignore 复查 | | |
| E4 | 默认网络暴露策略 | compose + 文档 | 默认可 LAN 直连；文档警告公网务必 TLS/反代或防火墙；**不把反代做成硬依赖** |

---

## P1 — 开源后第一波

| ID | 项 | 说明 |
|----|----|------|
| F2 | 备份 / 恢复一页纸 | `pg_dump` / volumes |
| F3 | 升级指南 | server + migrate + Scheme B client |
| F4 | systemd 示例 | 无 Docker 用户 |
| F5 | CONTRIBUTING + Issue 模板 | 环境指纹含 auth 模式（bootstrap / oidc） |
| F6 | 商标说明 | |
| F7 | SQLite 定位 | 仅开发或移出自托管主文档 |
| F8 | OIDC 兼容矩阵 | Keycloak / Authentik / Authing / Google 抽测记录 |

---

## P2 — 可后置

| ID | 项 |
|----|----|
| G1 | 联邦 / 镜像官方 Community |
| G2 | Helm / K8s |
| G3 | HA |
| G4 | 可插拔嵌入模型 |
| G5 | 自托管「关闭配额」产品化 |

---

## 建议实施顺序（按已拍板调整）

```text
迭代 1 — 可宣布「实验性自托管」
  B1–B3（OIDC 抽象骨架 + bootstrap 默认）
  A1–A5、C1–C4（Compose + embeddings on）
  D1–D5、E1–E4
  A6 可选示例反代配置

迭代 2 — 「推荐自托管」
  B2/B5 打磨多 IdP
  F2–F5、F8

迭代 3
  F6/F7、G* 按需
```

---

## 明确不做（写进自托管文档）

- 自建实例自动接入 ma3.io 公共知识  
- 账号与官方实例互通  
- 社区支持 SLA  
- 把内部 `deploy/deploy.sh`（SSH 推你们机器）当成社区主路径——对外主推 Compose  

---

## 决策状态

| # | 状态 |
|---|------|
| 1 Auth / OIDC / bootstrap | **已拍板** |
| 2 Embeddings 默认开 | **已拍板** |
| 3 反代 | **已拍板**：非硬性；公网/OIDC 推荐（见上文） |
| 4 无 SLA | **已拍板** |

下一步：按迭代 1 开 issue 或直接开工（建议先 B1 ADR + bootstrap 命令，再 Compose）。
