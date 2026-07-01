# ma3 — v1 redesign (default branch)

本仓库 **main** 为 v1 级 redesign（原 v2–v4 层叠实现见 **`old`** 分支）。

## 目录

| 路径 | 说明 |
|------|------|
| [docs/](docs/) | 愿景、架构、ADR |
| [code/](code/) | server / client / eval 实现 |
| [deploy/](deploy/) | 部署与验证脚本 |

历史代码：`git checkout old`

## 文档索引

| 文档 | 用途 |
|------|------|
| [docs/00-vision.md](docs/00-vision.md) | 最初设计目标（从 v2/v4/ lessons 提炼的一页纸） |
| [docs/01-problem-statement.md](docs/01-problem-statement.md) | ma3 是什么 / 不是什么 |
| [docs/02-current-state-audit.md](docs/02-current-state-audit.md) | 现有 `/home/hct/ma3` 诚实审计 |
| [docs/03-design-review.md](docs/03-design-review.md) | **设计 review + 待讨论问题**（请先读这篇） |
| [docs/04-target-architecture-draft.md](docs/04-target-architecture-draft.md) | v1 目标架构（**已定稿**） |
| [docs/05-doc-code-mapping.md](docs/05-doc-code-mapping.md) | 旧 repo 文件 → v1 模块映射计划 |
| [docs/PITCH.md](docs/PITCH.md) | **产品 pitch**（语义真源） |
| [docs/06-pitch-alignment-review.md](docs/06-pitch-alignment-review.md) | Pitch ↔ 设计对齐检查 |
| [docs/adr/](docs/adr/) | ADR 001–009（Accepted） |

## 分支

- **`main`** — v1 redesign（当前默认）
- **`old`** — 原 v4 及之前实现（`Release ma3 v4.0` @ `3c32330`）
