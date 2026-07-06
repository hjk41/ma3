# Review: 16 — Library Write Buffer

> **📚 历史评审** — ratified 见 [16-library-write-buffer-decisions-for-owner.md](16-library-write-buffer-decisions-for-owner.md)

> **Reviewer**: GPT-5.5  
> **Date**: 2026-07-04  
> **Doc reviewed**: [16-library-write-buffer-fable.md](16-library-write-buffer-fable.md)  
> **Code / ADR reviewed**: ADR-002, ADR-013, `report_store_service.py`, `search.py`, `mcp_tool_service.py`, `write_audit_log`, user portal `/ui/me/writes/`

## 1. Verdict

**ACCEPT-WITH-NITS — 方向可行，但必须分库默认 + 钉死与 ADR-002 的兼容契约，否则 agent 闭环和 Community「写即可搜」会被 silently 破坏。**

Buffer 解决的是 ADR-013 **写前确认**管不住的问题：agent 已 `agent_judged` 落库、或用户事后才发现误写。作为 **写后隔离窗口**，比把 Community 改回 draft-default 更贴近「用户对自己内容负责」叙事（ADR-013 §5 公共库 owner 可硬删）。

## 2. Blocking Issues

### B1 — 与 ADR-002「默认 active、写后立即可 context」的冲突必须可配置关闭

若 **所有库** 默认 24h buffer：

- `ma3_report` 成功后 `ma3_context` **搜不到自己的刚写 record**（search 只索引 active）→ agent 以为写入失败，可能重复 report  
- pitch / eval 场景「write → context 闭环」断裂  

**Fix（必须写进 ratified 设计）**：

1. **`write_buffer_hours=0` 必须等价于现行为**（默认 active、立刻可检索）  
2. **分库默认**：Community = 24h；**personal = 0**（fable §2.2 同意，我列为 blocking 因为不能 defer）  
3. `ma3_report` 响应在 buffered 时 **显式** 返回 `status`, `publish_at`, `readable_by: ["author"]`，并在 `structuredContent` 提示「对你可见、对他人不可检索，可 ma3_publish_record 提前发布」  

### B2 — Owner 判定与 agent 写入身份

Today `records.created_by` exists but **backfill 与 ma3_report 路径是否始终写入 principal** 须核实。Buffer 撤回权限绑定 `created_by == principal_id`：

- 若 agent 用 org key 写、principal 是 user A，撤回必须认 **key owner** 还是 **session principal**？  
- 建议：**write_audit_log.principal_id** 为权威（已有）；`created_by` 与之同步写入  

**Fix**：ratified 设计指定 owner = `write_audit_log.principal_id`；`created_by` 冗余一致；集成测试：A 的 key 写、B 不能 publish/delete。

### B3 — Stats / 计数 / 门户一致性

Portal library stats（design/15 Stats-only）与 Observatory 均按 `by_status.active` 计数。buffered 若处理不一致：

- 作者看「我写了 1 条」但库 Stats 显示 0 → 支持工单  
- Community 总数少算 → 运营误解  

**Fix**：文档已倾向 buffered **不计 active**；须同时：

- `/ui/me/writes/` 单独「待发布」计数  
- library detail 可选 pill「待发布 N（仅你可见）」— 仅对 author 展示，不进公共 stats  

## 3. Non-Blocking Nits

1. **Cron vs lazy publish**：仅 lazy-on-read 会在无流量时永不发布；必须 **scheduled job** 或 write 时 schedule。  
2. **Recall 是否重置 timer**：我倾向 **不重置**（防滥用 buffer 当 private draft）；若产品要「改完再宽限 24h」需单独 flag。  
3. **Update API 形状**：v1 可只做「delete + re-report」而非 PATCH，减 scope；UI 称「撤回修改」= 预填表单的新 report 替换（需否 tombstone 旧 id？建议 **同 record_id PATCH** 更简单）。  
4. **`ma3_publish_record` idempotency**：已 active → 200 noop。  
5. **verify/supplement 边界**：supplement 进 buffer、verify 不进 — 合理；需在 `report_kind` 分流单测。  
6. **Maintainer 不可见 buffered（v1）**：我同意；否则 Community 24h 内 maintainer 仍要审「未发布」内容，scope 膨胀。  
7. **Billing**：buffer 不计 quota「active+draft」计数（design/09）— buffered 应 **不计入** 或 **半计**；写清楚。  

## 4. What I Agree With

1. **新 status `buffered`** 优于 hidden-on-active — 与 search、portal、Observatory 过滤一致。  
2. **仅写入者** 可 recall/delete/publish — 对齐 ADR-013 owner 硬删哲学。  
3. **与 draft 互斥** — 三条轴（confirmation / buffer / draft）分工清晰。  
4. **verify 豁免 buffer** — 证伪/证实不应隐藏 target 所在库的更新。  
5. **门户 `/ui/me/writes/` 承载操作** — 人类友好；agent 用 MCP publish。  
6. **管理员可配 per-library** — `libraries` 表已有 `retention_days` / `deletion_protection` 先例，加列自然。  

## 5. Disagreements with Fable

### D1 — 全局默认 24h vs 分库默认

| | |
|---|---|
| **Fable** | 表格写默认 24，personal「建议 0」 |
| **GPT-5.5** | **ratified 必须** personal=0、Community=24；全局 24 会误伤 personal agent 闭环 |
| **严重度** | **Blocking** — 产品负责人需确认 |

### D2 — 「撤回并修改」= PATCH 同 record_id vs 删了重写

| | |
|---|---|
| **Fable** | 编辑表单，同 record 生命周期 |
| **GPT-5.5** | 同意同 record_id PATCH；反对删+新 report（破坏 audit / record_id 引用） |
| **严重度** | 工程细节，fable 方向正确 |

### D3 — Maintainer / admin 可见性

| | |
|---|---|
| **Fable** | v1 maintainer 不可见 buffered |
| **GPT-5.5** | 同意 v1；Observatory admin 可见即可 debug |
| **严重度** | Aligned |

### D4 — 提前 publish 是否需二次确认

| | |
|---|---|
| **Fable** | 一键 publish |
| **GPT-5.5** | 同意；buffer 本身就是确认窗口，publish 不需要 modal |
| **严重度** | Aligned |

## 6. Scope Check

**适合 v1.1 切片**，不必塞进 portal v1 刚交付的 PR：

- 依赖：`created_by` 可靠、search 过滤、新 MCP 工具、定时 publish  
- 可先 ship **DB + MCP + 无 UI**，portal badge 跟进  

**不应做**：把 buffer 当成 draft 审核替代品；Community 全面 draft-default（倒退 ADR-002）。

## 7. Test Matrix（preview）

| Case | Expect |
|------|--------|
| Community buffer=24, new report | status=buffered; other user context miss; author context hit after publish |
| personal buffer=0 | immediate active |
| verify_direct | active, no buffer |
| visibility=draft | draft, not buffered |
| author publish_now | active, searchable |
| author delete buffered | tombstone, gone |
| non-author GET record | 404 |
| buffer expiry job | active |

## 8. Summary

**没有问题的大方向** — buffer 是 Community 误写的正确补丁。  
**有问题的是「所有库统一 24h 默认」和「不声明 agent 可见性语义」** — Fix 后 ACCEPT。
