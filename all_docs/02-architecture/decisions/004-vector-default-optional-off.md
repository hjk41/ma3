# ADR-004 — Vector 搜索默认开启，可关闭

## 状态

Accepted（2026-07-01）

## 背景

LAN 202 曾因 HF 模型路径与 rsync 删 cache 导致 uvicorn 挂起。Q9 需在「体验完整」与「部署简单」间取舍。

## 决策

- **v1 默认启用 embedding + vector search**（与 FTS 混合）
- **关闭开关**：`MA3_DISABLE_EMBEDDINGS=1` → FTS-only，启动不拉 HF
- 完整模式部署 **必须**：
  - prewarm 到 `HF_HOME/.../hub/`
  - 生产设置 `HF_HUB_OFFLINE=1`
  - rsync/deploy exclude `data/`

## 后果

### 正面

- 生产/SaaS 搜索质量与旧设计一致
- LAN dev 仍可在无模型时快速起服务

### 负面

- 默认部署文档必须包含 HF cache 章节（见 `profile-common.md`）
- CI 需 FTS-only 与 vector 两套 job 或 mock embed

### 关联

- Q9
- 旧 `deploy/DEPLOY_RUNBOOK.md`、`prewarm_embedding_model.sh`
