# UI i18n Design for ma3 User Portal

> Scope: SSR FastAPI user-facing portal UI implemented with Python HTML strings.
> Target v1 languages: `zh-CN` default and `en-US`.
> Current state: no existing i18n layer; `ui_theme.py` hardcodes `<html lang="zh-CN">`, navigation copy, pagination copy, login/logout labels, and copy button feedback. Portal/key/auth routes embed most page copy inline.

---

## Summary & Decisions Table

ma3 should add a small first-party Python i18n layer for SSR pages instead of introducing Jinja2 or Babel/gettext immediately. The current UI is built from f-strings, `render_page(...)`, `esc(...)`, `badge(...)`, `render_table(...)`, and small render helpers. A custom JSON catalog plus a request-scoped translator fits that style, keeps diffs small, and lets routes migrate incrementally.

| Area | Decision | Rationale |
|---|---|---|
| v1 scope | User-facing portal SSR UI: top nav, account pages, writes/votes, libraries, records, keys, login/auth error pages | Matches current product surface and avoids translating MCP/API contracts or admin-only Observatory internals in v1. |
| Languages | `zh-CN` default, `en-US` secondary | Existing copy and docs are zh-CN-first; English unlocks broader users without changing data model. |
| Locale source | Query param `?lang=zh-CN|en-US` wins and sets cookie; cookie next; `Accept-Language` fallback; default `zh-CN` | Query param enables header switcher and tests. Cookie persists without schema migration. Accept-Language helps first-time anonymous users. |
| Persistence | Cookie-only in v1: `ma3_locale`, `SameSite=Lax`, `HttpOnly=False`, max-age 1 year | Minimal data-model change. User DB preference can be v1.1 if product wants cross-device persistence. |
| Switcher | Add compact header switcher in `render_page(...)` for all non-minimal portal pages and minimal login/auth pages where practical | Locale must be user-visible. Header is shared and stable. |
| i18n API | Add `app/api/ui_i18n.py` with `resolve_locale(request)`, `set_locale_cookie(response, locale)`, `get_translator(request)`, and `tr(locale, key, **params)` | Keeps call sites explicit and avoids globals. |
| Catalog format | JSON dictionaries under `code/server/app/api/i18n/{zh-CN,en-US}.json` | Easy to review, no compile step, no new runtime dependency. |
| Key style | Dot-separated semantic keys: `nav.me`, `portal.me.title`, `writes.table.time`, `common.save` | Stable across copy edits and grouped by route/component. |
| Interpolation | Python `str.format_map` with escaped values at call site policy: `tr()` returns plain text; callers still use `esc()` for untrusted params | Matches existing HTML safety model and avoids marking HTML-safe translations. |
| Plurals | v1 catalog supports `one`/`other` via `tr_count(locale, key, count, **params)`; zh-CN may use same text for both | Needed for English `item/items`, page totals, and future empty states. |
| HTML in translations | Avoid for v1. Compose HTML in Python and translate text fragments only | Safer with current f-string renderer. |
| Fallback behavior | Missing current-locale key falls back to `zh-CN`; missing both renders `[[key]]` in dev/test and logs warning | Default language remains usable and missing keys are visible in tests. |

---

## Locale Detection & Persistence Flow

Supported locale tags are exact BCP-47-ish strings:

- `zh-CN`
- `en-US`

Normalize incoming variants:

- `zh`, `zh-CN`, `zh_CN`, `zh-Hans`, `zh-Hans-CN` -> `zh-CN`
- `en`, `en-US`, `en_US`, `en-GB`, `en-*` -> `en-US`
- Anything else -> unsupported

Detection order for every SSR UI request:

```text
HTTP request
  |
  |-- query param lang?
  |     |-- supported -> locale = normalized lang
  |     |                 response sets ma3_locale cookie
  |     |-- unsupported -> ignore; continue
  |
  |-- cookie ma3_locale?
  |     |-- supported -> locale = cookie
  |     |-- unsupported -> ignore; continue
  |
  |-- Accept-Language?
  |     |-- first supported language by q order -> locale
  |     |-- none supported -> zh-CN
  |
  `-- default zh-CN
```

Implementation rules:

- Query param name: `lang`.
- Cookie name: `ma3_locale`.
- Cookie options: `max_age=31536000`, `samesite="lax"`, `httponly=False`, `secure` only when `settings.public_base_url` starts with `https://` or request scheme is HTTPS.
- The language switcher should preserve the current path and query string except replace/remove `lang`. Example: `/ui/me/writes/?status=buffered&lang=en-US`.
- When `?lang=` is present on a POST redirect target, POST handlers do not need to parse it from forms in Phase 1. The cookie set by the prior GET is enough. For POST validation pages that render inline errors, use `get_translator(request)` from the current request.
- Do not persist locale in the user/principal DB in v1. Add a DB-backed preference only if owner wants cross-device consistency later.

