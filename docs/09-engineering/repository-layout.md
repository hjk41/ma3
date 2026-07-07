# 代码仓库布局

> **状态**：待补充 — 以下为 v1 目标结构摘要

## 顶层

```text
ma3/
├── code/
│   ├── server/          FastAPI：MCP、UI、auth、domain、search
│   └── client/          HTTP bundle：manifest、policy、sync 脚本
├── docs/                系统化文档（产品、架构、运维、验收）
├── data/                运行时数据（勿 rsync --delete）
└── ma3.env              本地 env（勿提交 secret）
```

**202 生产运行目录**（与源码 checkout `~/ma3` 分离）：`~/ma3_deploy/` — 由 `deploy/deploy_ma3_v1_202.sh` rsync 同步并在此启动 uvicorn。

## Server 模块（目标）

```text
code/server/app/
├── api/           routes_mcp, routes_portal, routes_keys, routes_auth, ui_theme
├── services/      mcp_tool, onboarding, api_key, entitlement, billing, write_audit
├── storage/       db, search, ranking
├── models/        mcp_payloads
└── core/          config, security
```

## Client 面

```text
code/client/
├── agent-onboarding.md
├── templates/ma3-agent-policy.mdc
├── scripts/sync_ma3_client.{sh,py}
└── lib/ma3_sync_core.py
```

## 测试

```text
code/server/tests/
├── unit/
└── integration/
```

## 待补充

- [ ] 各 service 职责一句话表
- [ ] 新功能应修改的文件 checklist 模板
- [ ] eval 与 server 关系说明
