"""Shared SSR UI theme for Observatory and account pages (GitHub-inspired)."""
from __future__ import annotations

import html
import json
from typing import Any, Iterable
from urllib.parse import urlencode

from fastapi import Request

from app.api.ui_i18n import DEFAULT_LOCALE, tr
from app.core.config import settings


def esc(value: Any) -> str:
    return html.escape(str(value))


MA3_BRAND_SVG = """
<svg class="brand-icon" xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 36 36" role="img" aria-label="ma3">
  <defs>
    <linearGradient id="ma3-brand-g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#218bff"/>
      <stop offset="1" stop-color="#0969da"/>
    </linearGradient>
  </defs>
  <rect width="36" height="36" rx="9" fill="url(#ma3-brand-g)"/>
  <g stroke="#ffffff" stroke-width="2" fill="none">
    <path d="M11 24 L18 11 L25 24 Z" stroke-linejoin="round"/>
  </g>
  <circle cx="11" cy="24" r="2.8" fill="#ffffff"/>
  <circle cx="18" cy="11" r="2.8" fill="#ffffff"/>
  <circle cx="25" cy="24" r="2.8" fill="#ffffff"/>
  <text x="18" y="31.5" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="9.5" font-weight="700" letter-spacing="0.4">
    <tspan fill="#ffffff">ma</tspan><tspan fill="#b6e3ff">3</tspan>
  </text>
</svg>
"""