Header switcher behavior:

- Current `zh-CN`: show `EN` link to same URL with `lang=en-US`.
- Current `en-US`: show `中文` link to same URL with `lang=zh-CN`.
- Render inside `.topbar-meta` before account/logout links.
- Minimal header pages should render the switcher when possible, especially auth error/login pages, but Phase 1 can start with `render_page(...)` pages.

---

## API/Surface Area Inventory

### Shared Shell: `code/server/app/api/ui_theme.py`

Current hardcoded strings:

- HTML language: `<html lang="zh-CN">`
- Brand aria label: `ma3 首页`
- Top nav: `我的主页`, `库`, `记录`, `投票`, `API Keys`, `Observatory`
- Account subnav: `概览`, `设置`
- Meta links: `登录`, `账户`, `退出`
- Pagination/list footer: `上一页`, `下一页`, `第 {page} / {total_pages} 页`, `每页 ... 条`, `共 {total_items} 条`
- Copy JS feedback: `已复制`
- Table default empty state: `暂无数据`
- 403 helper title/back labels passed by callers

Design changes:

- `render_page(..., locale: str = "zh-CN", request: Request | None = None)` should render `<html lang="{locale}">`.
- Shared helpers that emit labels should accept `locale` or a translator `t`. Prefer `locale` for smaller call sites:
  - `portal_nav_items(base, *, is_admin, locale="zh-CN")`
  - `render_subnav(base, *, active, locale="zh-CN")`
  - `render_pagination(..., locale="zh-CN")`
  - `render_list_footer(..., locale="zh-CN")`
  - `render_table(..., empty: str | None = None, locale="zh-CN")`
  - `render_page_403(..., locale="zh-CN")`
- Keep `esc()` unchanged.

### Portal Routes: `code/server/app/api/routes_portal.py`

Routes in v1 scope:

- `GET /ui/me`, `/ui/me/`
  - Page title/subtitle, stat labels, section headers, table headers, empty states, CTAs, recent contribution status copy.
- `GET /ui/me/settings/`
  - Display name card, Principal ID explanatory copy, title/subtitle.
- `GET /ui/me/setup/` and `POST /ui/me/setup/`
  - Setup form, validation/error display strings, title/subtitle.
- `GET /ui/me/writes/` and `POST /ui/me/writes/batch/`
  - Page title/subtitle, filter pills, status badges, table headers, batch bar, deleted-record placeholder, validation error.
- `GET /ui/me/votes/`
  - Page title/subtitle, filter pills, table headers, unavailable badge, empty state.
- `GET /ui/libraries/`
  - Page title/subtitle, table headers, empty state.
- `GET /ui/libraries/{library_id}/`
  - Breadcrumb, stats labels where user-facing, access card, login CTA, distribution title, aggregation footnote.
- `GET/POST /ui/libraries/{library_id}/settings/`
  - Owner settings form labels, help text, save/back buttons.
- `GET /ui/records/{record_id}/`
  - Detail page title/subtitle, buffer action card, feedback card, button labels, breadcrumb.

Keep API/HTTP exception details out of scope unless they appear as rendered portal UI. JSON error contracts stay English where already API-like.

### Keys UI: `code/server/app/api/routes_keys.py`

Routes in v1 scope:

- `GET /ui/keys/`, `/ui/keys`
- `GET /ui/keys/{key_id}`
- `POST /ui/keys/create`
- `POST /ui/keys/{key_id}/edit`
- `POST /ui/keys/{key_id}/delete`
- Authing-disabled page rendered by `_render_authing_disabled_page(...)`
- Created page helper `_render_created_page(...)` even if rarely used

Strings:

- Copy buttons, delete confirmations, role labels, grant picker labels/hints, empty states, key list/detail titles/subtitles, save/delete/back buttons, saved/error alerts.

Do not translate JSON APIs under `/api/keys` in v1.

### Auth UI: `code/server/app/api/routes_auth.py`

In v1 scope because these are user-facing login/auth pages:

- `_auth_error_page(...)`
- Login failure title/body/action
- `<html lang="zh-CN">`

Auth redirects and OAuth protocol parameters are not translated.

### Observatory: `code/server/app/api/routes_ui.py`

Mostly non-goal for v1 because this is admin Observatory internals. Trivial shared-shell labels will become localized automatically through `render_page(...)`. Keep Observatory page content in its current mixed Chinese/English form unless owner explicitly prioritizes it.

The non-admin 403 page is visible to regular users. If touched by shared `render_page_403(...)`, translate:

- `Observatory 仅产品管理员可访问。`
- `返回我的主页`

