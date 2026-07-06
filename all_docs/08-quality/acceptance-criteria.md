# 验收标准（Acceptance Criteria）

> **门户 UI 完整验收（2026-07-06 起）**：[acceptance/v1-user-portal-ui.md](acceptance/v1-user-portal-ui.md) — **发版必跑**  
> **索引与命令**：[acceptance/README.md](acceptance/README.md)

## 索引

| 版本 | 主题 | 文件 | 状态 |
|------|------|------|------|
| v1 | **门户 UI（SSR + HTML 回归）** | [acceptance/v1-user-portal-ui.md](acceptance/v1-user-portal-ui.md) | ✅ 真源 |
| v1 | 自助 onboarding | `docs/acceptance/v1-self-service-onboarding.md` | 已有 |
| v1 | API Key 生命周期 | `docs/acceptance/v1-api-key-lifecycle.md` | 已有 |
| v1 | 显示名注册 | `docs/acceptance/v1-display-name-registration.md` | 已有 |
| v1 | 用户门户 P1–P19（归档） | `docs/acceptance/v1-user-portal.md` | 映射至 v1-user-portal-ui |
| v1 | Write buffer | `docs/acceptance/v1-library-write-buffer.md` | PASS-WITH-NITS |
| v1 | 个人开发者旅程 | `docs/acceptance/v1-personal-developer-journey.md` | 已有 |

## 发版硬门禁（门户）

```bash
cd code/server
.venv/bin/pytest tests/integration/test_user_portal*.py \
  tests/integration/test_portal_html_regression.py \
  tests/integration/test_display_name_registration.py -q
```

**R 系列（HTML 不变式）** 任一失败 → 不得 sign-off。

## 门户验收条目摘要

| 系列 | 范围 |
|------|------|
| **R1–R5** | 表头链接不转义、表单错误不返回 JSON |
| **N1–N7** | 路由、顶栏、subnav、Observatory 403 |
| **M1–M5** | 概览 stat、无 Principal ID 泄露 |
| **S1–S3** | settings 只读 |
| **W1–W20** | 记录列表 sort/filter/batch/全选/已删除文案 |
| **V1–V4** | 投票列表 |
| **L/D/K** | 库、详情、Keys（见各专题 doc） |

完整表见 [acceptance/v1-user-portal-ui.md](acceptance/v1-user-portal-ui.md)。

## 待补充

- [ ] 将其余 `docs/acceptance/v1-*.md` 正文迁入 `acceptance/`
- [ ] 发版 sign-off 模板（谁签、哪些 AC 必过）
- [ ] Agent 行为验收 T1–T5（release-agent-behavior-tests）
