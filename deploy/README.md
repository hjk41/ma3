# ma3 部署与验收

## 原则（强制）

**部署完成后，执行方必须先自行跑完验收清单，全部通过后再向用户汇报。**  
不得在未验证的情况下声称「已部署完成」。

验收失败时：修复 → 重新部署 → **重新跑完整清单** → 再汇报（附简要结果摘要）。

---

## 202 主机快速部署

```bash
# 从开发机同步并部署
./deploy/deploy_ma3_v1_202.sh
```

部署脚本会在远端启动 uvicorn 并调用 `deploy/verify_ma3_v1.sh`。

### 环境变量（202）

| 文件 | 用途 |
|------|------|
| `/home/hct/ma3/ma3.env` | Postgres、Authing、HF 缓存路径 |
| `/home/hct/ma3_deploy/ma3.env` | v1 运行时（`HF_HOME`、`MA3_DEV_AUTH` 等） |

**重启时必须同时 source 两个文件：**

```bash
set -a
source /home/hct/ma3/ma3.env
source /home/hct/ma3_deploy/ma3.env
set +a
export MA3_SKILL_VERSION=1.5.1
cd /home/hct/ma3_deploy/code/server
# embedding 启用时：启动会先加载模型，healthz 可能 1–3 分钟才就绪
nohup .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir . \
  >> /tmp/ma3-v1-uvicorn.log 2>&1 &
```

**不要**在 `ma3.env` 中设置 `MA3_DISABLE_EMBEDDINGS=1`（除非刻意关闭 vector 搜索）。  
确保 `HF_HOME=/home/hct/ma3/data/hf-cache`（或 `MA3_HF_HOME`，代码会自动映射）。

---

## 部署后验收清单

在 **202 本机**或能访问 `192.168.31.202:8000` 的环境执行：

```bash
export MA3_BASE_URL=http://127.0.0.1:8000   # 远端本机
export MA3_API_KEY=ma3dev
export MA3_READY_TIMEOUT=180                  # embedding 冷启动需更长时间
bash deploy/verify_ma3_v1.sh
```

`verify_ma3_v1.sh` 会自动：

1. 等待 `/healthz` 就绪（默认最多 180s）
2. 跑 `tests/integration/test_deploy_verification.py`（MCP、doctor、搜索、client 升级等）
3. 跑 UI/Auth smoke（登录跳转、Observatory/Keys 门禁、manifest、MCP tools/list）

### 部署后 inventory（自动）

`deploy_ma3_v1_202.sh` 会：

1. **部署前** — `scripts/db_inventory.py` 快照（v1 + legacy 计数、`legacy_importable`）
2. **部署中** — `MA3_MIGRATE_BACKFILL=1` 将 `legacy_records` upsert 进 v1 `records`
3. **部署后** — 再次 inventory，断言 v1 未减少且 legacy 可导入条数已并入
4. **pytest 门槛** — `MA3_EXPECT_MIN_RECORDS` 取自 post-deploy 实际 `v1_records`（不再硬编码 30）

手动：

```bash
cd code/server
export MA3_DATABASE_URL=postgresql://...
.venv/bin/python scripts/db_inventory.py -o /tmp/pre.json
MA3_MIGRATE_BACKFILL=1 MA3_DISABLE_EMBEDDINGS=1 .venv/bin/python scripts/migrate_legacy_pg.py
.venv/bin/python scripts/db_inventory.py --compare /tmp/pre.json --backfill /tmp/backfill.json
```

### 手动补充（可选）

| 检查项 | 命令/预期 |
|--------|-----------|
| vector 已启用 | `curl -s $MA3_BASE_URL/healthz \| jq .features` 含 `"vector"` |
| 登录直跳 Authing | `curl -sI $MA3_BASE_URL/auth/login` → `302`，`Location` 含 `authing.cn` |
| 未登录门禁 | `/ui/observatory/`、`/ui/keys/` → `302` → `/auth/login` |
| Authing 浏览器登录 + Key 创建 | 运行 `code/server/scripts/e2e_authing_ui.py`（需 `AUTHING_TEST_USER/PASS`）；`verify_ma3_v1.sh` 在变量已设置时会自动跑 |

### 已知可忽略项

- `test_deploy_database_migration_state`：若 DB 已完成迁移且 `legacy_records` 表已不存在，该用例会失败；不影响线上功能。全新迁移环境才需此表存在。

---

## 向用户汇报模板

```
已部署到 http://192.168.31.202:8000（skill x.x.x）

验收：
- healthz OK，features: [...]
- MCP 13 tools，ma3_context/whoami/doctor 正常
- 登录 /auth/login → Authing；Observatory/Keys 未登录 302
- [若测了] 浏览器 Authing 登录 → Observatory 正常

备注：（如有已知限制或未测项，明确写出）
```

---

## 相关脚本

| 脚本 | 说明 |
|------|------|
| `deploy/deploy_ma3_v1_202.sh` | rsync + 远端迁移 + 启动 + 验收 |
| `deploy/verify_ma3_v1.sh` | 部署后自动化验收（**部署方必须跑**） |
| `code/eval/scenarios/agent-client-sync/scripts/restart_host_ma3.sh` | 仅重启（skill 版本升级测试用） |
| `code/server/scripts/e2e_authing_ui.py` | 浏览器级 Authing 登录/退出 E2E |