---

## String Key Catalog

Catalog files:

```text
code/server/app/api/i18n/
  zh-CN.json
  en-US.json
```

Key naming:

- `common.*`: shared verbs, generic labels, empty states.
- `nav.*`: top nav and subnav.
- `shell.*`: page shell, pagination, footer, copy JS.
- `auth.*`: login/auth error pages.
- `portal.me.*`: overview/settings/setup.
- `portal.writes.*`: writes list and batch actions.
- `portal.votes.*`: votes list.
- `portal.libraries.*`: library list/detail/settings.
- `portal.records.*`: record detail.
- `keys.*`: API key list/detail/forms.
- `status.*`, `role.*`, `visibility.*`: repeated domain labels where UI needs localization.

Sample v1 catalog keys (more than 30) follow. Implementation should start with these and add keys as pages migrate.

| Key | zh-CN | en-US |
|---|---|---|
| `common.save` | 保存 | Save |
| `common.delete` | 删除 | Delete |
| `common.copy` | 复制 | Copy |
| `common.back` | 返回 | Back |
| `common.login` | 登录 | Sign in |
| `common.logout` | 退出 | Sign out |
| `common.account` | 账户 | Account |
| `common.none` | 无 | None |
| `common.not_available` | 不可用 | Unavailable |
| `common.empty` | 暂无数据 | No data |
| `common.created_at` | 创建时间 | Created |
| `common.last_used_at` | 最后使用 | Last used |
| `shell.brand_aria` | ma3 首页 | ma3 home |
| `shell.copied` | 已复制 | Copied |
| `shell.pagination.prev` | ← 上一页 | ← Previous |
| `shell.pagination.next` | 下一页 → | Next → |
| `shell.pagination.current` | 第 {page} / {total_pages} 页 | Page {page} of {total_pages} |
| `shell.list.total` | 共 {count} 条 | {count} total |
| `shell.list.per_page` | 每页 {sizes} 条 | {sizes} per page |
| `nav.me` | 我的主页 | Home |
| `nav.libraries` | 库 | Libraries |
| `nav.records` | 记录 | Records |
| `nav.votes` | 投票 | Votes |
| `nav.keys` | API Keys | API Keys |
| `nav.observatory` | Observatory | Observatory |
| `nav.overview` | 概览 | Overview |
| `nav.settings` | 设置 | Settings |
| `auth.error.title` | 登录失败 | Sign-in failed |
| `auth.error.retry` | 重新登录 | Try signing in again |
| `auth.error.missing_code` | 缺少 authorization code | Missing authorization code |
| `portal.me.title` | 我的主页 | Home |
| `portal.me.subtitle` | 你在 ma3 的贡献与权限概览。 | Your ma3 contributions and access overview. |
| `portal.me.stats.records` | 记录 | Records |
| `portal.me.stats.buffered` | 待发布 | Pending |
| `portal.me.stats.libraries` | 可访问库 | Accessible libraries |
| `portal.me.stats.votes` | 投票 | Votes |
| `portal.me.stats.keys` | API Keys | API Keys |
| `portal.me.my_libraries` | 我的库 | My libraries |
| `portal.me.recent_contributions` | 最近贡献 | Recent contributions |
| `portal.me.view_all` | 查看全部 → | View all → |
| `portal.me.no_contributions` | 还没有贡献。 | No contributions yet. |
| `portal.me.create_key` | 创建 API key | Create API key |
| `portal.me.onboarding_docs` | 接入文档 | Onboarding docs |
| `portal.settings.title` | 账户设置 | Account settings |
| `portal.settings.subtitle` | 账户与身份信息 | Account and identity |
| `portal.settings.display_name` | 显示名 | Display name |
| `portal.settings.display_name_help` | 注册时设定，之后不可修改。用于门户顶部、个人库名称（「{personal_library_name}」）等。 | Set during registration and cannot be changed later. Used in the portal header, personal library name ("{personal_library_name}"), and more. |
| `portal.settings.principal_help` | ma3 内部身份标识，创建 API key 或排查权限时可能需要。显示名在注册时设定，之后不可修改。 | Internal ma3 identity. You may need it when creating API keys or debugging access. Display name is set during registration and cannot be changed later. |
| `portal.setup.title` | 设定显示名 | Set display name |
| `portal.setup.subtitle` | 注册后一次性设定，之后不可更改。 | Set once after registration. It cannot be changed later. |
| `portal.setup.welcome` | 欢迎加入 ma3。请选择一个显示名：它将出现在门户顶部、个人库名称等位置。 | Welcome to ma3. Choose a display name: it appears in the portal header, personal library name, and more. |
| `portal.setup.unique` | 显示名在 ma3 内全局唯一（不区分大小写） | Display names are globally unique in ma3 (case-insensitive). |
| `portal.setup.immutable` | 设定后不可修改，请谨慎选择 | It cannot be changed after setup, so choose carefully. |
| `portal.setup.input_label` | 显示名（2–32 字符） | Display name (2-32 characters) |
| `portal.setup.submit` | 确认并继续 | Confirm and continue |
| `portal.writes.title` | 记录 | Records |
| `portal.writes.subtitle` | 来自写审计日志；含 API key 写入记录。 | From the write audit log, including API-key writes. |
| `portal.writes.deleted_record` | 记录内容已完全删除，不可显示 | The record content has been fully deleted and cannot be shown |
| `portal.writes.batch_label` | 批量操作 | Batch actions |
| `portal.writes.batch_publish` | 批量发布 | Publish selected |
| `portal.writes.batch_delete` | 批量删除 | Delete selected |
| `portal.writes.select_required` | 请先选择至少一条记录 | Select at least one record first |
| `portal.writes.empty` | 暂无记录 | No records |
| `portal.writes.select_all_page` | 全选本页 | Select all on this page |
| `portal.writes.filter.all` | 全部 | All |
| `portal.writes.filter.active` | 已发布 | Published |
| `portal.writes.filter.buffered` | 待发布 | Pending |
| `portal.writes.filter.deleted` | 已删除 | Deleted |
| `portal.writes.table.time` | 时间 | Time |
| `portal.writes.table.record` | 记录 | Record |
| `portal.writes.table.status` | 状态 | Status |
| `portal.writes.table.library` | 库 | Library |
| `portal.writes.table.kind` | 类型 | Type |
| `portal.votes.title` | 投票 | Votes |
| `portal.votes.subtitle` | 只读列表；改票请进入 record 详情页。 | Read-only list. Open the record detail page to change a vote. |
| `portal.votes.empty` | 还没有投过票 | No votes yet |
| `portal.votes.filter.all` | 全部 | All |
| `portal.votes.filter.up` | 👍 赞同 | 👍 Upvote |
| `portal.votes.filter.down` | 👎 反对 | 👎 Downvote |
| `portal.libraries.title` | 库 | Libraries |
| `portal.libraries.subtitle` | 你有读权限的知识库；仅展示统计，不提供 record 枚举。 | Knowledge libraries you can read. Shows statistics only; record enumeration is not available. |
| `portal.libraries.table.name` | 库名 | Library name |
| `portal.libraries.table.visibility` | 可见性 | Visibility |
| `portal.libraries.table.kind` | 类型 | Type |
| `portal.libraries.table.access` | 我的权限 | My access |
| `portal.libraries.empty` | 暂无库 | No libraries |
| `portal.library.access_title` | 我的访问 | My access |
| `portal.library.permission` | 权限 | Permission |
| `portal.library.bound_keys` | 绑定 key | Bound keys |
| `portal.library.settings` | 库设置 | Library settings |
| `portal.library.buffer_hours` | 写入缓冲期 {hours}h | Write buffer {hours}h |
| `portal.library.login_cta` | 登录以贡献知识、管理 API key 与投票。 | Sign in to contribute knowledge, manage API keys, and vote. |
| `portal.library.distribution` | 分布 | Distribution |
| `portal.library.stats_only_note` | 库内 record 列表仅管理员可枚举；此处仅展示聚合统计。 | Only administrators can enumerate records in this library; this page shows aggregate statistics only. |
| `portal.library.settings_title` | 库设置 | Library settings |
| `portal.library.settings_subtitle` | 写入缓冲期配置 | Write buffer configuration |
| `portal.library.buffer_label` | 写入缓冲期（小时，0 = 关闭） | Write buffer period (hours, 0 = off) |
| `portal.library.buffer_help` | 默认 24。设为 0 时新写入立即发布（active）。 | Default is 24. Set to 0 to publish new writes immediately as active. |
| `portal.library.back_to_detail` | ← 返回库详情 | ← Back to library detail |
| `portal.records.title_prefix` | Record | Record |
| `portal.records.subtitle` | 单条 record 详情。 | Record detail. |
| `portal.records.pending_title` | 待发布 | Pending |
| `portal.records.pending_help` | 仅你可见；到期自动发布，或立即发布 / 修改 / 删除。 | Visible only to you. It will publish automatically when due, or you can publish, edit, or delete it now. |
| `portal.records.publish_now` | 立即发布 | Publish now |
| `portal.records.confirm_delete` | 确定删除？ | Delete this record? |
| `portal.records.save_changes` | 保存修改 | Save changes |
| `portal.records.knowledge_entry` | 知识条目 | Knowledge entry |
| `portal.records.feedback` | Feedback | Feedback |
| `portal.records.clear_vote` | 清除我的投票 | Clear my vote |
| `portal.records.one_vote_help` | 同一用户对同一 record 只能保留一票。 | Each user can keep only one vote per record. |
| `portal.records.back_home` | ← 我的主页 | ← Home |
| `keys.title` | API Keys | API Keys |
| `keys.subtitle` | 管理 MCP 调用用的 API key；点击名称进入详情页修改权限。 | Manage API keys for MCP calls. Click a name to edit grants on the detail page. |
| `keys.management` | Key 管理 | Key management |
| `keys.personal_library` | 个人库 | Personal library |
| `keys.create_new` | 创建新 key | Create new key |
| `keys.empty` | 暂无 API key | No API keys |
| `keys.empty_hint` | 创建第一把 key 后，把它填入 agent MCP 配置的 X-API-Key。 | After creating your first key, put it in the agent MCP configuration as X-API-Key. |
| `keys.grants` | 知识库权限 | Library grants |
| `keys.saved` | 已保存 | Saved |
| `keys.back_to_list` | ← 返回列表 | ← Back to list |
| `keys.delete_key` | 删除 key | Delete key |
| `keys.delete_confirm` | 删除后 key 立即失效，无法恢复。确定？ | This key will stop working immediately and cannot be recovered. Continue? |
| `keys.delete_help` | 删除后此 key 立即失效，无法恢复。历史写入记录仍保留。 | Deleting this key disables it immediately and cannot be undone. Historical writes are retained. |
| `keys.old_key_hint` | 旧 key 无存储副本；如需复制完整 key，请创建新 key 后删除旧 key | Old keys do not have stored plaintext. Create a new key and delete the old one if you need to copy a full key. |
| `keys.authing_disabled.title` | API Keys | API Keys |
| `keys.authing_disabled.subtitle` | 自助注册未启用 | Self-service registration is disabled |
| `keys.authing_disabled.alert` | 本实例未配置 Authing，自助注册/API key 管理不可用。 | Authing is not configured for this instance. Self-service registration and API key management are unavailable. |
| `keys.authing_disabled.observatory` | 前往 Observatory | Go to Observatory |
| `role.reader` | 只读 | Read-only |
| `role.writer` | 读写 | Read/write |
| `role.none` | 无 | None |
| `status.deleted` | 已删除 | Deleted |
| `status.buffered` | 待发布 | Pending |
| `status.active` | active | active |

