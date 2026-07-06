# 22 — 用户门户统一布局讨论（fable × GPT-5.5）

> **📚 讨论记录**（2026-07-05）— 结论已并入 [22-user-portal-ui-unified-layout-fable.md](22-user-portal-ui-unified-layout-fable.md) 与 [00-design-index-fable.md](00-design-index-fable.md)

> **日期**：2026-07-05  
> **输入**：[22-user-portal-ui-unified-layout-fable.md](22-user-portal-ui-unified-layout-fable.md)、design/15–21  
> **结论**：**ACCEPT-WITH-NITS** — 可作为下一版门户 UI 的实现真源

---

## 1. 讨论背景

Owner 在 design/15 已交付门户 v1 后，连续提出：

- 概览 stat 可点、记录/投票列表可管理、分页可选每页条数  
- **库 / 记录 / 投票 / API Keys 应为同级顶栏目录**  
- **先写文档、暂不实现**

fable 将 design/18–21 与现网 design/15/14/17/16 合并为 **design/22 统一方案**，交 GPT-5.5 做架构与 SSR 可行性评审。

---

## 2. GPT-5.5 总评

**ACCEPT-WITH-NITS**

统一方案解决了 design/15 的核心 IA 债务：writes/votes 不应与「账户设置」混在同一 subnav。提升到顶栏后，用户心智变为：

- **我的主页** = 我看一眼整体状态  
- **库 / 记录 / 投票 / API Keys** = 我管理一类资源  

SSR 约束下，sort/filter/pagination 必须走 query string + server render，**不能**为列表页引入 SPA 状态；fable 方案与此一致。

**无 blocking issues。**

---

## 3. 共识决策（已写入 design/22）

| # | 议题 | 结论 |
|---|------|------|
| D1 | 顶栏 vs subnav 分工 | 资源 → 顶栏；账户 → `/ui/me/` subnav 仅概览+设置 |
| D2 | URL | v1 保留 `/ui/me/writes/`、`/ui/me/votes/`；只改 `active_nav` 与标题 |
| D3 | 文案 | 「库」中文化；`API Keys` 保留英文 |
| D4 | Stat「待发布」 | 依赖 writes `?status=buffered`；与 stat 链接同批或 stat 稍后 |
| D5 | 批量操作 | 仅记录列表、仅 buffered+owner、仅当前页 |
| D6 | 投票列表 | 共享列表壳，无批量；改票只在 record 详情 |
| D7 | 实现顺序 | Phase 0 helpers → IA → 列表 → stat links（见 design/22 §6） |
| D8 | 个人库名 | 数据同步，可与列表 phase 夹带，验收独立 |

---

## 4. GPT-5.5 非阻塞 nits（实现时注意）

1. **`render_pagination` 必须保留 query** — 否则 filter/sort/per_page 在翻页时丢失（现网已有此风险，增强时一并修）。
2. **`render_stat_cards` 向后兼容** — 库详情等页仍用不可点 stat；helper 应用 `(label, value)` 与 `(label, value, href)` 双形态。
3. **排序列 SQL 白名单** — `sort` query 不可直接拼进 ORDER BY。
4. **顶栏 5 项宽度** — v1 接受 flex 换行；不做 hamburger menu。
5. **filter pill 与 stat 标签一致** — 「待发布」在 stat、pill、badge 三处同词。
6. **批量删除 confirm** — 列表级一次 confirm，不必 per-row 双 confirm。
7. **零数据 list-footer** — 无行时仍显示「共 0 条」与 per_page pill，方便用户改每页条数。
8. **design/15 线框过时** — 以 design/22 + design/17 profile 为准，勿再引用「Principal ID 在概览」旧线框。

---

## 5. fable 对 GPT-5.5 的回应

| GPT-5.5 观点 | fable |
|--------------|-------|
| Phase 0 先抽 helper | **采纳** — 避免 writes/votes 各 copy 一套 pill/pagination HTML |
| 403 vs 302 Observatory | **不在本方案范围** — design/15 已 ratified 403 |
| 「当前 key 可访问的库」文案 | **defer** — 库列表 subtitle 可在实现时微调，不阻塞 IA |
| 跨页批量选择 | **拒绝 v1** — SSR 复杂度不值得；当前页批量足够 |

---

## 6. 标准列表页线框（双模型确认）

### 记录

```text
顶栏：… | 记录 | …  （记录 active）

记录
写审计日志；含 API key 写入。待发布记录可批量发布或删除。

[全部] [已发布] [待发布] [已删除]

┌ card ─────────────────────────────────────────────────────────────┐
│ □  时间↕  记录↕  状态↕  库↕  类型↕  Key↕                        │
│ □  …      problem…  待发布  hjk41的个人库  new  ma3k_ab…         │
└───────────────────────────────────────────────────────────────────┘
批量操作（仅待发布）： [批量发布] [批量删除]

共 128 条    每页 10 · 25 · 50 · 100    ← 上一页  第 1/3 页  下一页 →
```

### 投票

```text
顶栏：… | 投票 | …  （投票 active）

投票
只读列表；改票请进入 record 详情页。

[全部] [👍 赞同] [👎 反对]

┌ card ─────────────────────────────────────────────────────────────┐
│  时间↕  投票↕  记录↕  库↕                                       │
│  …     👍    problem…  Community                                 │
└───────────────────────────────────────────────────────────────────┘

共 42 条    每页 10 · 25 · 50 · 100    ← 上一页  第 1/1 页  下一页 →
```

---

## 7. 下一步（给 owner）

1. **确认 design/22** 为下一版 UI 真源（IA + 布局 + 阶段）  
2. 实现时 **单 PR 交付 Phase 0–5**，避免半套导航上线  
3. 验收对照 acceptance **P13–P19**  
4. v1.1 再议：URL 美化、库 subtitle 诚实化、移动端顶栏
