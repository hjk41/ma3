# API Key 页面布局指南（fable）

对象：`/ui/keys/`（列表）与 `/ui/keys/{key_id}`（详情）。
参照物：GitHub Personal Access Token 管理页。区别：ma3 的 key 明文可重复展示
（服务端加密存储），所以列表页可以直接提供「复制」，这是比 GitHub 更宽松的模型，
布局上要利用它，而不是照抄 GitHub 的 "只显示一次" 流程。

代码位置：

- 列表 `_render_keys_page` / 详情 `_render_key_detail_page`（`code/server/app/api/routes_keys.py`）
- 样式 `MA3_CSS`（`code/server/app/api/ui_theme.py`）
- 复制脚本 `ma3CopyFrom`：取按钮的 `previousElementSibling` 作为文本源，
  行内复制按钮前面必须紧邻一个 hidden/readonly input。

## 1. 列表页 `/ui/keys/`

### 线框

```
┌─ Key 管理 ──────────────────────────────────────────────────────────┐
│ Name          Prefix      Grants           Last used   Actions      │
│ ─────────────────────────────────────────────────────────────────── │
│ my-laptop     ma3_ab12…   个人库(读写),…   2026-07-03   [复制] [删除] │
│ ci-agent      ma3_cd34…   Community(读写)  —            [复制] [删除] │
│ ─────────────────────────────────────────────────────────────────── │
│ Label [my-laptop-agent      ] [创建新 key]                          │
│ (grant picker)                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

要点：

- 列：`Name | Prefix | Grants | Created | Last used | Actions`。Actions 是最后一列，
  表头留空字符串即可（GitHub 也不给操作列起名）。若嫌拥挤，Created 可以去掉，
  Last used 比 Created 对用户更有决策价值（"这把 key 还有人用吗"）。
- Name 保持现有 `key-link` 可点击进详情，这是行的主动作；
  Actions 列只放两个小按钮：
  - **复制**：`<input type="text" class="copy-src" hidden readonly value="...">` +
    `<button class="btn sm" onclick="ma3CopyFrom(this)">复制</button>`。
    注意 hidden input 必须是按钮的直接前一个兄弟节点，否则 `ma3CopyFrom` 取不到值。
    （`document.execCommand('copy')` 对 `hidden` 属性的 input 可能失效；
    更稳妥的做法是 `class="copy-src"` + CSS `position:absolute; left:-9999px`，
    或让 `ma3CopyFrom` 支持 `data-copy` 属性。实现时二选一，别两个都做。）
  - **删除**：行内 `<form method="post" action=".../delete">` + `btn sm danger`，
    加 `onsubmit="return confirm('删除后 key 立即失效，无法恢复。确定？')"`。
    列表页删除必须有 confirm，因为没有详情页那样的上下文缓冲。
- 旧 key（无 `plaintext_key`）复制按钮不渲染，只渲染删除，不要渲染 disabled 按钮
  再配 tooltip——SSR 页面 tooltip 可发现性差，缺席比禁用更清楚。

### 需要的 CSS

```css
/* 操作列：不换行、靠右、行 hover 前弱化 */
table.data td.cell-actions { white-space: nowrap; text-align: right; }
.cell-actions form { display: inline; margin-left: 6px; }
.btn.sm { padding: 3px 10px; font-size: 12px; }
.copy-src { position: absolute; left: -9999px; }  /* 供 execCommand 选中 */
```

`render_table` 目前对所有 cell 一视同仁，无法给单列加 class。两个选项：
给最后一列包一层 `<div class="cell-actions">`（零改动 `render_table`，推荐），
或给 `render_table` 加 `cell_classes` 参数（改动面大，不值得）。

## 2. 详情页 `/ui/keys/{key_id}`

### 线框

```
API Keys / my-laptop                        ← breadcrumb