Notes:

- Keep domain values like `active`, `draft`, `invalid`, `reader`, `writer`, and raw IDs unchanged when they are data values rather than labels. Translate only the surrounding UI label or badge if product wants that user-facing abstraction.
- Existing mixed English terms (`API Keys`, `Record`, `MCP`, `Problem`, `Outcome`, `Summary`, `Cases`) may remain English in zh-CN where they are product/domain terms. The catalog still lets en-US use the same text.
- For strings with HTML emphasis today, split into plain fragments or keep the emphasis in code:

```python
t = get_translator(request)
body = f"<p>{esc(t('portal.setup.welcome_prefix'))}<strong>{esc(t('portal.setup.display_name_term'))}</strong>{esc(t('portal.setup.welcome_suffix'))}</p>"
```

Prefer simpler plain text when emphasis is not required.

---

## Code Architecture

### New Module: `code/server/app/api/ui_i18n.py`

Add a focused module with no web framework side effects:

```python
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from fastapi import Request
from fastapi.responses import Response

SUPPORTED_LOCALES = ("zh-CN", "en-US")
DEFAULT_LOCALE = "zh-CN"
LOCALE_COOKIE = "ma3_locale"

def normalize_locale(value: str | None) -> str | None: ...
def parse_accept_language(value: str | None) -> str | None: ...
def resolve_locale(request: Request) -> str: ...
def locale_switch_url(request: Request, target_locale: str) -> str: ...
def set_locale_cookie(response: Response, locale: str, request: Request) -> None: ...
def catalog(locale: str) -> dict[str, Any]: ...
def tr(locale: str, key: str, **params: Any) -> str: ...
def tr_count(locale: str, key: str, count: int, **params: Any) -> str: ...
def get_translator(request: Request) -> Callable[..., str]: ...
```

