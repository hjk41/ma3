# 部署总览

> Authing 详细步骤：[deployment-authing.md](deployment-authing.md)

## 部署 Profile

| Profile | 用途 | Auth | 数据库 |
|---------|------|------|--------|
| **profile-saas** | 公网 SaaS / staging **首要** | OIDC（如 Authing）+ API Key | PostgreSQL |
| **profile-lan** | dev / 内网 staging（自选 LAN 主机） | 可选 `MA3_DEV_AUTH=1`（仅限内网） | Postgres 或 SQLite |
| **profile-selfhost** | 社区自托管（Docker Compose） | bootstrap key / 本地账号 / 可选 OIDC | PostgreSQL（compose 内置） |
| profile-ltp | legacy | — | 非 v1 core |

**同一 binary**；通过环境变量切换 profile 行为。文档不绑定具体主机——
LAN staging 主机由维护者在本地 deploy env 文件（不进 git）中配置。

## 必备环境变量（SaaS）

```bash
# 数据库
MA3_DATABASE_URL=postgresql://...

# OIDC（推荐 MA3_OIDC_*；Authing 可用 MA3_AUTHING_* 别名）
MA3_OIDC_ENABLED=1
MA3_OIDC_ISSUER=...
MA3_OIDC_CLIENT_ID=...
MA3_OIDC_CLIENT_SECRET=...
MA3_PUBLIC_BASE_URL=https://...

# 管理员（OIDC 开启时非空，否则拒绝启动）
MA3_AUTH_ADMIN_USERS=admin@example.com

# 搜索（默认开 vector）
# MA3_DISABLE_EMBEDDINGS=1

# HF 缓存（生产 offline）
HF_HUB_OFFLINE=1
HF_HOME=/path/to/hf
```

## 社区自托管（Compose）

见 **[self-hosting.md](self-hosting.md)** 与仓库 `deploy/self-host/`（bootstrap key / 可选 OIDC）。

## 目录与数据

- 运行时 `data/` **不可** rsync `--delete`
- prewarm embedding → `HF_HOME/hub/`
- deploy bundle 含 `server/scripts/`（seed 兜底）

## 健康检查

```bash
curl -s "$BASE/healthz"
curl -s "$BASE/doctor"   # 或 MCP ma3_doctor
```

## 部署后验收（强制）

每次线上部署（`ENV_MODE=preserve`）必须按 **[deploy/README.md](../../deploy/README.md)** 的标准流程验收：

1. `./deploy/deploy.sh deploy/deploy.<prod>.env`（本地配置文件，不进 git；自动含远端 smoke + 公网 `verify_ma3_prod.sh`）
2. 或单独：`MA3_BASE_URL=$MA3_BASE_URL bash deploy/common/verify_ma3_prod.sh`（对生产公网 URL）

清单摘要：healthz / UI·Auth / client bundle / 匿名 MCP 拒绝 / `ma3dev` 拒绝 / pytest。  
未设 `VERIFY_API_KEY` 时跳过需 API key 的 MCP 测例，汇报时须注明。

LAN（`regenerate`）用 `deploy/common/verify_ma3.sh`，勿与生产清单混用。

## Caddy 蓝绿（SaaS preserve，可选）

裸机 + Caddy（非 Compose 自托管）接近零停机：在线上 Caddyfile 已 `import` `deploy/caddy/upstream.caddy.example` 后，于本地 prod deploy env 设 `BLUE_GREEN=1`（见 `deploy/caddy/Caddyfile.ma3.io.example` 与 **[deploy/README.md](../../deploy/README.md)**）。一次性接线完成前，继续走经典 `pkill` 重启。

## 待补充

- [x] `deploy/self-host` docker compose 示例（见 [self-hosting.md](self-hosting.md)）
- [ ] systemd 示例
- [x] 密钥管理（`MA3_API_KEY_ENCRYPTION_SECRET`、bootstrap key 文件）
- [ ] 备份恢复 procedure（摘要已写入 self-hosting.md）
- [x] Caddy 蓝绿切换（`deploy/common/bluegreen_remote.sh`，`BLUE_GREEN=1` 可选开启）
