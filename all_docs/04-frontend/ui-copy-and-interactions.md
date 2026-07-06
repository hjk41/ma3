# UI 文案与交互规范

> **状态**：待补充 — 以下为已定片段

## 顶栏与导航

| 位置 | 文案 | 备注 |
|------|------|------|
| 顶栏 | 我的主页 · 库 · 记录 · 投票 · API Keys | 不用 Libraries |
| subnav（仅 /ui/me/*） | 概览 · 设置 | 不含「我的贡献/我的投票」 |
| admin | Observatory | 英文；`.nav-admin` 弱化 |

## 列表页标题

| 路由 | h1 |
|------|-----|
| `/ui/me/writes/` | 记录 |
| `/ui/me/votes/` | 投票 |
| `/ui/libraries/` | 库 |

## API Keys

| 元素 | 文案 |
|------|------|
| 删除按钮 | 删除 |
| 删除 title | 删除后此 key 将立即失效，无法恢复。 |
| 配额错误 | active key limit reached; delete an old key first |
| legacy 无 ciphertext | 旧 key 无存储副本；如需复制完整 key，请创建新 key 后删除旧 key。 |

**禁止**：撤销 / 已撤销

## 403 / 空状态

| 场景 | 文案 |
|------|------|
| Observatory 403 | Observatory 仅产品管理员可访问。 + 链接「返回我的主页」 |
| 新用户空贡献 | 引导创建 API key → onboarding |
| 匿名 public 库 | CTA「登录以贡献与投票」 |

## 交互模式

- 删除：`onsubmit="return confirm(...)"`（列表与详情 danger-zone）
- 复制：`ma3CopyFrom(this)` + `.copy-src` input 紧邻按钮前
- 表单失败：SSR 重渲染并回填用户输入（keys 详情 edit）
- 无 toast / modal 框架（v1）

## 待补充

- [ ] 全站错误页模板（401/403/404/503）
- [ ] 表单校验错误 inline 文案
- [ ] 中英文混排规范（Observatory 保留英文的例外列表）
