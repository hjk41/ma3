# 验收文档（Acceptance）

> **真源**：本目录 + [../acceptance-criteria.md](../acceptance-criteria.md)  
> **设计对照**：[../../04-frontend/information-architecture.md](../../04-frontend/information-architecture.md)

## 文档列表

| 文档 | 范围 | 门禁 |
|------|------|------|
| [v1-user-portal-ui.md](v1-user-portal-ui.md) | 登录后门户 SSR UI（导航、列表、批量、HTML 不变式） | **发版必跑** |
| [v1-self-service-onboarding.md](v1-self-service-onboarding.md) | 自助注册 + key 签发 | 发版必跑 |
| [v1-api-key-lifecycle.md](v1-api-key-lifecycle.md) | Keys UI/API | 发版必跑 |
| [v1-display-name-registration.md](v1-display-name-registration.md) | 显示名 setup | 发版必跑 |
| [v1-library-write-buffer.md](v1-library-write-buffer.md) | buffered 状态机 | 发版必跑 |
| [v1-user-portal.md](v1-user-portal.md) | 历史 P1–P19 映射（只读归档） | — |
| [v1-ui-i18n-acceptance-gpt55.md](v1-ui-i18n-acceptance-gpt55.md) | UI i18n 验收 | — |
| [v1-personal-developer-journey.md](v1-personal-developer-journey.md) | 个人开发者旅程 eval | — |

## 发版前必跑（门户 UI）

```bash
cd code/server
.venv/bin/pytest tests/integration/test_user_portal*.py \
  tests/integration/test_portal_html_regression.py \
  tests/integration/test_display_name_registration.py \
  tests/integration/test_ui_i18n.py \
  -q --tb=short
```

**通过标准**：0 failed；任一 **R\***（HTML 回归）或 **W\***（记录列表）失败则 **不得** 向用户汇报「门户已验收」。

## 验收层次

| 层次 | 工具 | 覆盖 |
|------|------|------|
| L1 自动化 HTML | pytest + TestClient | 路由、表头链接、批量表单、文案、403/302 |
| L2 部署 smoke | `deploy/verify_ma3_v1.sh` | healthz、匿名页、MCP 工具数 |
| L3 浏览器 E2E | `scripts/e2e_authing_ui.py`（Playwright） | Authing 真登录、Keys 表单 |
| L4 人工目视 | owner checklist（见各文档末尾） | 布局间距、移动端换行 |

L1 未覆盖的交互 **必须** 在 L3/L4 补测，不得假设「集成测过了就不会出 UI bug」。
