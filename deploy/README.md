# ma3 部署与验收

## 原则（强制）

**部署完成后，执行方必须先自行跑完验收清单，全部通过后再向用户汇报。**  
不得在未验证的情况下声称「已部署完成」。

验收失败时：修复 → 重新部署 → **重新跑完整清单** → 再汇报（附简要结果摘要）。

---

## 标准流程（每次线上部署）

生产（`ENV_MODE=preserve`，如 ma3.io）固定走下面这条路径；以后每次部署都按此执行。

```bash
# 1. 部署（自动：rsync → 断言 ma3.env → 重启 → 远端 loopback smoke → 公网验收）
./deploy/deploy.sh deploy/deploy.ma3.io.env

# 2. 若自动验收未跑通，或只想复跑验收（不重新部署）：
export MA3_BASE_URL=https://ma3.io
export MA3_EXPECT_INSTANCE_ID=ma3-v1-hk
export MA3_EXPECT_PUBLIC_BASE_URL=https://ma3.io
# 推荐：填生产只读/运维 API key，解锁 doctor / context / whoami 等 MCP 测例
# export MA3_API_KEY=ma3k_...   # 或在 deploy.ma3.io.env 设 VERIFY_API_KEY=
bash deploy/common/verify_ma3_prod.sh
```

`deploy.sh` preserve 路径在远端 loopback smoke 通过后，会**自动**在本机对公网 URL 调用 `verify_ma3_prod.sh`。

### 生产验收清单（`verify_ma3_prod.sh`）

| # | 检查 | 通过标准 |
|---|------|----------|
| 1 | `/healthz` | `status=ok`；`instance_id` / `public_base_url` 与配置一致；含 `vector`；**无** `dev_auth` |
| 2 | UI / Auth | `/ui/home/` → 200；`/ui/me/`、`/ui/observatory/`、`/ui/keys/` → 302；`/auth/login` → 302 到 Authing/OIDC |
| 3 | Client bundle | `/client/manifest.json`、`agent-onboarding.md`、policy/env 模板、sync 脚本、`mcp-tools.json` 均为 200 且非空 |
| 4 | MCP 匿名与发现 | `tools/list` ≥ 13；匿名 `ma3_whoami` 的 `readable_library_ids=[]`；匿名 `ma3_context` → `-32001 authentication required`；`X-API-Key: ma3dev` → 拒绝 |
| 5 | pytest | 必跑：`healthz`、`client_bundle`（OIDC off 时另测友好登录页）；设了 `MA3_API_KEY` 时再跑完整 deploy 套件（含匿名拒绝 + doctor/context） |
| 6 | 汇报 | 见下方模板；未测项（如缺 API key）必须写明 |

LAN / regenerate（内网 staging）仍用 `deploy/common/verify_ma3.sh`（可用 `ma3dev`），不要与生产清单混用。

---

## 通用部署脚本 + 本地环境配置

只有**一份通用脚本** `deploy/deploy.sh` 进 git；各环境的具体配置放在**本地、不进 git**的
`*.env` 文件里（真实主机/路径/实例名）。仓库只提交模板 `deploy/deploy.env.sample`。

```
deploy/
├── deploy.sh                 # 通用部署驱动（进 git）
├── deploy.env.sample         # 配置模板（进 git）
├── common/verify_ma3.sh      # LAN/regenerate 验收（进 git）
├── common/verify_ma3_prod.sh # 生产/公网验收（进 git）——每次线上部署必跑
├── README.md                 # 本文（进 git）
├── .gitignore                # 忽略本地 *.env 与遗留脚本
├── deploy.<lan>.env          # 本地：LAN staging（不进 git）
└── deploy.<prod>.env         # 本地：生产（不进 git）
```

用法：

```bash
./deploy/deploy.sh deploy/deploy.<lan>.env     # 部署到 LAN staging
./deploy/deploy.sh deploy/deploy.<prod>.env    # 部署到生产
# 或： DEPLOY_CONFIG=deploy/deploy.<lan>.env ./deploy/deploy.sh
```

新环境：复制 `deploy.env.sample` 为本地 `deploy.<name>.env`，填值即可。

### 两种模式（配置里的 `ENV_MODE`）