Expected behavior:

- `catalog(locale)` loads JSON lazily with `@lru_cache`.
- `tr(locale, key, **params)`:
  - Looks up current locale.
  - Falls back to `zh-CN`.
  - Logs missing keys once per process if both are missing.
  - Formats with `.format_map(_SafeDict(params))`.
  - Does not HTML-escape. Callers keep using `esc(...)` for user-controlled params.
- `tr_count(locale, key, count, **params)`:
  - Reads `{ "one": "...", "other": "..." }` values when present.
  - English uses `one` when `count == 1`, else `other`.
  - Chinese can map both to the same phrase.

### Request Integration

Add a small helper to avoid repeated boilerplate:

```python
def ui_locale(request: Request) -> tuple[str, Callable[..., str]]:
    locale = resolve_locale(request)
    return locale, lambda key, **params: tr(locale, key, **params)
```

Route usage:

```python
locale, t = ui_locale(request)
body = f"""
  <div class="card-header"><h2>{esc(t("portal.me.my_libraries"))}</h2></div>
"""
html = render_page(
    title=t("portal.me.title"),
    subtitle=t("portal.me.subtitle"),
    base=base,
    active_nav="me",
    user_line=ui_user_line(user),
    show_logout=True,
    is_admin=user.is_admin,
    body=body,
    locale=locale,
    request=request,
)
response = HTMLResponse(html)
maybe_set_locale_cookie(response, request, locale)
return response
```