MA3_CSS = """
:root {
  color-scheme: light;
  --bg: #f6f8fa;
  --surface: #ffffff;
  --surface-muted: #f6f8fa;
  --border: #d0d7de;
  --border-muted: #eaeef2;
  --text: #1f2328;
  --text-muted: #656d76;
  --text-subtle: #57606a;
  --accent: #0969da;
  --accent-hover: #0550ae;
  --accent-soft: #ddf4ff;
  --success: #1a7f37;
  --success-soft: #dafbe1;
  --warning: #9a6700;
  --warning-soft: #fff8c5;
  --danger: #cf222e;
  --danger-soft: #ffebe9;
  --shadow-sm: 0 1px 0 rgba(31,35,40,0.04);
  --shadow-md: 0 8px 24px rgba(140,149,159,0.2);
  --radius: 6px;
  --radius-lg: 12px;
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", Helvetica, Arial, sans-serif;
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: var(--font);
  font-size: 14px;
  line-height: 1.5;
  color: var(--text);
  background: var(--bg);
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
code, .mono {
  font-family: var(--mono);
  font-size: 12px;
  background: var(--surface-muted);
  border: 1px solid var(--border-muted);
  border-radius: 4px;
  padding: 0.1em 0.35em;
}
.topbar {
  background: #24292f;
  color: #f0f6fc;
  border-bottom: 1px solid rgba(255,255,255,0.08);
}
.topbar-inner, .page, .footer-inner {
  max-width: 1280px;
  margin: 0 auto;
  padding: 0 24px;
}
.topbar-row {
  display: flex;
  align-items: center;
  gap: 16px;
  min-height: 56px;
}
.brand {
  display: inline-flex;
  align-items: center;
  color: #f0f6fc;
  text-decoration: none;
  flex-shrink: 0;
}
.brand:hover { text-decoration: none; }
.brand-icon { display: block; width: 40px; height: 40px; }
.topnav {
  display: flex; align-items: center; gap: 4px; flex: 1;
}
.topnav a {
  color: #c9d1d9; padding: 8px 12px; border-radius: 6px;
  font-weight: 500; text-decoration: none;
}
.topnav a:hover, .topnav a.active {
  color: #fff; background: rgba(255,255,255,0.12); text-decoration: none;
}
.topbar-meta {
  margin-left: auto; color: #c9d1d9; font-size: 12px;
  display: flex; align-items: center; gap: 10px;
}
.topbar-meta a { color: #e6edf3; margin-left: 4px; }
.topbar-meta a + a { border-left: 1px solid rgba(255,255,255,0.12); padding-left: 10px; }
.page { padding: 24px 24px 48px; }
.page-header {
  display: flex; flex-wrap: wrap; align-items: flex-start;
  justify-content: space-between; gap: 16px; margin-bottom: 20px;
}
.page-title { margin: 0; font-size: 24px; font-weight: 600; letter-spacing: -0.02em; }
.page-subtitle { margin: 6px 0 0; color: var(--text-muted); max-width: 720px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.grid { display: grid; gap: 16px; }
.grid.stats { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); margin-bottom: 20px; }
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}
.card-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-muted);
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
}
.card-header h2, .card-header h3 {
  margin: 0; font-size: 16px; font-weight: 600;
}
.card-body { padding: 20px; }
.card-muted { color: var(--text-muted); font-size: 13px; }
.stat-card { padding: 16px 18px; }
.stat-value { font-size: 28px; font-weight: 700; line-height: 1.1; letter-spacing: -0.03em; }
.stat-label { margin-top: 6px; color: var(--text-muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; }
.table-wrap { overflow: auto; }
table.data {
  width: 100%; border-collapse: collapse; font-size: 13px;
}
table.data th, table.data td {
  padding: 10px 14px; border-bottom: 1px solid var(--border-muted); text-align: left; vertical-align: top;
}
table.data th {
  background: var(--surface-muted); color: var(--text-subtle); font-weight: 600; white-space: nowrap;
}
table.data tr:last-child td { border-bottom: none; }
table.data tr:hover td { background: #f6f8fa; }
.empty {
  text-align: center; padding: 40px 20px; color: var(--text-muted);
}
.empty-icon {
  width: 48px; height: 48px; margin: 0 auto 12px; border-radius: 12px;
  background: var(--surface-muted); border: 1px dashed var(--border);
  display: flex; align-items: center; justify-content: center; font-size: 20px;
}
.badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; border: 1px solid transparent;
}
.badge.success { background: var(--success-soft); color: var(--success); border-color: #aceebb; }
.badge.warning { background: var(--warning-soft); color: var(--warning); border-color: #f0ce68; }
.badge.muted { background: var(--surface-muted); color: var(--text-subtle); border-color: var(--border-muted); }
.badge.danger { background: var(--danger-soft); color: var(--danger); border-color: #ffbbb9; }
.btn {
  appearance: none; border: 1px solid var(--border);
  background: var(--surface); color: var(--text);
  border-radius: var(--radius); padding: 5px 12px;
  font: inherit; font-size: 13px; font-weight: 500;
  cursor: pointer; display: inline-flex; align-items: center; gap: 6px;
}
.btn:hover { background: var(--surface-muted); border-color: #afb8c1; text-decoration: none; }
.btn.primary { background: var(--accent); border-color: rgba(27,31,36,0.15); color: #fff; }
.btn.primary:hover { background: var(--accent-hover); color: #fff; }
.btn.danger { color: var(--danger); border-color: #ffbbb9; background: #fff; }
.btn.danger:hover { background: var(--danger-soft); }
.btn.subtle { border-color: transparent; background: transparent; color: var(--accent); padding-left: 0; padding-right: 0; }
.btn.subtle:hover { background: transparent; text-decoration: underline; }
.form-row { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; }
.key-create-row {
  display: flex; flex-wrap: nowrap; align-items: center; gap: 10px; margin-bottom: 14px;
}
.key-create-row .key-create-label {
  font-size: 13px; font-weight: 600; color: var(--text); white-space: nowrap;
}
.key-create-row .key-create-input {
  flex: 1; min-width: 160px; max-width: 320px;
  padding: 8px 12px; border: 1px solid var(--border); border-radius: var(--radius);
  font: inherit; background: #fff;
}
.key-create-row .btn { white-space: nowrap; flex-shrink: 0; }
.grant-picker {
  border: 1px solid var(--border-muted); border-radius: var(--radius);
  overflow: hidden; font-size: 13px;
}
.grant-picker table { width: 100%; border-collapse: collapse; margin: 0; }
.grant-picker th, .grant-picker td {
  padding: 10px 12px; border-bottom: 1px solid var(--border-muted); text-align: left; vertical-align: middle;
}
.grant-picker th { background: var(--surface-muted); color: var(--text-subtle); font-weight: 600; }
.grant-picker tr:last-child td { border-bottom: none; }
.grant-picker select {
  min-width: 120px; padding: 6px 8px; border: 1px solid var(--border);
  border-radius: var(--radius); font: inherit; background: #fff;
}
.grant-picker select:disabled { background: var(--surface-muted); color: var(--text-muted); cursor: not-allowed; }
.grant-hint { color: var(--text-muted); font-size: 12px; }
.key-label-row {
  display: flex; align-items: center; gap: 8px;
}
.key-label-row input[type="text"] {
  flex: 1; min-width: 100px; max-width: 200px;
  padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius);
  font: inherit; background: #fff;
}
.btn.sm { padding: 3px 10px; font-size: 12px; line-height: 1.4; }
.cell-actions { white-space: nowrap; text-align: right; }
.cell-actions form { display: inline; margin-left: 6px; }
.copy-src {
  position: absolute; left: -9999px; width: 1px; height: 1px; opacity: 0;
}
.form-footer {
  display: flex; justify-content: space-between; align-items: center;
  margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border-muted);
}
.danger-zone {
  margin-top: 24px; border: 1px solid #ffbbb9; border-radius: var(--radius-lg);
  padding: 14px 16px; display: flex; justify-content: space-between;
  align-items: center; gap: 12px; flex-wrap: wrap;
}
.danger-zone .zone-text { color: var(--text-muted); font-size: 13px; }
.key-detail-section { margin-bottom: 20px; }
.key-detail-section h3 { font-size: 14px; margin: 0 0 8px; font-weight: 600; }
label.field { display: grid; gap: 6px; font-size: 13px; font-weight: 600; color: var(--text); }
input[type=text], .copy-input {
  min-width: 280px; padding: 8px 12px; border: 1px solid var(--border);
  border-radius: var(--radius); font: inherit; background: #fff;
}
input[type=text]:focus, .copy-input:focus {
  outline: 2px solid var(--accent-soft); border-color: var(--accent);
}
.alert {
  border: 1px solid var(--border); border-radius: var(--radius-lg);
  padding: 14px 16px; margin-bottom: 16px;
}
.alert.warning { background: var(--warning-soft); border-color: #f0ce68; color: #4d2d00; }
.alert.error { background: var(--danger-soft); border-color: #ffbbb9; color: #82071e; }
.alert.info { background: var(--accent-soft); border-color: #9cd7ff; color: #0550ae; }
.kv {
  display: grid; grid-template-columns: 140px 1fr; gap: 8px 16px; font-size: 13px;
}
.kv dt { color: var(--text-muted); margin: 0; }
.kv dd { margin: 0; }
.split { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; }
@media (max-width: 960px) { .split { grid-template-columns: 1fr; } }
.footer {
  border-top: 1px solid var(--border-muted); margin-top: 24px; padding: 20px 0 40px;
  color: var(--text-muted); font-size: 12px;
}
.footer a { margin-right: 12px; }
.pill-list { display: flex; flex-wrap: wrap; gap: 6px; }
.pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 10px; border-radius: 999px; background: var(--surface-muted);
  border: 1px solid var(--border-muted); font-size: 12px; color: var(--text-subtle);
}
.hero-key {
  font-family: var(--mono); font-size: 13px; word-break: break-all;
  background: #0d1117; color: #e6edf3; border-radius: var(--radius);
  padding: 14px 16px; border: 1px solid #30363d;
}
.copy-row { display: flex; gap: 8px; align-items: stretch; }
.copy-row .copy-input { flex: 1; min-width: 0; font-family: var(--mono); font-size: 13px; color: var(--text); background: #fff; }
.steps { margin: 0; padding-left: 18px; color: var(--text-muted); }
.steps li { margin: 8px 0; }
.key-detail-meta { margin: 16px 0; }
.key-detail-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border-muted); }
.breadcrumb { font-size: 13px; color: var(--text-muted); margin-bottom: 12px; }
.breadcrumb a { color: var(--accent); text-decoration: none; }
.breadcrumb a:hover { text-decoration: underline; }
.data td a.key-link { color: var(--accent); font-weight: 600; text-decoration: none; }
.data td a.key-link:hover { text-decoration: underline; }
.page-narrow { max-width: 1012px; }
.nav-admin { opacity: 0.75; font-weight: 400 !important; }
.subnav-links {
  display: flex; gap: 8px; margin-bottom: 20px;
  border-bottom: 1px solid var(--border-muted);
}
.subnav-links a {
  padding: 8px 12px; margin-bottom: -1px; color: var(--text-muted);
  text-decoration: none; font-weight: 500; border-bottom: 2px solid transparent;
}
.subnav-links a:hover { color: var(--text); text-decoration: none; }
.subnav-links a.active {
  color: var(--text); font-weight: 600; border-bottom-color: var(--accent);
}
.profile-header {
  display: flex; gap: 16px; align-items: center; margin-bottom: 20px;
}
.profile-avatar {
  width: 64px; height: 64px; border-radius: 50%; background: var(--accent-soft);
  color: var(--accent); display: flex; align-items: center; justify-content: center;
  font-size: 24px; font-weight: 700; flex-shrink: 0; border: 1px solid #9cd7ff;
}
.profile-name { margin: 0 0 6px; font-size: 20px; font-weight: 600; }
.profile-meta { color: var(--text-muted); font-size: 13px; }
.id-block {
  display: block; margin-top: 8px; padding: 10px 12px; font-size: 13px;
  word-break: break-all; background: var(--surface-muted);
  border: 1px solid var(--border-muted); border-radius: var(--radius);
}
.list-group {
  border: 1px solid var(--border-muted); border-radius: var(--radius-lg); overflow: hidden;
}
.list-item {
  display: block; padding: 12px 16px; border-bottom: 1px solid var(--border-muted);
  text-decoration: none; color: inherit;
}
.list-item:last-child { border-bottom: none; }
.list-item:hover { background: var(--surface-muted); text-decoration: none; }
.list-item-title { font-weight: 600; color: var(--accent); margin-bottom: 4px; }
.list-item-meta { font-size: 12px; color: var(--text-muted); }
.page-403 { text-align: center; padding: 64px 20px; }
.page-403 h1 { font-size: 48px; margin: 0 0 8px; color: var(--text-muted); }
.page-403 p { color: var(--text-muted); margin-bottom: 20px; }
.pagination {
  display: flex; align-items: center; justify-content: center; gap: 12px;
  margin-top: 16px; font-size: 13px; color: var(--text-muted);
}
.pagination a { color: var(--accent); text-decoration: none; }
.pagination a:hover { text-decoration: underline; }
.pagination .current { font-weight: 600; color: var(--text); }
a.stat-card-link {
  display: block; text-decoration: none; color: inherit;
  transition: border-color 0.15s ease, background 0.15s ease;
}
a.stat-card-link:hover, a.stat-card-link:focus-visible {
  border-color: var(--accent-muted, #0969da);
  background: var(--canvas-subtle, #f6f8fa);
}
.filter-pills { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.filter-pills a {
  display: inline-block; padding: 4px 12px; border-radius: 999px;
  border: 1px solid var(--border); font-size: 13px; text-decoration: none; color: var(--text);
}
.filter-pills a.active { border-color: var(--accent, #0969da); background: #ddf4ff; font-weight: 600; }
.batch-bar {
  display: flex; gap: 8px; align-items: center; padding: 12px 16px;
  border-bottom: 1px solid var(--border-muted); background: var(--canvas-subtle, #f6f8fa);
}
th.sortable a { color: inherit; text-decoration: none; font-weight: 600; }
th.sortable a:hover { color: var(--accent, #0969da); }
.list-footer {
  display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
  justify-content: space-between; margin-top: 12px; font-size: 13px;
}
.list-footer .page-size a {
  display: inline-block; padding: 2px 8px; margin: 0 2px; border-radius: 6px;
  border: 1px solid var(--border); text-decoration: none; color: var(--text);
}
.list-footer .page-size a.active { border-color: var(--accent, #0969da); background: #ddf4ff; font-weight: 600; }
.list-total { color: var(--text-muted); }
.empty-cta { margin-top: 12px; }
"""

