# Review: 15 — User Portal

> Reviewer: GPT-5.5  
> Scope: [15-user-portal-fable.md](15-user-portal-fable.md) against ADR-005, ADR-011, design/08, live code (`routes_ui.py`, `routes_keys.py`, `db.py`)

## 1. Verdict

**ACCEPT-WITH-NITS**

方向正确：把 `/ui/me/` 作为人类落地页，把 Observatory 降级为管理员面，v1 不假装 org 管理已存在。实现前需钉死一条：`/ui/records/{id}` 的可读库策略必须写清楚，不能继承 Observatory 的「仅 lib_default」或意外暴露他人 private 库。

## 2. Blocking Issues

1. **`/ui/records/{id}` 需要明确的 session 读权限规则**

   迁移后不再是「Observatory 看公共库」，而是通用门户路由。须定义共享 SSR 读策略：

   - `lib_default`（Community Library）active record
   - 用户自己的 personal library（`owner_principal_id == session.principal_id`）
   - 用户 active key grants 涉及的库
   - org 衍生库在 `org_members` 落地前排除

   越权 → 404。需集成测试：Community active、自己的 personal、他人 personal、draft、unknown。

2. **旧路由与 feedback POST 的迁移契约**

   当前投票 POST 在 `/ui/observatory/records/{id}/feedback`。迁移后 canonical 路径应为 `/ui/records/{id}/feedback`，303 回详情页。旧 GET 301 或 admin-only redirect；旧 POST 404/410，避免双路径并存。

## 3. Non-Blocking Nits

1. 文档化所有默认落地入口：`/auth/login` 的 `next`、`pop_oauth_next` 回退、logo、post-logout、E2E。
2. Observatory admin 门控区分未登录 vs 已登录非 admin；避免 redirect 环。
3. v1 库列表文案诚实标注为「当前 key 可访问的库」，而非「全部 entitlement」。
4. 多把 key grant 同一库时，列表去重显示一行 + key 数量摘要。
5. `/auth/account` 若仍跳转 Authing，principal ID 应放本地 `/ui/me/` 或新 `/ui/me/account`，不要假设 Authing 页能展示。

## 4. What I Agree With

1. 默认落地 `/ui/me/` — Observatory 是运营概念，开发者应先看到自己的 key / 贡献。
2. Observatory admin-only — 全局 org/user 统计不应暴露给普通登录用户。
3. `/ui/records/{id}` 中性路由 — 可从 writes、votes、未来搜索复用。
4. v1 跳过 org UI — 无表则无 UI，避免空头承诺。
5. `is_admin` ≠ org/library admin — 平台观测与业务管理分离。
6. v1 库列表用 key grants + personal ownership 启发式 — 可接受，待 entitlement service。
7. 投票只在 record 详情页 — SSR 简单、状态单点。
8. 展示 principal ID — 邀请成员前必需。

## 5. Scope Check

v1 切片合适，聚焦个人开发者门户：me 主页、writes/votes、libraries 只读、records 迁移、Observatory 门控。不要把 org 管理、entitlement 编辑、billing 塞进 v1。

唯一应纳入 v1 的「额外」工作是 `/ui/records/{id}` 授权契约 — 这是路由迁移的安全前提，不是 scope creep。

## 6. Disagreements with Fable

### D1 — Observatory 非 admin 访问：302 vs 403

| | |
|---|---|
| **Fable** | 已登录非 admin 访问 Observatory → 302 `/ui/me/`（不用 403） |
| **GPT-5.5** | 未登录 302；已登录非 admin 更倾向 **403**（权限诊断更清晰） |
| **建议** | 若产品坚持 302，须写死目标 URL 并加非 admin 集成测试；否则用 403 |
| **严重度** | **需产品负责人决策** |

### D2 — Principal ID 展示时机

| | |
|---|---|
| **Fable** | v1.1 邀请流程再在 account 页展示 |
| **GPT-5.5** | 若 v1 已做 `/ui/me/`，顺手展示 copyable `principal_id`（低风险、利于支持） |
| **建议** | v1 在 `/ui/me/` 概况区展示；不必等 org 页面 |
| **严重度** | 可 defer |

### D3 — 库列表命名

| | |
|---|---|
| **Fable** | 「我的库权限」 |
| **GPT-5.5** | v1 实际是 key 能力并集，应称「当前 key 可访问的库」 |
| **建议** | 保留实现，改 UI 文案 |
| **严重度** | 可 defer |

### D4 — 旧 Observatory record 路径

| | |
|---|---|
| **Fable** | 301 到新路径 |
| **GPT-5.5** | 同意；须同一 PR 退役旧 feedback POST |
| **建议** | 301 GET + 410/404 旧 POST |
| **严重度** | 可 defer（工程卫生，非产品决策） |
