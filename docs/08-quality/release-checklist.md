# 发布检查清单

> **状态**：待补充

## 发版前（草案）

- [ ] 全量 `pytest` 绿
- [ ] `ma3_doctor` 无 fail（目标环境）
- [ ] MCP smoke：`tools/list`、`ma3_whoami`、`ma3_context`、dry-run `ma3_report`
- [ ] 门户 smoke：login → `/ui/me/` → keys 列表
- [ ] Authing callback + setup 流程（staging 新账号）
- [ ] manifest / policy `skill_bundle_version` bump（若 policy 变更）
- [ ] ADR/文档与行为一致（若 breaking）
- [ ] acceptance P* 回归（见 [acceptance-criteria.md](acceptance-criteria.md)）

## 部署后

- [ ] `/healthz` version/commit 正确
- [ ] admin 可访问 Observatory；非 admin 403
- [ ] buffer publish job 运行（写 buffered → 等 60s → active）
- [ ] 监控无异常 error rate

## 待补充

- [ ] 回滚检查项
- [ ] 数据库 migration 顺序
- [ ] 客户可见 changelog 链接
