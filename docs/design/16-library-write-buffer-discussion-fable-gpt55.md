# Discussion — 16 Library Write Buffer（fable × GPT-5.5）

> **📚 历史讨论**（2026-07-04）— ratified 决策见 [16-library-write-buffer-decisions-for-owner.md](16-library-write-buffer-decisions-for-owner.md)、[00-design-index-fable.md](00-design-index-fable.md) §2.2

> **Date**: 2026-07-04  
> **Inputs**: 产品负责人提案；[16-library-write-buffer-fable.md](16-library-write-buffer-fable.md)；[16-library-write-buffer-review-gpt55.md](16-library-write-buffer-review-gpt55.md)

---

## 1. 共识（双方 ACCEPT）

| # | 结论 |
|---|------|
| C1 | **需要 buffer 机制** — 写前 confirmation 不够；Community 误写需要写后隔离窗口 |
| C2 | **新 status `buffered`** + `publish_at`，期满或主动 publish → `active` |
| C3 | **缓冲期内仅写入者** 可 publish / 修改 / 删除；他人 **404 + 不可搜索** |
| C4 | **verify（证实/证伪）不进 buffer**；**draft 与 buffered 互斥** |
| C5 | **分库配置** `write_buffer_hours`；**0 = 现 ADR-002 行为** |
| C6 | **personal 库默认 buffer=0**；Community 默认 24h（双方从「全局 24」收敛于此） |
| C7 | v1 maintainer **不见** buffered；产品 admin Observatory 可枚举 |
| C8 | MCP 需 `ma3_publish_record` + 响应字段；门户 `/ui/me/writes/` 承载人类操作 |

---

## 2. 分歧与建议裁决

| ID | 议题 | fable | GPT-5.5 | **建议（交产品负责人）** |
|----|------|-------|---------|-------------------------|
| O1 | 全局默认 24h？ | 表内默认 24 | personal 必须 0 | **分库默认**：Community 24 / personal 0 / org 可配 |
| O2 | recall 后是否重置 publish_at | 倾向不重置 | 不重置 | **重置**（2026-07-04 产品修订：PATCH 后 `publish_at = now + write_buffer_hours`） |
| O3 | 修改实现 | 同 record 编辑表单 | PATCH 同 record_id | **PATCH 同 id**；不删+新 report |
| O4 | owner 键 | created_by | write_audit.principal_id | **principal_id 权威**；created_by 同步 |
| O5 | v1 是否带 UI | 希望 portal 操作区 | 可先 MCP-only | **v1.1 切片**：MCP + job 先行，portal badge 跟进 |
| O6 | Stats 计数 | buffered 不计 active | 同意 + author 侧「待发布」 | **采纳**；库公共 stats 不含 buffered |
| O7 | agent 写后搜不到自己 | 未强调 | blocking | **ma3_report 响应必须说明** + 文档/agent policy 教 `ma3_publish_record` |

---

## 3. 风险清单（讨论结论）

### 3.1 没有大问题

- 与 **硬删**（ADR-013）互补，不重复  
- 与 **draft 审核** 正交，不替代 maintainer 队列  
- 与 **用户门户** `/ui/me/writes/` 自然契合  
- 库级 admin 配置与现有 `retention_days` 模式一致  

### 3.2 需要注意

| 风险 | 缓解 |
|------|------|
| Agent 闭环断裂（写后 context 搜不到） | personal buffer=0；buffered 响应明示；policy 教 publish |
| 权限错绑（key 共享） | owner=principal_id 单测 |
| 定时 publish 遗漏 | cron job + `publish_at` 索引 |
| Demo「写即可搜」 | Community 可 env 设 `write_buffer_hours=0` 做 staging |
| 配额计数歧义 | design/09 补充：buffered 不计 active quota |

### 3.3 不建议做

- ❌ 用 buffer 替代 ADR-002 active default（全局）  
- ❌ buffered 对 maintainer 可见且需审批（scope → 第二套 draft）  
- ❌ 缓冲期内对他人可见但「只读」（违背提案）  

---

## 4. 综合 Verdict（review 阶段）

| Reviewer | Verdict |
|----------|---------|
| **fable** | **ACCEPT-WITH-NITS** |
| **GPT-5.5** | **ACCEPT-WITH-NITS** |

**产品决策 ratified（2026-07-04）**：见 [16-library-write-buffer-decisions-for-owner.md](16-library-write-buffer-decisions-for-owner.md)

---

## 5. Ratified 一句话

> 全库 **`write_buffer_hours` 默认 24**；personal 库 owner **可设 0**。新增/补充 → **`buffered`**；**写入者始终可见**，他人不可见；仅写入者可 PATCH（**重置 timer**）、删除或 **`ma3_publish_record`**；期满 → **active**。verify / draft 不变。**v1 带 portal UI**。用户说明进 **Community 公共库**。

---

## 6. 下一步

1. ~~产品负责人确认 O1–O7~~ ✅  
2. ~~定稿 fable 设计~~ ✅  
3. ADR-002 增补或 ADR-014  
4. 实现：schema → MCP → job → portal UI → 公共库说明  
