# ADR-008 — 维护者（Maintainer）：人与 Agent 共同维护知识社区

## 状态

Accepted（2026-07-01）

## 背景

ma3 library 类比 **线上知识社区**：除 Agent 贡献 verified 知识外，还需要 **维护者** 参与标注、纠错、整理与总结。

**维护者可以是人，也可以是有权限的 Agent** — 参照开源项目的 *maintainer* 与论坛 *版主* 的职责，但不使用生僻的「策展者 / Curator」称谓。

**术语区分**：

| 用语 | 含义 |
|------|------|
| **维护者（Maintainer）** | 运行时角色：治理 library 内容的人 **或** Agent |
| **产品负责人** | 设计拍板、文档决策的人（非产品角色名） |
| **管理者 / Admin** | 组织、席位、SSO 等平台后台（v1.1+，与内容维护者分离） |

## 决策

### 1. 角色：维护者（Maintainer）

| 维护者能力 | 人（Observatory UI） | Agent（MCP） |
|------------|---------------------|--------------|
| 浏览 case / record / explain | ✓ v1 | ✓ 读类 MCP 工具 |
| Mark record **invalid** | ✓ v1（ADR-007） | ✓ v1 — review / invalid 语义 |
| Approve / reject **draft** | v1.1 UI；v1 走 MCP | ✓ `ma3_list_drafts` / `ma3_review_record` |
| Case **总结 / 标注** | v1.1+ | v1.1+ |
| 社区级 **知识整理**（合并重复 case 等） | 后续 | 后续 — 高权限维护者 Agent |

### 2. 维护分层：Agent 执行，人裁量

```text
Agent 贡献者 ── 写回 ──► verified 知识
Agent 维护者 ── 日常维护 ──► 标过时、整理、建议（规模化）
人 / 团队维护者 ── 监督纠偏 ──► 纠正 Agent 维护者误判
                              ──► 清除不该有的内容（隐私、价值观/合规）
```

- **维护者 Agent**：自动化、高频、可审计；其动作 **可被人类推翻或修正**。  
- **人与团队维护者**：library 的 **最终责任方**；对维护者 Agent **纠偏**，并处理 Agent 无法单独承担的判断（隐私、组织价值观、合规红线）。  
- **管理者（Admin）**：组织成员与订阅，不替代内容维护职责。

写回默认 **active**（ADR-002）；日常维护靠 Agent 扩展，**信任与合规靠人兜底**。

### 3. 人与团队维护者纠偏范围（必须支持）

| 类别 | 示例 | 典型动作 |
|------|------|----------|
| **纠正 Agent 维护者** | 误标 invalid、误合并 case | 恢复 status、撤销 relation |
| **隐私与敏感信息** | token、密钥、个人身份信息 | 作废或 redact record |
| **价值观 / 合规** | 与团队准则或政策不符的内容 | 作废 + 可选 library 级 policy 说明 |

维护者 Agent 的每次治理动作应 **可审计**（op log），供人类复查与纠偏。

### 4. 权限

- **Reader Agent**：读
- **Writer Agent**：+ 写回
- **维护者 Agent**（`library_maintainer`）：review、mark invalid、整理建议；动作可被人撤销  
- **人 — 维护者**（`library_admin` 或更高）：**覆盖** Agent 维护者决策；隐私/价值观类 **最终删除权**

Observatory UI 与 MCP **同一套 domain 逻辑**；人维护者优先于 Agent 维护者。

### 5. v1 范围

- 对外 Pitch 与文档统一 **维护者 / Maintainer**
- v1：Agent 经 MCP 参与日常维护；Observatory 供 **人 — 维护者** 浏览、mark invalid、**撤销/纠正 Agent 维护者动作**（最小：invalid + op log 可见）
- v1.1+：Case 总结、维护者 Agent 动作队列、人审工作台、library 价值观/隐私 policy 模板

## 后果

### 正面

- 称谓自然，技术用户熟悉 *maintainer*
- 与「管理者（组织 Admin）」边界清晰
- 维护者 Agent 提效，**人不失控**
- 企业可接受：隐私与价值观有 **人类最终责任方**

### 负面

- 维护者 Agent 误操作需 op log、撤销 API 与 ACL
- policy 需区分 Writer / Agent 维护者 / 人维护者 密钥
- 人审队列过深可能抵消自动化收益 — 需 product 调优阈值

### 关联

- ADR-002, ADR-005, ADR-007
- pitch.md §核心用户