┌─ my-laptop ─────────────────────────────────────────────┐
│ Key                                                     │
│ [ma3_xxxxxxxxxxxxxxxx        ] [复制]                    │
│                                                         │
│ Prefix    ma3_ab12                                      │
│ Created   2026-07-01                                    │
│ Last used 2026-07-03                                    │
│ ─────────────────────────────────────────────────────── │
│ <form method="post" action=".../edit">   ← 单一表单开始  │
│ Label                                                   │
│ [my-laptop                    ]                         │
│                                                         │
│ 知识库权限                                               │
│ ┌──────────────────────┬────────┐                       │
│ │ Community Library    │ [读写▾] │                       │
│ │ 个人库 lib_xxx        │ [读写▾] │                       │
│ └──────────────────────┴────────┘                       │
│ ─────────────────────────────────────────────────────── │
│ [← 返回列表]                    [保存]  ← form-footer    │
│ </form>                                                 │
│ ─────────────────────────────────────────────────────── │
│ ┌─ 危险操作 ────────────────────────────────┐            │
│ │ 删除后此 key 立即失效，无法恢复。 [删除 key] │            │
│ └───────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────┘
```

要点：

- **一个 `<form>` 包住 label 输入和 grant picker**，一个 `保存` 按钮（`btn primary`）
  放在表单底部 footer。GitHub 的 token 编辑页就是单表单 + 底部单个 "Update token"。
- 后端合并：新增 `POST /ui/keys/{key_id}/edit` 同时处理 label + grants
  （内部就是现有 `normalize_key_label` + `_grants_from_form` 两步），
  旧的 `/label`、`/grants` 端点直接删掉——项目未上线，无需兼容期。
  失败时带着用户填写的值重渲染详情页，不要丢输入。
- 只读事实（Key 明文、Prefix、Created、Last used）放表单**外**、页面上部；
  可编辑字段（Label、权限）放表单内。读/写分区让用户扫一眼就知道哪里能改。
- 删除移出普通按钮排，放独立的「危险操作」区块（GitHub Danger Zone 模式）：
  红边框小卡片 + 一句后果说明 + `btn danger`，加 `onsubmit confirm`。
  它必须是独立 `<form>`，不能嵌在编辑表单里（嵌套 form 是非法 HTML，
  且回车提交会歧义）。
- `← 返回列表` 是链接不是提交，放 footer 左侧与 `保存` 对齐，视觉上主次分明
  （次要动作靠左、主动作靠右，和 GitHub 一致）。

### 需要的 CSS

```css
.form-footer {
  display: flex; justify-content: space-between; align-items: center;
  margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border-muted);
}
.danger-zone {
  margin-top: 24px; border: 1px solid #ffbbb9; border-radius: var(--radius-lg);
  padding: 14px 16px; display: flex; justify-content: space-between;
  align-items: center; gap: 12px;
}
.danger-zone .zone-text { color: var(--text-muted); font-size: 13px; }
```

现有 `.key-detail-actions` 被 `.form-footer` + `.danger-zone` 取代后可删除。
`.key-label-row` 里的 `保存名称` 按钮随合并一起删除。

## 3. 避免的做法

- **不要**在列表行内放「复制后自动展开明文」的交互——行内 hidden input 足够，
  展示明文留给详情页。
- **不要**给详情页保留两个保存按钮再做视觉弱化，直接合并端点；
  半合并（一个按钮提交两个表单的 JS hack）在 SSR 无 JS 依赖的架构里是倒退。
- **不要**把删除按钮和保存按钮并排放在同一 footer。误触成本不对称的动作
  必须物理隔离。
- **不要**在操作列使用图标-only 按钮。当前 UI 没有 icon 体系，文字按钮
  （复制/删除）在 13px 表格里完全放得下。
- **不要**为窄屏做操作列折叠菜单（kebab menu）。SSR 无 JS 组件库，
  `table-wrap` 已有横向滚动兜底。

## 4. 给实现者的五条规则

1. 列表 Actions 列 = 复制（hidden copy-src input 紧贴按钮之前，适配
   `ma3CopyFrom` 的 `previousElementSibling` 约定）+ 删除（行内 form +
   `confirm`）；无明文的旧 key 不渲染复制按钮。
2. 详情页合并为单一 `<form>` → `POST /ui/keys/{key_id}/edit`，一个
   `保存`（btn primary）在 `form-footer` 右侧；删掉 `/label`、`/grants`
   两个端点和「保存名称/保存权限」按钮。
3. 删除在详情页放独立 `danger-zone` 区块（独立 form，不嵌套），
   在两处（列表行、详情）都加 `onsubmit confirm`。
4. 新增 CSS：`.btn.sm`、`.cell-actions`、`.copy-src`（offscreen 而非
   `hidden` 属性，保证 execCommand 回退可用）、`.form-footer`、
   `.danger-zone`；删除 `.key-detail-actions`、`.key-label-row`。
5. 只读信息（Key/Prefix/Created/Last used）在表单外的页面上部，
   可编辑字段全部在表单内；编辑失败时回填用户输入重渲染，不丢状态。