MA3_COPY_JS_TEMPLATE = """
function ma3CopyFrom(btn) {
  var input = btn.previousElementSibling;
  if (!input) return;
  var text = input.value || input.textContent || '';
  input.focus();
  if (input.select) input.select();
  function flash() {
    var orig = btn.textContent;
    btn.textContent = __COPIED__;
    setTimeout(function() { btn.textContent = orig; }, 1500);
  }
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(flash).catch(function() {
      if (ma3CopyExec(input)) flash();
    });
  } else if (ma3CopyExec(input)) {
    flash();
  }
}
function ma3CopyExec(input) {
  try {
    input.focus();
    if (input.select) input.select();
    return document.execCommand('copy');
  } catch (e) {
    return false;
  }
}
"""


def render_copy_js(locale: str = DEFAULT_LOCALE) -> str:
    copied = json.dumps(tr(locale, "shell.copied"), ensure_ascii=False)
    return MA3_COPY_JS_TEMPLATE.replace("__COPIED__", copied)


def portal_nav_items(base: str, *, is_admin: bool, locale: str = DEFAULT_LOCALE) -> list[tuple[str, str, str, bool]]:
    items: list[tuple[str, str, str, bool]] = [
        ("me", tr(locale, "nav.me"), f"{base}/ui/me/", False),
        ("libraries", tr(locale, "nav.libraries"), f"{base}/ui/libraries/", False),
        ("records", tr(locale, "nav.records"), f"{base}/ui/me/writes/", False),
        ("votes", tr(locale, "nav.votes"), f"{base}/ui/me/votes/", False),
        ("keys", tr(locale, "nav.keys"), f"{base}/ui/keys/", False),
    ]
    if is_admin:
        items.append(("observatory", tr(locale, "nav.observatory"), f"{base}/ui/observatory/", True))
    return items


