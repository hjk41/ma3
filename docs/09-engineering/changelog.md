# 变更日志（Changelog）

> **状态**：待建立 — 从首次公网发布起按 semver 记录

## 格式

遵循 [Keep a Changelog](https://keepachangelog.com/)：

- **Added** / **Changed** / **Fixed** / **Removed** / **Security**
- 链接到 ADR 或 docs 规格（如有 breaking）

## 未发布（Unreleased）

### Added

- 用户门户统一 IA（顶栏：库·记录·投票·API Keys）
- Write buffer（24h 默认，作者可见）
- API Key 硬删除替代撤销
- Display name 一次性 setup
- MCP 错误 message 自纠（ADR-014）
- 搜索 GTN 排序（lexical 路径统一）

### Changed

- 默认落地页 `/ui/me/`
- Observatory 非 admin → 403
- Principal ID 移至 settings 只读

## 待补充

- [ ] 版本号与 git tag 对应关系
- [ ] 历史版本回填（202 部署里程碑）