To keep the migration smaller, add:

```python
def html_response(request: Request, html: str, *, status_code: int = 200) -> HTMLResponse:
    response = HTMLResponse(html, status_code=status_code)
    locale = resolve_locale(request)
    if request.query_params.get("lang") is not None:
        set_locale_cookie(response, locale, request)
    return response
```

Then migrated routes can return `html_response(request, render_page(...))`.

### `ui_theme.py` Changes

Minimal signature changes:

```python
def portal_nav_items(base: str, *, is_admin: bool, locale: str = DEFAULT_LOCALE) -> list[tuple[str, str, str, bool]]:
    return [
        ("me", tr(locale, "nav.me"), f"{base}/ui/me/", False),
        ...
    ]

def render_page(..., locale: str = DEFAULT_LOCALE, request: Request | None = None) -> str:
    ...
    switcher = render_locale_switcher(request, locale) if request else ""
    ...
    return f"""<!DOCTYPE html>
<html lang="{esc(locale)}">
...
<a class="brand" ... aria-label="{esc(tr(locale, "shell.brand_aria"))}">
...
"""
```

Add `render_locale_switcher(request, locale)` in `ui_i18n.py` or `ui_theme.py`. Prefer `ui_i18n.py` for URL/query handling, called by `ui_theme.py`.

Copy JS:

- Current JS embeds `btn.textContent = '已复制';`.
- In Phase 1, make `MA3_COPY_JS` a function:

```python
def render_copy_js(locale: str) -> str:
    copied = json.dumps(tr(locale, "shell.copied"), ensure_ascii=False)
    return MA3_COPY_JS_TEMPLATE.replace("__COPIED__", copied)
```

Then `render_page(...)` emits `<script>{render_copy_js(locale)}</script>`.

### Auth Page Integration

`routes_auth.py` currently has standalone HTML. Either:

1. Convert `_auth_error_page(...)` to use `render_page(..., show_minimal_header=True, locale=locale, request=request)`; or
2. Keep standalone HTML but call `resolve_locale(request)`, translate title/action, and set `<html lang>`.

Prefer option 1 for consistency if it does not pull in unwanted nav; `show_minimal_header=True` already supports a minimal header.

### Files to Add/Modify

Add:

- `code/server/app/api/ui_i18n.py`
- `code/server/app/api/i18n/zh-CN.json`
- `code/server/app/api/i18n/en-US.json`
- `code/server/tests/integration/test_ui_i18n.py`

Modify Phase 1:

- `code/server/app/api/ui_theme.py`
- `code/server/app/api/routes_portal.py`
- `code/server/app/api/routes_keys.py`
- `code/server/app/api/routes_auth.py`

Optional v1.1:

- `code/server/app/api/routes_ui.py` for Observatory content if owner wants admin localization.

### Safety Rules

- `tr()` returns plain text. Any user-controlled interpolation must be escaped by the caller:

```python
esc(t("portal.settings.display_name_help", personal_library_name=f"{user.display_name} 的个人库"))
```

- Do not store HTML in JSON catalogs for v1.
- Do not translate API JSON response fields, MCP tool messages, exception details used by API clients, or database values.
- Do not change URL paths. Locale is query/cookie only.
- Keep `zh-CN` as full fallback so Phase 1 can ship with partially migrated pages.

---

## Implementation Phases

### Phase 1: Shippable Minimum

Goal: language selection works and the most-used user portal pages render zh-CN/en-US without changing data models or route structure.

Touch:

- `ui_i18n.py` and catalog files.
- `ui_theme.py` shared shell:
  - `<html lang>`
  - nav/subnav
  - account/login/logout links
  - pagination/list footer
  - table default empty
  - copy feedback
  - language switcher
- `routes_portal.py`:
  - `/ui/me/`
  - `/ui/me/settings/`
  - `/ui/me/setup/`
  - `/ui/me/writes/`
  - `/ui/me/votes/`
