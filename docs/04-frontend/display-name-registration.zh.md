# 17 — 显示名注册设定（display name registration）

> **状态**：已实现（2026-07-05）  
> **实现**：`principal_service.py`、`routes_auth.py`、`routes_portal.py`、`db.py`  
> **验收**：[acceptance-criteria.md](../08-quality/acceptance-criteria.md)（`v1-display-name-registration` 待迁入）

用户在 Authing 注册/首次登录后，必须在 **`/ui/me/setup/`** 一次性选定 **显示名**（门户可见昵称）。显示名与 Authing 账户昵称、Principal ID 不同。

---

## 1. 产品约束

| ID | 约束 | 说明 |
|----|------|------|
| **C1** | **注册时提示设定** | Authing `/auth/callback` 完成后，若 `display_name_locked=0`，302 到 `/ui/me/setup/?next=…`；门户其他页与 API Keys 在此之前不可用 |
| **C2** | **只能设定一次** | 用户通过 setup 表单提交成功后 `display_name_locked=1`；此后 setup POST、settings POST 均返回 400「显示名已设定，不可修改」；settings 页只读展示 |
| **C3** | **全局唯一** | 所有 `kind=user` 的显示名在 ma3 内唯一；比较时 **不区分大小写**（`lower(display_name)`）；冲突时返回「显示名已被使用，请换一个」 |

### 1.1 格式规则（setup 校验）

- 长度 2–32 字符（trim + 折叠空白）
- 不可为 uuid / Authing sub 风格（`[0-9a-f]{20,}`）
- 不可含控制字符

### 1.2 与 Principal ID 的关系

- **Principal ID**（`user:{sso_sub}`）永久不变，在 **设置页** 只读展示（无复制按钮）
- **显示名**用于顶栏、个人库名（`{显示名} 的个人库`）、MCP `whoami.display_name`
- **概览页**只展示 avatar + 显示名，**不**展示 Principal ID，**不**提供编辑入口

---

## 2. 用户流程

```
Authing 注册/登录
    → /auth/callback（upsert principal，display_name=sso_sub，locked=0）
    → /ui/me/setup/（欢迎 + 表单）
    → POST 设定显示名（校验唯一 + 格式）
    → display_name_locked=1，重命名个人库
    → next（默认 /ui/me/）
```

未完成 setup 时访问 `/ui/me/`、`/ui/keys/` 等 → 302 `/ui/me/setup/`。  
`GET /api/keys` → 403，detail 提示先完成 setup。

---

## 3. 数据与实现

| 项 | 说明 |
|----|------|
| `principals.display_name` | 用户可见昵称 |
| `principals.display_name_locked` | `0`=待设定；`1`=已锁定 |
| `idx_principals_user_display_name` | 部分唯一索引 `lower(display_name) WHERE kind='user'` |
| `complete_display_name_setup()` | 首次设定 + 锁 + 个人库重命名 |
| 启动迁移 | 已有 `display_name <> sso_user` 且长度≥2 的老用户自动 `locked=1` |

Authing 再次登录 **不会** 覆盖已锁定的显示名；未锁定用户 upsert 时 display_name 保持 `sso_sub` 占位。

---

## 4. 页面职责

| 路由 | 职责 |
|------|------|
| `/ui/me/setup/` | 注册后一次性设定（表单 + 约束说明） |
| `/ui/me/settings/` | 只读显示名 + Principal ID（`.id-block`，mono，无复制） |
| `/ui/me/` | 概览（仅 avatar + 显示名，无编辑链接） |
