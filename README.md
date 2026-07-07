# ma3 — v1 redesign (default branch)

本仓库 **main** 为 v1 级 redesign（原 v2–v4 层叠实现见 **`old`** 分支）。

## 目录

| 路径 | 说明 |
|------|------|
| [docs/](docs/) | 系统化文档（产品、架构、运维、验收） |
| [code/](code/) | server / client / eval 实现 |
| [deploy/](deploy/) | 部署与验证脚本 |

历史代码：`git checkout old`

## 文档入口

| 文档 | 用途 |
|------|------|
| [docs/README.md](docs/README.md) | **文档地图**（新人从这里开始） |
| [docs/01-product/pitch.md](docs/01-product/pitch.md) | 产品 pitch |
| [docs/01-product/vision.md](docs/01-product/vision.md) | 愿景与原则 |
| [docs/02-architecture/system-overview.md](docs/02-architecture/system-overview.md) | 系统架构与 MCP 契约 |
| [docs/02-architecture/architecture-decisions.md](docs/02-architecture/architecture-decisions.md) | ADR 索引 |
| [docs/05-agent/getting-started.md](docs/05-agent/getting-started.md) | Agent 接入 |
| [docs/08-quality/acceptance/README.md](docs/08-quality/acceptance/README.md) | 验收文档索引 |

## 分支

- **`main`** — v1 redesign（当前默认）
- **`old`** — 原 v4 及之前实现（`Release ma3 v4.0` @ `3c32330`）