def render_subnav(base: str, *, active: str, locale: str = DEFAULT_LOCALE) -> str:
    """Account-area tabs only; resource management lives in top nav (design/22)."""
    tabs = [
        ("overview", tr(locale, "nav.overview"), f"{base}/ui/me/"),
        ("settings", tr(locale, "nav.settings"), f"{base}/ui/me/settings/"),
    ]
    links = "".join(
        f'<a href="{esc(href)}" class="{"active" if key == active else ""}">{esc(label)}</a>'
        for key, label, href in tabs
    )
    return f'<nav class="subnav-links">{links}</nav>'


def render_pagination(
    *,
    page: int,
    total_pages: int,
    base_path: str,
    query: dict[str, str] | None = None,
    locale: str = DEFAULT_LOCALE,
) -> str:
    if total_pages <= 1:
        return ""

    def _page_href(target_page: int) -> str:
        params = dict(query or {})
        if target_page > 1:
            params["page"] = str(target_page)
        else:
            params.pop("page", None)
        qs = urlencode(params)
        return f"{esc(base_path)}?{esc(qs)}" if qs else esc(base_path)

    prev_label = tr(locale, "shell.pagination.prev")
    next_label = tr(locale, "shell.pagination.next")
    prev_link = f'<a href="{_page_href(page - 1)}">{esc(prev_label)}</a>' if page > 1 else f"<span>{esc(prev_label)}</span>"
    next_link = (
        f'<a href="{_page_href(page + 1)}">{esc(next_label)}</a>' if page < total_pages else f"<span>{esc(next_label)}</span>"
    )
    current = tr(locale, "shell.pagination.current", page=page, total_pages=total_pages)
    return (
        f'<div class="pagination">{prev_link}'
        f'<span class="current">{esc(current)}</span>{next_link}</div>'
    )


