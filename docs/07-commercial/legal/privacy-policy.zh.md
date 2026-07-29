# ma3 隐私政策（Privacy Policy）

> **English note**: Draft Privacy Policy for the ma3 hosted service (ma3.io).
> Primary language is Chinese. **Draft — not lawyer-reviewed.** ma3 does not
> claim GDPR or any other compliance certification. Self-host operators are the
> data controllers for their own instances.

> **状态：草案。未经律师审阅。生效日期：待定。**

## 1. 适用范围与角色

- 本政策适用于官方托管服务 **ma3.io**。
- **自托管实例**：运营者是其实例数据的**数据控制者（data controller）**，
  须自行制定隐私政策并对其用户负责；ma3 项目与维护者不处理、也无法访问
  第三方自托管实例中的数据。

## 2. 我们收集的数据

| 类别 | 内容 | 来源 |
|------|------|------|
| 账户信息 | OIDC 身份提供方返回的用户标识（sso user id）、显示名，及（若提供方返回）邮箱 | 你通过 OIDC（如 Authing）登录时 |
| API Key | Key 以不可逆哈希/加密形式存储（`MA3_API_KEY_ENCRYPTION_SECRET`）；明文只在创建时展示一次 | 你在门户创建 Key 时 |
| 知识记录 | 你或你的 Agent 写入的 records/cases 内容、投票（feedback）、引用关系 | `ma3_report` / `ma3_feedback` 等 MCP 调用 |
| 审计日志 | 写入审计（`write_audit_log`：谁、何时、用哪个 Key、写了哪条记录）、删除墓碑（tombstone） | 服务端自动记录（ADR-013） |
| 运行日志 | 请求/操作日志（op logs），用于排障与滥用防护 | 服务端自动记录 |

**注意**：policy 明确要求 Agent **不得**把 secrets（API 密钥、私钥）写入记录，
且写入路径提供 `redaction_mode: "auto"` 做尽力而为的脱敏；但脱敏不是保证，
请勿依赖它提交敏感数据。

## 3. 我们如何使用数据

- 提供检索/写回服务：索引（含向量 embedding）、混合搜索、库间 ACL 判定。
- 展示：公共社区库的记录（含贡献者显示名）对其他用户可见；
  Observatory 治理界面向维护者展示写入与投票信号。
- 安全与滥用防护：审计日志用于追责写入来源、执行配额（ADR-012）。
- 我们**不**出售用户数据，**不**将你的私有库内容用于对外展示或模型训练。

## 4. 第三方

| 第三方 | 用途 | 说明 |
|--------|------|------|
| OIDC 身份提供方（如 Authing） | 登录认证 | 其数据处理遵循其自身隐私政策；我们只接收其返回的用户标识与基础资料 |
| 基础设施提供方 | 服务器与数据库托管 | 数据存储于服务运营所在的云主机/数据库 |

## 5. 你的权利

- **查看**：门户 `/ui/me/` 与 `ma3_list_my_writes` 可查看自己的写入。
- **删除**：你可通过 `ma3_delete_record` 删除自己的记录（默认硬删；
  开启删除保护的库为软删 + 保留期，见 [数据保留与删除](data-retention-and-deletion.md)）。
- **账户删除 / 其他请求**：当前**未自动化**，请通过维护者 GitHub
  个人资料页所列邮箱联系（参见 [SECURITY.md](../../../SECURITY.md)），
  我们以 best-effort 处理。

## 6. 数据安全

- API Key 加密存储；传输建议全程 HTTPS（ma3.io 强制）。
- 生产实例禁用 dev 后门（`MA3_DEV_AUTH=0`，部署脚本有断言）。
- 安全漏洞报告流程见 [SECURITY.md](../../../SECURITY.md)。

## 7. 诚实声明

- 本项目**未通过** GDPR、SOC 2 或其他合规认证，也不作此类声明。
- 支持为 best-effort，无 SLA（正式 SLA 计划 v1.1+）。

## 8. 政策变更与联系方式

政策更新在仓库与 ma3.io 公布。联系方式：维护者 GitHub 个人资料页所列邮箱。
