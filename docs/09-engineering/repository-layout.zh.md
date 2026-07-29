# 代码仓库布局

> 结构变更时请随 PR 同步更新本文件。真源以仓库实际目录为准。

## 顶层

```text
ma3/
├── README.md / README.zh.md / CONTRIBUTING.md / CHANGELOG.md / LICENSE / SECURITY.md
├── code/
│   ├── server/          FastAPI：MCP、门户 UI、REST、auth、search
│   ├── client/          HTTP bundle：manifest、policy、sync 脚本
│   └── eval/            评测场景（非 v1 发布物）
├── docs/                系统化文档（01–09）
└── deploy/
    ├── self-host/       社区 Compose 交付物
    └── *.sh / README    维护者推送与验收（环境 env 不进 git）
```

运行时数据与 secret 留在部署目录 / 环境变量中（例如 `<DEPLOY_DIR>`），**不要**假定仓库根下存在已提交的 `data/` 或 `ma3.env`。

## Server 模块

```text
code/server/app/
├── api/           MCP、门户 HTML、REST（keys/orgs/libraries/setup/admin）、i18n、setup_gate
├── services/      mcp、onboarding、api_key、org、invite、local_auth、setup、billing、…
├── storage/       db、search、ranking
├── models/        mcp_payloads
├── auth/          session、OIDC / local
└── core/          config、security
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

CI：`.github/workflows/ci.yml`（unit + integration + self-host Docker build）。

## 设计过程稿

`docs/09-engineering/design-archive/` 仅保留各主题**决策摘要**（非契约）。规划中的设计项见 `design-backlog.md`。