def render_list_footer(
    *,
    page: int,
    total_pages: int,
    total_items: int,
    base_path: str,
    query: dict[str, str] | None = None,
    page_sizes: tuple[int, ...] = (10, 25, 50, 100),
    per_page: int = 50,
    default_per_page: int = 50,
    locale: str = DEFAULT_LOCALE,
) -> str:
    base_query = dict(query or {})
    size_links: list[str] = []
    for size in page_sizes:
        params = dict(base_query)
        if size != default_per_page:
            params["per_page"] = str(size)
        else:
            params.pop("per_page", None)
        params.pop("page", None)
        qs = urlencode(params)
        href = f"{esc(base_path)}?{esc(qs)}" if qs else esc(base_path)
        cls = "active" if size == per_page else ""
        size_links.append(f'<a class="{cls}" href="{href}">{size}</a>')
    if locale == "en-US":
        size_bar = f'<span class="page-size">{" · ".join(size_links)} per page</span>'
    else:
        size_bar = f'<span class="page-size">每页 {" · ".join(size_links)} 条</span>'
    pagination = render_pagination(
        page=page, total_pages=total_pages, base_path=base_path, query=query, locale=locale
    )
    total_label = tr(locale, "shell.list.total", count=total_items)
    return (
        f'<div class="list-footer">'
        f'<span class="list-total">{esc(total_label)}</span>'
        f"{size_bar}"
        f"{pagination}"
        f"</div>"
    )


