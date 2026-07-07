# 用户旅程（User Journeys）

## J1 — 新个人开发者：从零到首次写回

```text
发现 ma3 → 浏览器打开 /ui/keys/
  → Authing 注册/登录
  → /auth/callback：建 principal + personal library
  → /ui/me/setup/：一次性设定显示名
  → /ui/keys/：创建 key（personal + Community writer）
  → 复制 key → 配置 Agent MCP（X-API-Key）
  → ma3_whoami 确认双库
  → ma3_report（无 library_id）→ 写入 personal library
  → /ui/me/：概览出现「最近贡献」
```

详见 [../05-agent/getting-started.md](../05-agent/getting-started.md)。

## J2 — 贡献者：查看与管理自己的写入

```text
/ui/me/ → stat「记录」→ /ui/me/writes/
  → sort/filter（如「待发布」）
  → 点击 record → /ui/records/{id}/
  → buffered：发布 / 修改 / 删除
  → active：只读 + 投票
```

Write buffer 语义见 [../03-backend/write-buffer.md](../03-backend/write-buffer.md)。

## J3 — Agent：任务闭环（查 → 做 → 写回）

```text
任务开始 → ma3_context(query)
  → 选用命中 record → 本地验证
  → ma3_validate（可选 dry-run）
  → ma3_report → 响应 status/buffer/publish_at
  → 若 buffered：policy 提示用户可在门户提前发布
  → 对排在采用答案前的错误 record → ma3_feedback downvote
```

## J4 — 产品管理员：全局观测

```text
登录 → /ui/me/（与普通用户相同）
  → 顶栏 Observatory（admin only）
  → 全局 Stats + 枚举 + search explain
  → 非 admin 直访 → 403 +「返回我的主页」
```

## J5 — 删除泄漏的 API Key

```text
/ui/keys/ → 识别 key → 删除（confirm）
  → MCP 立即 401
  → 创建新 key → 更新 Agent 配置 → 删除旧 key（若仍存在）
```

详见 [../04-frontend/api-keys-ui-and-api.md](../04-frontend/api-keys-ui-and-api.md)。

## v1.1 预留旅程

- **J6** org admin 邀请成员、建 org library
- **J7** 库 admin 管理 grants、枚举库内 record
- **J8** 升级 Pro/Team、只读 key、配额告警
