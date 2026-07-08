# ma3 部署与验收

## 原则（强制）

**部署完成后，执行方必须先自行跑完验收清单，全部通过后再向用户汇报。**  
不得在未验证的情况下声称「已部署完成」。

验收失败时：修复 → 重新部署 → **重新跑完整清单** → 再汇报（附简要结果摘要）。

---

## 通用部署脚本 + 本地环境配置

只有**一份通用脚本** `deploy/deploy.sh` 进 git；各环境的具体配置放在**本地、不进 git**的
`*.env` 文件里（真实主机/路径/实例名）。仓库只提交模板 `deploy/deploy.env.sample`。

```
deploy/
├── deploy.sh            # 通用部署驱动（进 git）
├── deploy.env.sample    # 配置模板（进 git）
├── common/verify_ma3.sh # 共享验收，按 MA3_* 变量参数化（进 git）
├── README.md            # 本文（进 git）
├── .gitignore           # 忽略本地 *.env 与遗留脚本
├── deploy.202.env       # 本地：LAN 202 配置（不进 git）
└── deploy.ma3.io.env    # 本地：ma3.io 生产配置（不进 git）
```

用法：

```bash
./deploy/deploy.sh deploy/deploy.202.env       # 部署到 LAN 202
./deploy/deploy.sh deploy/deploy.ma3.io.env    # 部署到 ma3.io 生产
# 或： DEPLOY_CONFIG=deploy/deploy.202.env ./deploy/deploy.sh
```

新环境：复制 `deploy.env.sample` 为本地 `deploy.<name>.env`，填值即可。

### 两种模式（配置里的 `ENV_MODE`）

| | `regenerate`（LAN/dev，如 202） | `preserve`（生产，如 ma3.io） |
|---|---|---|
| 远端 `ma3.env` | 从 `LEGACY_ENV_FILE` + 配置**重新生成**（实例名、public base、dev auth） | **保留远端 env**，只注入 `MA3_GIT_COMMIT` |
| dev 后门 | `DEV_AUTH` 可设 `1`（LAN 可用 `ma3dev`） | 启动前断言 `MA3_DEV_AUTH≠1`，否则中止 |
| legacy 回填 | `RUN_MIGRATION=1` 跑 backfill | 不迁移 |
| uvicorn bind | `0.0.0.0`（直连 LAN） | `127.0.0.1`（Caddy 反代 443） |
| 验收 | `common/verify_ma3.sh`（含 pytest，用 `ma3dev`） | 内联生产 smoke（dev_auth off、`ma3dev` 被拒、Authing 回调、tools/list） |

### 防串环境的护栏

- **主机守卫 `ALLOWED_HOSTS`**：`REMOTE_HOST` 不在允许列表就 `exit 2`。202 配置永远无法推到 ma3.io。
- **preserve 模式保留远端 `ma3.env`**：rsync `--exclude ma3.env`，脚本不 source 任何 legacy env、
  不重写 env，只 `sed` 更新 `MA3_GIT_COMMIT`——这堵住了历史上把 202 配置写进 ma3.io 的根因
  （公网开 dev 后门、`public_base_url` 指向内网、内网代理搞坏 Authing）。
- **preserve 模式启动前断言**：`MA3_DEV_AUTH≠1`、`MA3_INSTANCE_ID`、`MA3_PUBLIC_BASE_URL`、无 LAN 代理变量。

### 环境变量文件（202 运行时）

| 文件 | 用途 |
|------|------|
| `/home/hct/ma3/ma3.env` | Postgres、Authing、HF 缓存路径（`regenerate` 的 `LEGACY_ENV_FILE`） |
| `/home/hct/ma3_deploy/ma3.env` | v1 运行时（由 `deploy.sh` 在 `regenerate` 模式生成） |

生产 `ma3.io` 的 `ma3.env` 由人工维护、含 secret，不进 git，由 `preserve` 模式保留不动。

---

## 部署后验收（共享脚本）

`deploy/common/verify_ma3.sh` 按环境变量参数化，`deploy.sh` 的 `regenerate` 模式会自动调用它；
也可手动跑：

```bash
export MA3_BASE_URL=http://127.0.0.1:8000   # 远端本机
export MA3_API_KEY=ma3dev                    # 仅 dev_auth=1 的环境（如 202）
export MA3_EXPECT_INSTANCE_ID=ma3-v1-202     # ma3.io 用 ma3-v1-hk
export MA3_EXPECT_ROOT_REDIRECT=/ui/me/      # ma3.io 落地页用 /ui/home/
export MA3_READY_TIMEOUT=180
bash deploy/common/verify_ma3.sh
```

`verify_ma3.sh` 会：

1. 等待 `/healthz` 就绪
2. UI/Auth smoke（根跳转、Observatory/Keys 门禁、manifest、MCP tools/list）
3. `tests/integration/test_deploy_verification.py` 等（MCP、doctor、搜索、client 升级、门户页）

### 部署后 inventory（regenerate 模式自动）

1. **部署前** — `scripts/db_inventory.py` 快照
2. **部署中** — `MA3_MIGRATE_BACKFILL=1` 将 `legacy_records` upsert 进 v1 `records`
3. **部署后** — 再次 inventory，断言 v1 未减少
4. **pytest 门槛** — `MA3_EXPECT_MIN_RECORDS` 取自 post-deploy 实际 `v1_records`

### 手动补充（可选）

| 检查项 | 命令/预期 |
|--------|-----------|
| vector 已启用 | `curl -s $MA3_BASE_URL/healthz \| jq .features` 含 `"vector"` |
| 登录直跳 Authing | `curl -sI $MA3_BASE_URL/auth/login` → `302`，`Location` 含 `authing.cn` |
| 未登录门禁 | `/ui/observatory/`、`/ui/keys/` → `302` → `/auth/login` |
| Authing 浏览器登录 + Key 创建 | `code/server/scripts/e2e_authing_ui.py`（需 `AUTHING_TEST_USER/PASS`） |

### 已知可忽略项

- `test_deploy_database_migration_state`：DB 已迁移且 `legacy_records` 表不存在时会失败；不影响线上。

---

## 向用户汇报模板

```
已部署到 <目标 URL>（skill x.x.x, commit xxxxxxx）

验收：
- healthz OK，features: [...]（生产不含 dev_auth）
- MCP 13 tools，ma3_context/whoami/doctor 正常
- 登录 /auth/login → Authing；Observatory/Keys 未登录 302
- [若测了] 浏览器 Authing 登录 → Observatory 正常

备注：（如有已知限制或未测项，明确写出）
```

---

## 相关脚本

| 脚本 | 状态 | 说明 |
|------|------|------|
| `deploy/deploy.sh` | git | 通用部署驱动（config 决定环境与模式） |
| `deploy/deploy.env.sample` | git | 配置模板 |
| `deploy/common/verify_ma3.sh` | git | 部署后自动化验收（**部署方必须跑**） |
| `deploy/deploy.*.env` | 本地 | 各环境真实配置（不进 git） |
| `code/eval/scenarios/agent-client-sync/scripts/restart_host_ma3.sh` | git | 仅重启（skill 版本升级测试） |
| `code/server/scripts/e2e_authing_ui.py` | git | 浏览器级 Authing 登录/退出 E2E |