def render_sort_link(
    *,
    label: str,
    column: str,
    current_sort: str,
    current_dir: str,
    base_path: str,
    query: dict[str, str],
) -> str:
    next_dir = "desc" if current_sort == column and current_dir == "asc" else "asc"
    params = dict(query)
    params["sort"] = column
    params["dir"] = next_dir
    params.pop("page", None)
    arrow = ""
    if current_sort == column:
        arrow = " ↑" if current_dir == "asc" else " ↓"
    href = f"{esc(base_path)}?{esc(urlencode(params))}"
    return f'<a href="{href}">{esc(label)}{arrow}</a>'


def render_breadcrumb(items: list[tuple[str, str | None]]) -> str:
    parts: list[str] = []
    for label, href in items:
        if href:
            parts.append(f'<a href="{esc(href)}">{esc(label)}</a>')
        else:
            parts.append(f"<span>{esc(label)}</span>")
    return f'<div class="breadcrumb">{" / ".join(parts)}</div>'


def render_page_403(
    *,
    base: str,
    message: str,
    back_href: str,
    back_label: str,
    locale: str = DEFAULT_LOCALE,
    request: Request | None = None,
) -> str:
    body = f"""
  <div class="page-403">
    <h1>403</h1>
    <p>{esc(message)}</p>
    <a class="btn" href="{esc(back_href)}">{esc(back_label)}</a>
  </div>"""
    return render_page(
        title="Forbidden",
        base=base,
        active_nav="",
        body=body,
        show_minimal_header=True,
        locale=locale,
        request=request,
    )


