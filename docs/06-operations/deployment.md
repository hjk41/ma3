# 部署总览

> Authing 详细步骤：[deployment-authing.md](deployment-authing.md)

## 部署 Profile

| Profile | 用途 | Auth | 数据库 |
|---------|------|------|--------|
| **profile-saas** | 公网 / staging **首要** | Authing OIDC + API Key | PostgreSQL |
| **profile-lan** | dev / 192.168.31.202 | 可选 `MA3_DEV_AUTH=1` | Postgres 或 SQLite |
| profile-ltp | legacy | — | 非 v1 core |

**同一 binary**；通过环境变量切换 profile 行为。

## 必备环境变量（SaaS）

```bash
# 数据库
MA3_DATABASE_URL=postgresql://...

# Authing（见 deployment-authing.md）
MA3_AUTHING_ENABLED=1
MA3_AUTHING_ISSUER=...
MA3_AUTHING_APP_ID=...
MA3_AUTHING_APP_SECRET=...
MA3_PUBLIC_BASE_URL=https://...

# 管理员（非空，否则拒绝启动）
MA3_AUTH_ADMIN_USERS=admin@example.com

# 搜索（默认开 vector）
# MA3_DISABLE_EMBEDDINGS=1

# HF 缓存（生产 offline）
HF_HUB_OFFLINE=1
HF_HOME=/path/to/hf
```

## 目录与数据

- 运行时 `data/` **不可** rsync `--delete`
- prewarm embedding → `HF_HOME/hub/`
- deploy bundle 含 `server/scripts/`（seed 兜底）

## 健康检查

```bash
curl -s "$BASE/healthz"
curl -s "$BASE/doctor"   # 或 MCP ma3_doctor
```

## 待补充

- [ ] `profile-saas.md` / `profile-lan.md` 完整 runbook
- [ ] systemd / docker compose 示例
- [ ] 密钥管理（MA3_AUTHING_APP_SECRET、Fernet key for key_ciphertext）
- [ ] 备份恢复 procedure
