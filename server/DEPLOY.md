# ma3 部署指南

本文件面向部署 ma3 的 agent 或运维人员。代码库本身不修改，但部署时
必须完成下面的配置步骤，否则 `agents.md` 里指向的 Base URL 仍是默认
值 `https://hjk41.cc`，接入该实例的 agent 会被引导到错误的服务器。

---

## 必做：替换 agents.md 中的 Base URL

`server/app/docs/agents.md` 第 27 行写有：

```
Default: `https://hjk41.cc`
```

部署到新实例后，用实际的服务地址替换它。示例（将 URL 改为
`http://10.100.193.54:8000`）：

```bash
sed -i 's|https://hjk41.cc|http://10.100.193.54:8000|g' \
    /root/ma3/server/app/docs/agents.md
```

同时更新 `server/app/docs/agents.md` 最后的 Interaction Contract 部分，
把示例里的公网地址也一并替换，让 agent 读到的例句和实际地址一致。

上面一条 `sed -i ... -g` 已经覆盖了文件内所有出现位置，无需单独处理。

验证替换结果：

```bash
grep 'hjk41.cc' /root/ma3/server/app/docs/agents.md
# 期望：无输出（即没有残留旧地址）
```

---

## 参考：完整生产部署流程

以下步骤基于本组 LTP 集群机器的实际限制（Docker 容器内，无 DinD，无
systemd PID 1，无外部网络）。公网或其他环境可按实际情况调整。

### 前提

| 项目 | 说明 |
|------|------|
| OS | Ubuntu 22.04 / 24.04 |
| Python | 3.10+ |
| 进程守护 | supervisord（无 systemd 时使用） |
| 数据库 | 原生 PostgreSQL 16（无 Docker） |
| HF 模型 | 离线缓存（无外网时加 `HF_HUB_OFFLINE=1`） |
| SSH 私钥 | `~/.ssh/id_rsa` |

### 步骤

#### 1. 安装系统依赖

```bash
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    postgresql postgresql-client supervisor cron
```

#### 2. 启动 PostgreSQL

```bash
pg_ctlcluster 16 main start
pg_isready
```

#### 3. 创建数据库与用户

```bash
su -c "psql -c \"CREATE DATABASE ma3db;\""          postgres
su -c "psql -c \"CREATE USER ma3user WITH PASSWORD 'ma3pass';\""  postgres
su -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE ma3db TO ma3user;\""  postgres
su -c "psql -d ma3db -c \"GRANT ALL ON SCHEMA public TO ma3user;\""  postgres
```

#### 4. 同步代码

```bash
rsync -az \
  --exclude='.venv' --exclude='__pycache__' \
  --exclude='*.pyc' --exclude='.tmp_http_tests' \
  -e "ssh -i ~/.ssh/id_rsa -p <PORT>" \
  /root/ma3/ root@<HOST>:/root/ma3/
```

#### 5. 替换 agents.md Base URL（必做）

```bash
DEPLOY_URL="http://<HOST>:<PORT>"
sed -i "s|https://hjk41.cc|${DEPLOY_URL}|g" \
    /root/ma3/server/app/docs/agents.md

# 验证
grep 'hjk41.cc' /root/ma3/server/app/docs/agents.md && echo 'ERROR: 仍有残留' || echo 'OK'
```

#### 6. 创建虚拟环境

```bash
python3 -m venv /root/ma3/.venv
/root/ma3/.venv/bin/pip install -r /root/ma3/server/requirements.txt
```

#### 7. 生成 Admin Key

```bash
openssl rand -hex 24
# 记录输出，用于步骤 8
```

#### 8. 写 supervisor 配置

```ini
# /etc/supervisor/conf.d/ma3.conf
[program:ma3]
command=/root/ma3/.venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
directory=/root/ma3/server
user=root
autostart=true
autorestart=true
startretries=5
stdout_logfile=/var/log/ma3/ma3.log
stderr_logfile=/var/log/ma3/ma3.log
stdout_logfile_maxbytes=20MB
stdout_logfile_backups=3
environment=MA3_DATABASE_URL="postgresql://ma3user:ma3pass@localhost:5432/ma3db",MA3_API_KEY="<ADMIN_KEY>",HF_HUB_OFFLINE="1"
```

`HF_HUB_OFFLINE=1`：服务器无外网时必须设，否则 sentence-transformers
会在搜索时尝试联网检查模型版本，导致 500 错误（模型需预先缓存在
`~/.cache/huggingface/hub/`）。

#### 9. 启动服务

```bash
mkdir -p /var/log/ma3
supervisord -c /etc/supervisor/supervisord.conf
sleep 3
supervisorctl -c /etc/supervisor/supervisord.conf status
curl -sf http://localhost:8000/healthz
```