def render_page(
    *,
    title: str,
    base: str,
    active_nav: str,
    body: str,
    subtitle: str = "",
    user_line: str = "",
    show_logout: bool = False,
    is_admin: bool = False,
    actions_html: str = "",
    breadcrumb_html: str = "",
    brand_href: str | None = None,
    show_minimal_header: bool = False,
    header_extra_html: str = "",
    locale: str = DEFAULT_LOCALE,
    request: Request | None = None,
) -> str:
    from app.api.ui_i18n import render_locale_switcher

    logout = f'<a href="{esc(base)}/auth/logout">{esc(tr(locale, "common.logout"))}</a>' if show_logout else ""
    account = f'<a href="{esc(base)}/auth/account">{esc(tr(locale, "common.account"))}</a>' if show_logout else ""
    login_link = (
        f'<a href="{esc(base)}/auth/login?next={esc(base)}/ui/me/">{esc(tr(locale, "common.login"))}</a>'
        if show_minimal_header
        else ""
    )
    nav_items = [] if show_minimal_header else portal_nav_items(base, is_admin=is_admin, locale=locale)
    nav_html = "".join(
        f'<a href="{esc(href)}" class="{"active" if key == active_nav else ""}{" nav-admin" if admin_muted else ""}">{esc(label)}</a>'
        for key, label, href, admin_muted in nav_items
    )
    subtitle_html = f'<p class="page-subtitle">{subtitle}</p>' if subtitle else ""
    user_meta = f"<span>{esc(user_line)}</span>" if user_line else ""
    brand_link = brand_href or f"{base}/ui/me/"
    switcher = render_locale_switcher(request, locale) if request is not None else ""
    meta_bits = [user_meta, account, logout, switcher] if show_logout else ([login_link, switcher] if show_minimal_header else [user_meta, switcher])
    meta_html = "".join(bit for bit in meta_bits if bit)
    header_block = "" if show_minimal_header else f"""
    <div class="page-header">
      <div>
        <h1 class="page-title">{esc(title)}</h1>
        {subtitle_html}
      </div>
      <div class="actions">{actions_html}</div>
    </div>"""
    return f"""<!DOCTYPE html>
<html lang="{esc(locale)}">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{esc(title)} · ma3</title>
  <style>{MA3_CSS}</style>
</head>
<body>
  <header class="topbar">
    <div class="topbar-inner">
      <div class="page-narrow topbar-row">
      <a class="brand" href="{esc(brand_link)}" aria-label="{esc(tr(locale, "shell.brand_aria"))}">
        {MA3_BRAND_SVG}
      </a>
      <nav class="topnav">{nav_html}</nav>
      <div class="topbar-meta">
        {meta_html}
      </div>
      </div>
    </div>
  </header>
  <main class="page">
    <div class="page-narrow">
      {breadcrumb_html}
      {header_extra_html}
      {header_block}
      {body}
    </div>
    <footer class="footer">
      <div class="footer-inner" style="padding:0;">
        <a href="{esc(base)}/healthz">healthz</a>
        <a href="{esc(base)}/mcp/info">MCP</a>
        <a href="{esc(base)}/client/manifest.json">manifest</a>
        <a href="{esc(base)}/client/agent-onboarding.md">onboarding</a>
        <span>v{esc(settings.service_version)} · {esc(settings.instance_id or "local")}</span>
      </div>
    </footer>
  </main>
  <script>{render_copy_js(locale)}</script>
</body>
</html>"""


def _render_table_cell(cell: Any) -> str:
    if isinstance(cell, str) and cell.startswith("<"):
        return cell
    return esc(cell)


def render_table(
    headers: list[str],
    rows: list[list[Any]],
    *,
    empty: str | None = None,
    locale: str = DEFAULT_LOCALE,
) -> str:
    empty_text = empty if empty is not None else tr(locale, "common.empty")
    if not rows:
        return f'<div class="empty"><div class="empty-icon">—</div><div>{esc(empty_text)}</div></div>'
    head = "".join(f"<th>{_render_table_cell(h)}</th>" for h in headers)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{_render_table_cell(cell)}</td>" for cell in row)
        body_rows.append(f"<tr>{cells}</tr>")
    return f'<div class="table-wrap"><table class="data"><thead><tr>{head}</tr></thead><tbody>{"".join(body_rows)}</tbody></table></div>'


def render_stat_cards(items: Iterable[tuple[str, Any] | tuple[str, Any, str]]) -> str:
    cards: list[str] = []
    for item in items:
        if len(item) == 3:
            label, value, href = item  # type: ignore[misc]
            cards.append(
                f'<a class="card stat-card stat-card-link" href="{esc(href)}">'
                f'<div class="stat-value">{esc(value)}</div>'
                f'<div class="stat-label">{esc(label)}</div></a>'
            )
        else:
            label, value = item  # type: ignore[misc]
            cards.append(
                f'<div class="card stat-card"><div class="stat-value">{esc(value)}</div>'
                f'<div class="stat-label">{esc(label)}</div></div>'
            )
    return f'<div class="grid stats">{"".join(cards)}</div>'


def badge(text: str, kind: str = "muted") -> str:
    return f'<span class="badge {esc(kind)}">{esc(text)}</span>'
