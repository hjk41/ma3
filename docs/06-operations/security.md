# 安全规范

> **状态**：部分定稿 — 分散规格已吸收

## 认证与密钥

| 项 | 措施 |
|----|------|
| API key 存储 | 仅 SHA-256 hash + Fernet ciphertext；明文不落库日志 |
| key 传输 | HTTPS；`X-API-Key` header |
| key 失效 | 硬删或 legacy `revoked_at` |
| Session | Authing OIDC；mutating UI/API same-origin |
| Dev bypass | 仅 LAN；公网禁 `MA3_DEV_AUTH` |

## 授权

- MCP：**仅** DB key + dev bypass；无 anonymous 读
- key grants ⊆ owner entitlement；免费档 Community writer 锁定
- 越权：404（existence oracle 防护）
- Observatory：admin only → 403

## MCP 错误与泄露

- `error.message` 不含 secrets、堆栈、SQL
- search explain **不**经 MCP 返回（ADR-005 / 防刷榜）

## 写入与内容

- Write buffer：他人不可见 buffered
- 人 — 维护者：清除隐私/价值观不合规（ADR-008）
- `ma3_ui_session` **禁止**用于签 key

## 待补充

- [ ] 威胁模型（STRIDE 轻量）
- [ ] 依赖漏洞扫描流程
- [ ] 渗透测试 / 安全 review 节奏
- [ ] 数据保留与 GDPR/PII 处理