- `routes_keys.py`:
  - `/ui/keys/`
  - `/ui/keys/{key_id}`
  - authing-disabled page
- `routes_auth.py` auth error page.
- Tests for zh/en on representative pages.

Phase 1 acceptance:

- `GET /ui/me/?lang=en-US` sets `ma3_locale=en-US`, emits `<html lang="en-US">`, shows `Home`, `Libraries`, `Records`, `Votes`, `Account`, `Sign out`.
- `GET /ui/me/` after that cookie stays English.
- `GET /ui/me/?lang=zh-CN` switches back to Chinese and sets cookie.
- `Accept-Language: en-US,en;q=0.9` renders English for first-time users without cookie.
- Writes/votes list filters and table headers are localized.
- Keys list/detail primary labels are localized.
- Existing zh-CN tests remain stable or are updated to assert default locale explicitly.

### Phase 2: Complete Portal Surface

Touch:

- `routes_portal.py` library list/detail/settings and record detail.
- Remaining helper labels in `routes_portal.py`, including buffer actions and feedback copy.
- Shared status/role/visibility display helpers if repeated enough.

Deliverables:

- Translate all v1 user-facing portal SSR pages named in the scope.
- Add tests for library detail/settings and record detail.
- Add a missing-key test that scans migrated pages for `[[`.

### Phase 3: Cleanup and Guardrails

Touch:

- Add a catalog completeness test: every key in `zh-CN.json` exists in `en-US.json` and vice versa.
- Add a hardcoded Chinese string audit test for `code/server/app/api/ui_theme.py`, `routes_portal.py`, `routes_keys.py`, and `routes_auth.py` with an allowlist for test data/domain terms.
- Consider extracting repeated route-local patterns:
  - `status_badge(locale, status, deleted=False)`
  - `role_label(locale, role)`
  - `render_filter_pills(..., locale=locale)`

### Phase 4: Optional Owner Decisions

Only if requested:

- Store `preferred_locale` on principal/user profile for cross-device persistence.
- Translate Observatory internals.
- Translate email templates or future notifications.
- Introduce Babel/gettext if catalogs grow enough to need translator tooling.

---

## Testing

Add `code/server/tests/integration/test_ui_i18n.py`. Use existing `authing_portal_client` fixtures where possible.

Recommended tests:

1. Default locale is zh-CN:
   - `GET /ui/me/`
   - Assert `<html lang="zh-CN">`, `我的主页`, `库`, `记录`, `投票`, `退出`.

2. Query param switches and sets cookie:
   - `GET /ui/me/?lang=en-US`
   - Assert `<html lang="en-US">`, `Home`, `Libraries`, `Records`, `Votes`, `Sign out`.
   - Assert response `set-cookie` includes `ma3_locale=en-US`.

3. Cookie persists:
   - Set `ma3_locale=en-US`.
   - `GET /ui/me/writes/`
   - Assert `Records`, `All`, `Published`, `Pending`, `Deleted`, `Batch actions`, `Time`, `Status`.

4. Query param overrides cookie:
   - Cookie `ma3_locale=en-US`.
   - `GET /ui/me/votes/?lang=zh-CN`
   - Assert `<html lang="zh-CN">`, `投票`, `赞同`, `反对`.

5. Accept-Language fallback:
   - No cookie.
   - Header `Accept-Language: en-US,en;q=0.8,zh-CN;q=0.5`.
   - `GET /ui/me/`
   - Assert English.

6. Unsupported locale falls back:
   - `GET /ui/me/?lang=fr-FR`.
   - Assert zh-CN default and no `ma3_locale=fr-FR` cookie.

7. Keys pages:
   - Cookie `ma3_locale=en-US`.
   - `GET /ui/keys/`
   - Assert `Key management`, `Create new key`, `Personal library`, `Library grants`.

8. Auth error page:
   - Trigger or directly request a known auth error path if existing tests permit.
   - Assert `<html lang="en-US">` and `Sign-in failed` when `?lang=en-US` or cookie is present.

9. Catalog completeness:
   - Load both JSON files.
   - Assert equal key sets after flattening.
   - Assert every value is a non-empty string or valid plural object.

10. No missing key markers on migrated pages:
   - Fetch `/ui/me/`, `/ui/me/settings/`, `/ui/me/writes/`, `/ui/me/votes/`, `/ui/keys/` in both locales.
   - Assert `"[[` not in response text.

Existing tests with Chinese assertions should either keep default zh-CN or be updated to use explicit default behavior. Avoid making tests depend on machine/browser `Accept-Language`; TestClient requests without that header should remain zh-CN.

---

## Acceptance Criteria

### I18N-1 Locale Resolution

