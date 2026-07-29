# ADR-004 — Vector search enabled by default, can be turned off

> Chinese version: [004-vector-default-optional-off.zh.md](004-vector-default-optional-off.zh.md)

## Status

Accepted (2026-07-01)

## Context

LAN host 202 once hung uvicorn on startup due to HF model path issues combined with rsync deleting the cache. Q9 required weighing "full experience" against "simple deployment."

## Decision

- **v1 enables embedding + vector search by default** (hybrid with FTS)
- **Off switch**: `MA3_DISABLE_EMBEDDINGS=1` → FTS-only, no HF pull at startup
- Full-mode deployments **must**:
  - Prewarm to `HF_HOME/.../hub/`
  - Set `HF_HUB_OFFLINE=1` in production
  - Exclude `data/` from rsync/deploy

## Consequences

### Positive

- Production/SaaS search quality matches the old design
- LAN dev can still start the service quickly without the model

### Negative

- Default deployment docs must include an HF cache section (see `profile-common.md`)
- CI needs separate FTS-only and vector jobs, or a mock embedder

### Related

- Q9
- Old `deploy/DEPLOY_RUNBOOK.md`, `prewarm_embedding_model.sh`
