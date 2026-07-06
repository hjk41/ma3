# 16 — Write Buffer 产品决策（ratified）

> **状态**：定稿（2026-07-04，产品负责人拍板）  
> **设计真源**：[16-library-write-buffer-fable.md](16-library-write-buffer-fable.md)  
> **Review**：[16-library-write-buffer-review-gpt55.md](16-library-write-buffer-review-gpt55.md)、[16-library-write-buffer-discussion-fable-gpt55.md](16-library-write-buffer-discussion-fable-gpt55.md)

---

## Ratified 决策

| # | 议题 | 决定 |
|---|------|------|
| **1** | 默认 buffer | **全局默认 `write_buffer_hours = 24`**。personal 库因 buffer 内容对 owner 本就可读，功能上 buffer 对 sole owner **无实质影响**；personal 库 **owner 可将 buffer 设为 0**（立即 publish，等同关闭 buffer） |
| **2** | 撤回修改后计时 | **PATCH 后重置 `publish_at`** = `now + write_buffer_hours`（更友好：改完再给完整缓冲窗口） |
| **3** | 修改实现 | **PATCH 同 `record_id` 覆盖**原 record；不删+新 report |
| **4** | 写入者判定 | **`write_audit_log.principal_id` 为权威**；`records.created_by` 与之同步 |
| **5** | UI | **v1 即带 UI**：`/ui/me/writes/` 待发布态 + `/ui/records/{id}/` 操作区（发布 / 修改 / 删除） |
| **6** | Stats 计数 | **buffered 不计入**库公共 active stats；作者侧展示「待发布」计数 |
| **7** | 用户/agent 说明 | **自己写的 buffered 内容对自己可见**，仅他人暂时不可见；该说明与 ma3 其他用户指南一并写入 **Community 公共知识库（`lib_default`）** |

---

## 对 review 分歧的覆盖

| 原建议 | 产品决定 |
|--------|----------|
| personal 库默认 buffer=0（GPT-5.5 blocking） | **schema 默认仍 24**；personal owner **可配 0**；对 sole owner 体验等价 |
| v1.1 再带 portal UI | **v1 带 UI** |
| ma3_report 响应 + policy 教 publish | **采纳** + **公共库知识条目**（决策 7） |

---

## 实现约束（engineering）

1. `libraries.write_buffer_hours INTEGER NOT NULL DEFAULT 24`
2. personal 库创建时仍默认 24；owner 在库设置（v1 可先 Observatory admin 或 `/ui/libraries/{id}/settings`）改为 0
3. 作者读路径：`ma3_context` / `ma3_list_my_writes` / deep link **包含本人 buffered**
4. 他人读路径：404；search 索引排除他人 buffered
5. verify / draft 路径不变（见 fable §2.1、§6）

---

## 下一步

- [x] 更新 `16-library-write-buffer-fable.md` → 定稿  
- [x] 实现 + acceptance（[v1-library-write-buffer](../acceptance/v1-library-write-buffer.md) PASS-WITH-NITS）  
- [ ] 公共库用户说明 record（决策 7，内容运营）
