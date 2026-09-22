# ma3 部署与验收

## 原则（强制）

**部署完成后，执行方必须先自行跑完验收清单，全部通过后再向用户汇报。**  
不得在未验证的情况下声称「已部署完成」。

验收失败时：修复 → 重新部署 → **重新跑完整清单** → 再汇报（附简要结果摘要）。

---

## 标准流程（每次线上部署）

生产（`ENV_MODE=preserve`，如 ma3.io）固定走下面这条路径；以后每次部署都按此执行。

```bash
# 1. 部署（自动：服务器按精确 SHA 拉 Git → 断言 ma3.env → 蓝绿切换 → 验收）
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
├── caddy/                    # 蓝绿 Caddy 片段（进 git）
│   ├── upstream.caddy.example
│   └── Caddyfile.ma3.io.example
├── common/verify_ma3.sh      # LAN/regenerate 验收（进 git）
├── common/verify_ma3_prod.sh # 生产/公网验收（进 git）——每次线上部署必跑
├── common/bluegreen_remote.sh # Caddy 蓝绿切换（进 git）
├── common/prepare_git_release.sh # 远端 Git 缓存与不可变 release 准备
├── tests/test_prepare_git_release.sh # release 准备回归测试
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
| 代码来源 | 默认 `rsync` | 默认由服务器拉取**精确 commit** |
| uvicorn bind | `0.0.0.0`（直连 LAN） | `127.0.0.1`（Caddy 反代 443） |
| 重启 | `pkill` → 在 `MA3_PORT` 启动 | 默认相同；`BLUE_GREEN=1` 时 → 空闲端口 + Caddy upstream reload |
| 验收 | `common/verify_ma3.sh`（含 pytest，常用 `ma3dev`） | 远端 loopback smoke + **`common/verify_ma3_prod.sh`（公网 URL）** |

### 生产代码来源：服务器拉 Git release（preserve 强制路径）

控制端不再上传本机工作区。脚本把本地目标 commit 解析为完整 40 位 SHA，正常部署只通过
SSH 发送短命令参数。仅首次迁移会传一次小型准备脚本；首次成功后将它安装到
`$REMOTE_DIR/bin/prepare_git_release.sh`，供后续复用。服务器拉取配置的 Git ref，确认该 SHA 可从 ref 到达，
再解包为独立 release：

```text
$REMOTE_DIR/
├── ma3.env                    # 主机共享配置，不进 Git
├── data/                      # 共享运行态与蓝绿状态
├── bin/prepare_git_release.sh # 首次成功后安装的稳定 bootstrap helper
├── repo.git/                  # bare Git 拉取缓存
├── releases/<full-sha>/       # 不可变应用源码 + 该 release 的 .venv
├── current -> releases/<sha>  # 仅在切流成功后更新
└── previous -> releases/<sha> # 上一个成功版本（如存在）
```

生产配置必须包含：

```bash
DEPLOY_SOURCE=git
GIT_REPO_URL=https://github.com/YOUR_ORG/ma3.git
GIT_REF=refs/heads/main
# 仅私有仓库需要：
# GIT_DEPLOY_KEY=/root/.ssh/ma3_github_deploy
```

仓库访问配置：

1. 公共仓库直接使用匿名 `https://github.com/...git` URL，服务器不保存任何 GitHub 凭据。
2. 私有仓库才在服务器生成专用 SSH key，并把公钥添加为 GitHub 仓库的**只读 Deploy
   Key**；绝不复制开发者个人私钥。
3. 使用 SSH Git URL 时，在部署用户的 `known_hosts` 中固定 GitHub host key；部署强制
   `StrictHostKeyChecking=yes`。Deploy Key 放在 release 外并限制权限。

正常部署和回滚：

```bash
# 本地 HEAD 已 push 到 GIT_REF 后部署。
./deploy/deploy.sh deploy/deploy.ma3.io.env

# 回滚到仍可从 GIT_REF 到达的旧 commit。
DEPLOY_GIT_COMMIT=<本地可解析的旧-sha> \
  ./deploy/deploy.sh deploy/deploy.ma3.io.env
```

服务器会拒绝未拉到的 SHA、不属于 `GIT_REF` 的 SHA，以及 commit marker 不一致的复用
release。只有新进程健康且蓝绿切换成功后才移动 `current`。切流逻辑由已拉取 release 内的
`deploy_release_remote.sh` 执行，控制端不传应用代码，也不发送大段内联 shell。本机未提交
和未跟踪文件永远不会进入生产。

### Caddy 蓝绿（可选，仅 preserve）

默认 preserve 仍会短暂停旧进程再起新进程。若要在 Caddy 后接近零停机：

1. **主机一次性**：站点块 `import` upstream 片段（见 `deploy/caddy/Caddyfile.ma3.io.example`），必要时从 `deploy/caddy/upstream.caddy.example` 播种 `$REMOTE_DIR/data/bluegreen/upstream.caddy`。校验：`caddy validate --config /etc/caddy/Caddyfile`。
2. **在 `deploy.<prod>.env`**：设 `BLUE_GREEN=1`、`UVICORN_HOST=127.0.0.1`、端口 A/B、`CADDY_UPSTREAM_FILE`、`CADDY_RELOAD_CMD`。
3. **每次部署**：空闲端口起新 uvicorn → 等 `/healthz` → 改写 upstream → `caddy reload` → 公网 smoke（失败回滚 Caddy）→ drain → 停旧进程。状态：`$REMOTE_DIR/data/bluegreen/active_port`。

未部署时查看状态：

```bash
ssh user@host 'REMOTE_DIR=/opt/ma3_deploy CADDY_UPSTREAM_FILE=/opt/ma3_deploy/data/bluegreen/upstream.caddy bash /opt/ma3_deploy/current/deploy/common/bluegreen_remote.sh status'
```

**在线上 Caddyfile 已 import 该 upstream 文件之前，不要开 `BLUE_GREEN=1`**——否则 reload 不会切流量，停掉旧端口会直接断站。

### 防串环境的护栏

- **主机守卫 `ALLOWED_HOSTS`**：`REMOTE_HOST` 不在允许列表就 `exit 2`。LAN 配置永远无法推到生产。
- **preserve 的主机状态位于 release 外**：Git archive 只含代码；`ma3.env` 与 `data/` 留在
  `$REMOTE_DIR`，脚本通过不变式检查后只更新 `MA3_GIT_COMMIT`。
- **commit 护栏**：生产使用完整 SHA，并验证它可从 `GIT_REF` 到达；不执行浮动的 `git pull`。
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
| `deploy/common/prepare_git_release.sh` | git | 精确 SHA 远端拉取与 release 准备 |
| `deploy/common/deploy_release_remote.sh` | git | 远端不变式检查、进程启动与原子 release 激活 |
| `deploy/tests/test_prepare_git_release.sh` | git | Git release 完整性/可达性测试 |
| `deploy/tests/test_deploy_git_source.sh` | git | 部署驱动 bootstrap/复用测试 |
| `deploy/tests/test_deploy_release_remote.sh` | git | release marker 护栏测试 |
| `deploy/common/verify_ma3_prod.sh` | git | **生产公网验收（每次线上必跑）** |
| `deploy/common/verify_ma3.sh` | git | LAN / regenerate 验收 |
| `deploy/deploy.*.env` | 本地 | 各环境真实配置（不进 git） |
| `code/server/scripts/e2e_authing_ui.py` | git | 浏览器级 Authing 登录/退出 E2E |
