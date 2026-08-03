# 门户 Playwright 回归

> 英文版：[portal-playwright-regression.md](portal-playwright-regression.md)

设计：[Fable archive](../../09-engineering/design-archive/26-quality-playwright-eval-cadence-fable.md)。

## 决策记录

| 层级 | 何时 | 密钥 | 套件 |
|------|------|------|------|
| **A — local-auth smoke** | **每个 PR**（`ci.yml` → `e2e-portal`）+ nightly | 无 | `tests/e2e/test_portal_smoke.py`（P1–P12） |
| **B — Authing** | Nightly + 发版前 checklist | `AUTHING_TEST_*` + `MA3_E2E_BASE_URL` | `scripts/e2e_authing_ui.py`；缺密钥则 SKIP 并写 summary |

## 范围内 / 范围外

见英文版（登录会话、门户 SSR、浏览器交互；不重复 integration HTML 断言；无像素/跨浏览器）。

## 本地运行

```bash
cd code/server
pip install -r requirements.txt -r requirements-e2e.txt
playwright install chromium
pytest -q -o addopts= -m e2e tests/e2e --browser chromium
```
