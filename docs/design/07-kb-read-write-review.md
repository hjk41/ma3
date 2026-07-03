# 07 — 知识库读写 Review 与改进路线

> 多模型 review + Fable follow-up + P2 实现（2026-07-02）。

## 状态摘要

| 阶段 | 状态 |
|------|------|
| P0 读写闭环 | ✅ |
| P1 信任/检索/授权 | ✅ |
| P2 规模/产品化（核心三项） | ✅ |
| Fable P2 验收 | ✅ ACCEPT |
| P3 知识库访问与组织隔离（设计） | ✅ ADR-011 + [08-kb-access-and-org-isolation.md](08-kb-access-and-org-isolation.md) |
| P4 付费套餐与配额（设计） | ✅ ADR-012 + [09-billing-and-quotas.md](09-billing-and-quotas.md) |
| P5 写入确认、审计与删除（设计） | ✅ ADR-013 + [10-write-audit-and-delete.md](10-write-audit-and-delete.md) |

## P5 设计定稿（Write / Audit / Delete，2026-07-03）

- 证实/证伪 → 写 target 所在库，免确认（`verify_direct`）
- 补充/新增 → 写入前 agent↔用户确认；`user_confirmed` / `agent_judged`；默认个人库
- Library 必有可读 `name`；`ma3_list_my_writes` 审计；`ma3_delete_record` owner 硬删 + tombstone
- 下游保留，`source_deleted` + lineage 警告；信任 agent 分类，审计+删除兜底
- 修订 ADR-012：系统不因欠费删 record；用户可删自己的 record

## P3 设计定稿（KB + Team Isolation，2026-07-02）

- 强制 API key；移除匿名 MCP 读
- 双层授权：entitlement（visibility/org/grants）+ key_grants（read/write/maintain）
- Read+write 耦合；read-only key 仅 paid 用户或 paid org 成员
- org 多对多成员；org library + public/private visibility
- 实现分 6 阶段，见 08 文档 §10

## P2 完成项（2026-07-02）

### pgvector ANN
- Postgres：`CREATE EXTENSION vector`、HNSW 索引、`embedding_vec vector(384)`、启动时 blob 回填
- `ann_vector_search()` 替代 PG 上 500 条 brute-force；失败时降级到 blob 扫描
- SQLite 仍用 BLOB + cosine；`ma3_doctor` 报告 `pgvector_ready` / `hybrid_fts_pgvector`

### MCP JWT Bearer
- `RawCredential` + `extract_credential()`（`X-API-Key` / `Authorization: Bearer`）
- 解析顺序：dev key → maintainer → writer → Authing userinfo（Bearer）
- 无效 Bearer → JSON-RPC `-32001`；admin 用户 → `library_maintainer`
- `MA3_DEV_AUTH` 默认 **0**（测试 conftest 显式开启）

### ma3_report 幂等
- 表 `report_idempotency`（PK: `idempotency_key` + `principal_id`）
- 可选字段 `idempotency_key`；SHA256(canonical payload + `_visibility`)
- 同 key 同 hash → replay 同一 `record_id` + 索引 heal；hash 冲突 → 409
- record + idempotency 同事务；race 用 `ON CONFLICT DO NOTHING` + winner 检查

## P1 完成项（摘要）

- 写：redaction、relations、evidence 门槛、supersedes/redaction_mode 维护者门控、SaaS writer/maintainer API keys、无效 key → JSON-RPC -32001
- 读：trust 字段、include_full_json、读时 redaction、Observatory 仅 active + default library + 脱敏
- 检索：hybrid max-merge、context boost、feedback 加权、superseded 过滤、FTS OR + plainto fallback
- 治理：draft approve 写 relations + evidence 校验、索引 status 同步、relation library ACL

## 仍待（P2+ / 后续）

- case 语义聚类（embedding 相似度归属）
- FTS 中文/CJK 分词
- ~~匿名 MCP 读 default library~~ → **已定**：移除，所有读写须 key（ADR-011）
- review_note 审计表
- Agent policy 纳入 ma3_feedback
- pgvector Postgres 集成测试（CI 目前 SQLite-only）

## 环境变量

```bash
MA3_DEV_AUTH=1                    # LAN/dev 才开；默认 0
MA3_DEV_API_KEY=ma3dev
MA3_WRITER_API_KEYS=key1,key2    # DEPRECATED (ADR-011)：迁移期并存，改用 DB key
MA3_MAINTAINER_API_KEYS=key3     # DEPRECATED (ADR-011)
MA3_VECTOR_SCAN_LIMIT=500
MA3_EMBEDDING_DIM=384             # pgvector 列维度
```

## 验证

`tests/unit/test_kb_read_write.py` · `test_kb_p1.py` · `test_report_idempotency.py` · `test_mcp_jwt_auth.py` · `tests/integration/test_mcp_integration.py`（含 idempotency replay）