| | `regenerate`（LAN/dev staging） | `preserve`（生产，如 ma3.io） |
|---|---|---|
| 远端 `ma3.env` | 从 `LEGACY_ENV_FILE` + 配置**重新生成** | **保留远端 env**，只注入 `MA3_GIT_COMMIT` |
| dev 后门 | `DEV_AUTH` 可设 `1`（LAN 可用 `ma3dev`） | 启动前断言 `MA3_DEV_AUTH≠1`，否则中止 |
| legacy 回填 | `RUN_MIGRATION=1` 跑 backfill | 不迁移 |
| uvicorn bind | `0.0.0.0`（直连 LAN） | `127.0.0.1`（Caddy 反代 443） |
| 验收 | `common/verify_ma3.sh`（含 pytest，常用 `ma3dev`） | 远端 loopback smoke + **`common/verify_ma3_prod.sh`（公网 URL）** |

### 防串环境的护栏

- **主机守卫 `ALLOWED_HOSTS`**：`REMOTE_HOST` 不在允许列表就 `exit 2`。LAN 配置永远无法推到生产。
- **preserve 模式保留远端 `ma3.env`**：rsync `--exclude ma3.env`，脚本不 source 任何 legacy env、
  不重写 env，只 `sed` 更新 `MA3_GIT_COMMIT`。
- **preserve 模式启动前断言**：`MA3_DEV_AUTH≠1`、`MA3_INSTANCE_ID`、`MA3_PUBLIC_BASE_URL`、无 LAN 代理变量。

### 环境变量文件（LAN staging 运行时）

| 文件 | 用途 |
|------|------|
| `<LEGACY_ENV_FILE>`（如 `~/ma3/ma3.env`） | Postgres、OIDC、HF 缓存路径（`regenerate` 的 `LEGACY_ENV_FILE`） |
| `<DEPLOY_DIR>/ma3.env`（如 `~/ma3_deploy/ma3.env`） | v1 运行时（由 `deploy.sh` 在 `regenerate` 模式生成） |

生产 `ma3.io` 的 `ma3.env` 由人工维护、含 secret，不进 git，由 `preserve` 模式保留不动。

---

## LAN 验收（`verify_ma3.sh`）

`deploy.sh` 的 `regenerate` 模式会自动调用；也可手动：

```bash
export MA3_BASE_URL=http://127.0.0.1:8000
export MA3_API_KEY=ma3dev
export MA3_EXPECT_INSTANCE_ID=<your-instance-id>   # 与 WRITE_INSTANCE_ID 一致
export MA3_EXPECT_ROOT_REDIRECT=/ui/me/
export MA3_READY_TIMEOUT=180
bash deploy/common/verify_ma3.sh
```

### 部署后 inventory（regenerate 模式自动）

1. **部署前** — `scripts/db_inventory.py` 快照  
2. **部署中** — `MA3_MIGRATE_BACKFILL=1` 将 `legacy_records` upsert 进 v1 `records`  
3. **部署后** — 再次 inventory，断言 v1 未减少  
4. **pytest 门槛** — `MA3_EXPECT_MIN_RECORDS` 取自 post-deploy 实际 `v1_records`

### 手动补充（可选）

| 检查项 | 命令/预期 |
|--------|-----------|
| 浏览器 Authing 登录 + Key 创建 | `code/server/scripts/e2e_authing_ui.py`（需 `AUTHING_TEST_USER/PASS`） |

### 已知可忽略项

- `test_deploy_database_migration_state`：DB 已迁移且 `legacy_records` 表不存在时会失败；不影响线上。

---

## 向用户汇报模板

生产部署通过后使用：

```
已部署到 https://ma3.io（commit <shortsha>，instance ma3-v1-hk）

验收（verify_ma3_prod.sh）：
- healthz OK：features 含 vector/oidc，无 dev_auth；public_base_url=https://ma3.io
- UI：home 200；me/observatory/keys 未登录 302；/auth/login → Authing
- client bundle：onboarding + manifest + sync 脚本 200
- MCP：tools/list≥13；匿名 context 拒绝；ma3dev 拒绝
- pytest：healthz + client_bundle [+ authed MCP，若设了 VERIFY_API_KEY]

备注：（未测项写清楚，例如「未设 VERIFY_API_KEY，跳过 doctor/context」）
```

---

## 相关脚本

| 脚本 | 状态 | 说明 |
|------|------|------|
| `deploy/deploy.sh` | git | 通用部署驱动 |
| `deploy/deploy.env.sample` | git | 配置模板 |
| `deploy/common/verify_ma3_prod.sh` | git | **生产公网验收（每次线上必跑）** |
| `deploy/common/verify_ma3.sh` | git | LAN / regenerate 验收 |
| `deploy/deploy.*.env` | 本地 | 各环境真实配置（不进 git） |
| `code/server/scripts/e2e_authing_ui.py` | git | 浏览器级 Authing 登录/退出 E2E |