#### 10. 配置每日备份（可选）

```bash
# 写备份脚本
cat > /root/ma3-backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR=/mnt/3fs/data/chuntao.hong/ma3_postgres_backup
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p ${BACKUP_DIR}
PGPASSWORD=ma3pass pg_dump -U ma3user -h localhost ma3db \
    | gzip > ${BACKUP_DIR}/ma3db_${TIMESTAMP}.sql.gz
ls -t ${BACKUP_DIR}/ma3db_*.sql.gz | tail -n +31 | xargs -r rm -f
EOF
chmod +x /root/ma3-backup.sh

# 添加 crontab（凌晨 3 点）
(crontab -l 2>/dev/null; echo '0 3 * * * /root/ma3-backup.sh >> /var/log/ma3/backup.log 2>&1') | crontab -
/usr/sbin/cron
```

#### 11. 配置容器重启自动恢复（PAI 环境）

适用于 OpenPAI Docker 容器（PID 1 为 `/usr/local/pai/runtime`，无
systemd）：

```bash
# 写启动脚本
cat > /root/ma3-startup.sh << 'EOF'
#!/bin/bash
pg_isready -q 2>/dev/null || pg_ctlcluster 16 main start
pg_isready -q -t 15 || exit 1
supervisorctl -c /etc/supervisor/supervisord.conf status >/dev/null 2>&1 \
    || supervisord -c /etc/supervisor/supervisord.conf
pgrep -x cron >/dev/null || /usr/sbin/cron
sleep 3
supervisorctl -c /etc/supervisor/supervisord.conf status
curl -sf http://localhost:8000/healthz | python3 -m json.tool
EOF
chmod +x /root/ma3-startup.sh

# 注入 user.sh（只执行一次）
if ! grep -q 'ma3-startup' /usr/local/pai/runtime.d/user.sh; then
    cp /usr/local/pai/runtime.d/user.sh /usr/local/pai/runtime.d/user.sh.bak
    awk '/^sleep infinity/{
        print "bash /root/ma3-startup.sh >> /var/log/ma3/startup.log 2>&1 || true"
        print ""
    }1' /usr/local/pai/runtime.d/user.sh.bak \
        > /usr/local/pai/runtime.d/user.sh
fi
```

有 systemd 的机器改用 systemd service 即可，无需上述 hack。

#### 12. 验证

```bash
curl http://localhost:8000/healthz
curl http://localhost:8000/agents.md | grep 'Default:'   # 确认 URL 已替换
```

---

## 升级（代码变更后）

```bash
# 1. 同步代码
rsync -az --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='.tmp_http_tests' \
  -e "ssh -i ~/.ssh/id_rsa -p <PORT>" \
  /root/ma3/ root@<HOST>:/root/ma3/

# 2. 替换 agents.md URL（rsync 会覆盖为源码默认值，每次升级后必须重新替换）
ssh -i ~/.ssh/id_rsa -p <PORT> root@<HOST> \
  "sed -i 's|https://hjk41.cc|http://<HOST>:<PORT>|g' /root/ma3/server/app/docs/agents.md"

# 3. 重启 ma3 进程
ssh -i ~/.ssh/id_rsa -p <PORT> root@<HOST> \
  "supervisorctl -c /etc/supervisor/supervisord.conf restart ma3"

# 4. 确认
ssh -i ~/.ssh/id_rsa -p <PORT> root@<HOST> \
  "curl -sf http://localhost:8000/healthz && curl -sf http://localhost:8000/agents.md | grep 'Default:'"
```

> **注意**：每次 rsync 都会把 `app/docs/agents.md` 重置为代码库里的默认版本
> （含 `https://hjk41.cc`），因此步骤 2 的 URL 替换在每次升级后都必须重跑。

---

## 坑点速查

| 坑 | 现象 | 解法 |
|----|------|------|
| agents.md URL 未替换 | agent 接入后被引导到 hjk41.cc | `sed -i 's\|hjk41.cc\|<实际地址>\|g' server/app/docs/agents.md` |
| 无 systemd / DinD | pg/supervisor 不自动启动 | 手动启动 + user.sh hook |
| HuggingFace 无法联网 | `POST /search` 返回 500 | supervisor 配置加 `HF_HUB_OFFLINE=1` |
| ingest 返回 401 | 服务端设了 `MA3_API_KEY` | 请求头加 `X-API-Key: <key>` |
| healthz `service` 断言 | `service == "ma3"` 失败 | 改为 `"ma3" in service`（值为"马妈妈 (ma3)"） |
