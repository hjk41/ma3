# Review — 15-user-portal-fable — sonnet-5

> **📚 历史评审** — 实现真源见 [00-design-index-fable.md](00-design-index-fable.md)

> Reviewer: sonnet-5  
> Scope: [15-user-portal-fable.md](15-user-portal-fable.md) against ADR-005, ADR-011, design/08, live code as of 2026-07-04  
> Method: claims cross-checked against `routes_ui.py`, `routes_keys.py`, `security.py`, `feedback_service.py`, `db.py`, `config.py`, `authing_client.py`

## 1. Verdict

**REQUEST-CHANGES**

大方向对：门户与 admin Observatory 分离、records 独立 URL、org/browse 等 Phase 4 能力 defer。但有两处与**当前代码**对撞会产生正确性 bug，一处是**部署锁死**风险（空 admin 白名单），且六条决策未覆盖 record 路由鉴权级别、LAN 无 Authing 分支、nav 硬编码、测试计划。

## 2. Blocking Issues

### B1 — Observatory admin-only + 空 `MA3_AUTH_ADMIN_USERS` = 全员锁死

`auth_admin_users` 默认空 tuple（`config.py` L101）；`is_admin` 仅在此非空时可能为 true（`authing_client.py` L130–133）。Observatory 今天只检查「有无 session」，不检查 admin。

若 literal 实现「admin-only + is_admin」且 deploy 忘记设 `MA3_AUTH_ADMIN_USERS`（`deploy/README.md` 门禁表也未列此项），**每个登录用户（含部署者）都会被拒** — 比今天更糟。

另：`authing_configured=False`（LAN dev）时 today Observatory 完全开放（`routes_ui.py` L124–126）；`test_smoke.py` 在此模式跑。fable 未说明 admin 门控是否适用于 LAN。

**Fix**：(1) 明确 Authing on/off 两套行为；(2) `ma3_doctor` 在 `authing_configured && !auth_admin_users` 时 warn 或 refuse boot；(3) 加「已登录非 admin 被拒」集成测试（今天只有 anonymous 302 测试）。

### B2 — `list_entitled_libraries` 不能仅是 key grants 并集

design-08 §3.3：Layer 1 entitlement（principal 被允许接触的库）≠ Layer 2 key grants。

纯 key grants 启发式的问题：

- 首登后 `ensure_personal_library` 已运行，但用户尚未建 key → 个人库不在列表 → 看自己 personal record 404。
- ADR-011：任何已认证 principal 对 `lib_default` 有 Layer-1 entitlement；仅 personal-grant 的 key 用户不应在门户里「看不到 Community」。

**Fix**（v1，无新表）：

```python
def list_entitled_libraries(principal_id: str) -> set[str]:
    libs = {settings.default_library_id}
    personal = db.find_personal_library(principal_id)
    if personal:
        libs.add(personal["library_id"])
    for key in db.list_api_keys_for_principal(principal_id):
        for grant in db.get_api_key_grants(key["key_id"]):
            libs.add(grant["library_id"])
    return libs
```

### B3 — 「key grants 并集」在代码里不存在，语义未定义

`McpAuthContext.readable_library_ids` 是**单 key** 解析（`security.py` L153–165）。门户 session 无 X-API-Key，必须新写 union 逻辑。须明确：revoked key 是否计入（应否）、reader vs writer grant 是否都算 entitled（应都算 read）。

### B4 — record 迁移后 feedback 鉴权级别未声明

若只 admin-gate Observatory 而不迁 record，会 admin-gate 社区投票 — 与 ADR-005 贡献者场景冲突。须写一句：`/ui/records/{id}` GET + feedback POST 要求**任意 authenticated session**，与 Observatory `is_admin` 解耦。

未决：未登录访客能否**只读** public active Community record（「给 agent 可 cite 的 URL」动机）？

### B5 — 旧路径兼容

`routes_ui.py` L151 硬编码 `/ui/observatory/records/{id}/feedback`。迁移须 301 GET + 退役旧 POST；202 已有 live 数据。

### B6 — 无测试计划

缺：admin-only Observatory（logged-in non-admin）；cross-principal record 404；zero-key 首登 entitlement；record 迁移 redirect。

## 3. Non-Blocking Nits

1. `ui_theme.py` nav 硬编码 observatory+keys — 参数化是第一个 PR，应列入 diff 清单。
2. 无 root `/` 路由 — 「默认落地」是 nav 改序还是新 `GET /` redirect，影响面不同。
3. `/ui/me/` 在 `not authing_configured` 时行为未定义（keys 页有 503 模板可复用）。
4. 非 active record 是否只对 maintainer 可见 — 迁移时一句话定夺。
5. admin-gate Observatory 是否也「修复」今天任何登录用户看全平台 org/user 表的 over-exposure — 应说明动机。

## 4. What I Agree With

1. admin 遥测 vs 单条 record 分离 — 今天 observatory_home 对任何 session 暴露全 org/user 表，过大。
2. `/ui/records/{id}` 解决 citation URL 缺失 — acceptance journey 已有 agent 编造 URL 的证据。
3. `is_admin` 保持 env allowlist，不与 library `role=admin` 混同。
4. defer org pages / community browse — Phase 4 服务不存在，design-13 keys UI 已证明「先 ship 小切片」可行。

## 5. Scope Check

v1 边界合理；under-specification 在 `list_entitled_libraries`（B2/B3）和 admin 门控 LAN/空白名单（B1），不是 scope creep。

## 6. Disagreements with Fable

### D1 — 空 admin 白名单时的降级策略

| | |
|---|---|
| **Fable** | `is_admin` 门控 Observatory |
| **Sonnet-5** | 空 allowlist + Authing on = 锁死；须 doctor warn / bootstrap admin / 或仅 Authing on 时门控 |
| **选项** | (i) warn only (ii) refuse boot (iii) `MA3_BOOTSTRAP_ADMIN_SUB` 临时 admin |
| **严重度** | **需产品负责人决策** |

### D2 — Community Library 是否无条件出现在门户可读集

| | |
|---|---|
| **Fable** | v1 启发式 = personal + key grants（§8.2 已修正为含 default） |
| **Sonnet-5** | 必须 unconditional 含 `lib_default`（ADR-011 Layer-1）；否则与「仅 personal key」用户矛盾 |
| **备选** | 若产品故意「门户只见 key 已 grant 的库」，须 explicit 写为 privacy 策略 |
| **严重度** | **需产品负责人决策**（fable §8.2 已采纳 sonnet 公式；若你同意则关闭） |

### D3 — 未登录只读 public record

| | |
|---|---|
| **Fable** | 未明确（隐含需 session，与 today 一致） |
| **Sonnet-5** | 窄 case：仅 `lib_default` + active 可匿名读，便于 cite；投票仍要 session |
| **严重度** | **需产品负责人决策** |

### D4 — Observatory 非 admin：302 vs 403

与 GPT-5.5 D1 相同 — **需产品负责人决策**。

### D5 — 301 旧 record 路径

工程卫生，非产品决策 — 必须做，fable 已写 301。