Given a request with `?lang=en-US`, the UI resolves locale `en-US`, renders `<html lang="en-US">`, and sets `ma3_locale=en-US`.

### I18N-2 Default zh-CN

Given no query, no cookie, and no supported `Accept-Language`, the UI renders zh-CN and `<html lang="zh-CN">`.

### I18N-3 Cookie Persistence

Given `ma3_locale=en-US`, subsequent SSR UI GET requests render English without requiring `?lang=en-US`.

### I18N-4 Query Overrides Cookie

Given `ma3_locale=en-US` and `?lang=zh-CN`, the request renders zh-CN and updates the cookie to `zh-CN`.

### I18N-5 Accept-Language Fallback

Given no locale cookie and `Accept-Language: en-US,en;q=0.9`, first-time UI GET requests render English.

### I18N-6 Header Switcher

Every migrated `render_page(...)` user portal page shows a language switcher in the top bar that links to the same path/query with the alternate supported locale.

### I18N-7 Shared Shell Localized

Top nav, account/logout/login links, account subnav, pagination, list footer, table empty state, brand aria label, and copy-button feedback are localized.

### I18N-8 Overview Localized

`/ui/me/` localizes page title/subtitle, stat labels, card headers, table headers, empty state, and CTAs in both zh-CN and en-US.

### I18N-9 Settings and Setup Localized

`/ui/me/settings/` and `/ui/me/setup/` localize explanatory text, form labels, buttons, and page metadata in both locales.

### I18N-10 Writes Localized

`/ui/me/writes/` localizes filters, sortable table headers, status badges controlled by UI, batch operation labels, deleted-record placeholder, empty state, and selection error.

### I18N-11 Votes Localized

`/ui/me/votes/` localizes filters, table headers, unavailable badge, empty state, and page metadata.

### I18N-12 Keys Localized

`/ui/keys/` and `/ui/keys/{key_id}` localize key management headings, grant picker labels, role labels, empty states, save/delete/copy controls, confirmations, and authing-disabled page text.

### I18N-13 Auth Error Localized

Auth error pages render the resolved locale, localized title/action, and no longer hardcode `<html lang="zh-CN">`.

### I18N-14 Catalog Fallback

Missing en-US keys fall back to zh-CN; missing keys in both catalogs emit a visible `[[key]]` marker in dev/test and log a warning.

### I18N-15 HTML Safety Preserved

Translated text is treated as plain text. User-controlled interpolation remains escaped with `esc(...)`, and catalogs do not contain arbitrary HTML.

### I18N-16 No API Contract Change

MCP responses, JSON API responses, and machine-readable error contracts do not change as part of UI i18n.

### I18N-17 Incremental Migration

Partially migrated pages continue rendering because `zh-CN` fallback exists and helper signatures have defaults.

### I18N-18 Tests

Pytest coverage verifies zh-CN/en-US rendering for overview, writes, votes, keys, locale persistence, query override, Accept-Language fallback, catalog completeness, and no missing-key markers on Phase 1 pages.

---

## Open Questions for Owner

1. Should English copy keep product terms as `Record`, `Library`, `API Key`, `MCP`, `Problem`, `Outcome`, and `Summary`, or should some be more user-friendly (`Entry`, `Knowledge library`, etc.)?
2. Should the language switcher label be `EN/中文`, `English/中文`, or a dropdown? The minimal recommendation is a single alternate-language link.
3. Should anonymous public library pages persist locale by cookie even before login? Recommendation: yes, because it is not user-identifying by itself and keeps behavior consistent.
4. Should per-user DB persistence be added in v1.1 for cross-device locale preference? Recommendation: defer until a broader account preferences model exists.
5. Should non-admin Observatory 403 be considered portal scope? Recommendation: translate it via shared `render_page_403(...)`; leave admin dashboard internals untranslated.
6. Should Chinese use `API key` or `API Key` consistently? Current code uses both `API key` and `API Keys`; recommendation: use `API key` in prose and `API Keys` in nav/title.
7. Should validation errors from services, currently raised as `HTTPException(detail=...)`, be mapped to UI translation keys when rendered inside forms? Recommendation: only map known user-facing form errors in v1; keep API exception details unchanged.
8. Should locale be reflected in canonical URLs? Recommendation: no. Use query param only for switching and cookie for persistence.

---

## Non-Goals

- RTL languages and layout changes for bidirectional text.
- Full Observatory/admin dashboard localization.
- MCP tool responses, JSON API responses, or SDK/client protocol messages.
- Email templates or notification templates.
- Replacing f-string SSR rendering with Jinja2 or a SPA.
- Database-backed locale preference in v1.
- Translating user-generated content, library names, record content, API key labels, principal/display names, or raw domain IDs.
