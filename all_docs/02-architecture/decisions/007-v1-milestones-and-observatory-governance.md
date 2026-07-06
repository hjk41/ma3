# ADR-007 — v1 里程碑：Observatory 治理、首 deploy、数据迁移

## 状态

Accepted（2026-07-01）

## 背景

Q1–Q12 与 ADR 001–006 已定核心架构。开写 `code/` 前仍需三项执行层拍板：Observatory 写权限边界、首个可运行环境、旧库数据策略。

## 决策

### 1. Observatory 治理（选项 B）

Observatory 以 **只读浏览** 为主，供 **人 — 维护者** 使用；**Agent — 维护者** 通过 MCP 执行同等语义（ADR-008）。

人可在 UI 执行 **单一写动作（v1）**：

- **Mark record `invalid`**（含简要原因）

**不包含 v1**：

- 完整 review queue UI
- draft approve/reject 表单（仍走 MCP `ma3_review_record`）
- org/seat/billing 管理

与 ADR-005 关系：在「只读 Observatory」上增加 **最小治理写路径**，支撑 ADR-002 active 默认下的搜索污染缓解。

### 2. 首个 deploy 目标（选项 A）

v1 **先在 LAN dev（192.168.31.202）平行验证**：

- 新端口（如 `:8001`）
- SaaS **同一 binary**，`profile-lan` + `MA3_DEV_AUTH=1`
- 公网 SaaS staging（完整 OIDC）在 202 验证通过后推进

### 3. 数据迁移（选项 C）

**并行部署，cutover 后再迁数据**：

- v1 起 **新 PG 库 / 新 schema**（不原地改 202 上 `:8000` 生产库）
- 旧实例 `:8000` 继续服务直至 v1 验证完成
- cutover 时运行 **v2→v1 migration script**（含 `org_default` 回填）
- 回滚：DNS/端口指回旧实例

## 后果

### 正面

- 202 风险可控，不影响当前 `:8000` 用户
- Observatory 给人一个「纠错」按钮，不必全靠 MCP
- 迁移窗口清晰，可反复 dry-run

### 负面

- cutover 前 v1 库为空或仅测试数据，需接受双实例期
- invalid 写路径需 UI + API + ACL 设计与 MCP 语义对齐

### 关联

- ADR-002, ADR-005, ADR-001
- [pitch.md](../../01-product/pitch.md)
- [system-overview.md](../../02-architecture/system-overview.md) — v1 架构与 deploy profile
- [deployment.md](../../06-operations/deployment.md) — LAN / SaaS 部署
