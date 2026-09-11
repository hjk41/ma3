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
.storage-meter { margin: 12px 0 4px; }
.storage-meter-track {
  height: 10px; border-radius: 999px; background: var(--border);
  overflow: hidden;
}
.storage-meter-fill {
  height: 100%; border-radius: 999px; background: var(--accent);
  max-width: 100%;
}
.storage-meter-fill.warn { background: #d4a017; }
.storage-meter-fill.full { background: #cf222e; }
.storage-meter-meta { font-size: 13px; color: var(--muted); margin-top: 6px; }
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
input[type=text],
input[type=password],
input[type=email],
input[type=search],
input[type=number],
textarea.copy-input,
.copy-input {
  min-width: 280px; padding: 8px 12px; border: 1px solid var(--border);
  border-radius: var(--radius); font: inherit; background: #fff;
}
textarea.copy-input {
  width: 100%; min-height: 7.5rem; resize: vertical; line-height: 1.45;
  font-family: var(--mono); font-size: 13px;
}
.copy-row.stack { flex-direction: column; align-items: stretch; }
.copy-row.stack .btn { align-self: flex-start; }
.password-field {
  position: relative; max-width: 360px; width: 100%;
}
.password-field input[type=password],
.password-field input[type=text] {
  width: 100%; max-width: 100%; min-width: 0; box-sizing: border-box;
  padding-right: 42px;
}
.password-toggle {
  position: absolute; right: 4px; top: 50%; transform: translateY(-50%);
  border: 0; background: transparent; color: var(--text-muted);
  cursor: pointer; padding: 6px 8px; border-radius: var(--radius);
  line-height: 0;
}
.password-toggle:hover { color: var(--text); background: var(--surface-muted); }
.password-toggle:focus-visible { outline: 2px solid var(--accent-soft); }
.password-toggle svg { width: 18px; height: 18px; display: block; }
input[type=text]:focus,
input[type=password]:focus,
input[type=email]:focus,
input[type=search]:focus,
input[type=number]:focus,
.copy-input:focus {
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
.landing-hero {
  text-align: center; padding: 32px 0 48px;
}
.landing-hero-title {
  font-size: 28px; line-height: 1.25; font-weight: 700; color: #24292f;
  max-width: 720px; margin: 0 auto 16px;
}
.landing-hero-lead {
  font-size: 18px; line-height: 1.5; color: #57606a;
  max-width: 640px; margin: 0 auto 24px;
}
.landing-hero-actions {
  display: flex; flex-wrap: wrap; gap: 12px; justify-content: center;
}
.landing-section + .landing-section { margin-top: 48px; }
.landing-section-title {
  font-size: 20px; font-weight: 600; margin: 0 0 16px; color: #24292f;
}
.landing-section-lead {
  font-size: 15px; color: #57606a; margin: -8px 0 16px; line-height: 1.5;
}
.landing-problem-list {
  margin: 0; padding-left: 20px; color: #57606a;
}
.landing-problem-list li { margin: 10px 0; line-height: 1.5; }
.landing-compare-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
}
.landing-compare-grid h3 {
  font-size: 14px; font-weight: 600; margin: 0 0 12px; color: #24292f;
}
.landing-compare-grid ul {
  margin: 0; padding-left: 18px; font-size: 14px; color: #57606a;
}
.landing-compare-grid li { margin: 6px 0; }
.landing-flow {
  display: flex; flex-wrap: wrap; gap: 12px; list-style: none; padding: 0; margin: 0;
}
.landing-flow li {
  flex: 1 1 140px; display: flex; gap: 10px; align-items: flex-start;
  padding: 12px; background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px;
}
.landing-flow-step {
  width: 24px; height: 24px; border-radius: 50%; background: #0969da; color: #fff;
  font-size: 12px; font-weight: 700; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.landing-flow-text { font-size: 14px; color: #24292f; line-height: 1.4; }
.landing-feature-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px;
}
.landing-feature-card h3 {
  font-size: 14px; font-weight: 600; margin: 0 0 8px; color: #24292f;
}
.landing-feature-card p {
  margin: 0; font-size: 13px; color: #57606a; line-height: 1.5;
}
.landing-status-meta {
  margin-top: 12px; font-size: 13px; color: #57606a;
}
.landing-numbered-steps {
  margin: 0; padding-left: 20px; color: #57606a;
}
.landing-numbered-steps li { margin: 10px 0; line-height: 1.5; }
.landing-getstarted-cta { margin-top: 20px; }
@media (max-width: 768px) {
  .landing-hero-title { font-size: 24px; }
  .landing-section + .landing-section { margin-top: 32px; }
  .landing-compare-grid, .landing-feature-grid { grid-template-columns: 1fr; }
  .landing-hero-actions .btn { width: 100%; justify-content: center; }
}
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
function ma3TogglePassword(btn) {
  var wrap = btn.closest('.password-field');
  if (!wrap) return;
  var input = wrap.querySelector('input');
  if (!input) return;
  // revealing: password was masked → show plaintext; icon becomes open eye
  var revealing = input.type === 'password';
  input.type = revealing ? 'text' : 'password';
  btn.setAttribute(
    'aria-label',
    revealing
      ? (btn.getAttribute('data-hide-label') || 'Hide password')
      : (btn.getAttribute('data-show-label') || 'Show password')
  );
  btn.setAttribute('aria-pressed', revealing ? 'true' : 'false');
  var eye = btn.querySelector('.pw-eye');
  var eyeOff = btn.querySelector('.pw-eye-off');
  // Open eye = plaintext visible; closed/slashed eye = masked (default)
  if (eye) eye.style.display = revealing ? '' : 'none';
  if (eyeOff) eyeOff.style.display = revealing ? 'none' : '';
}
function ma3CheckPasswordConfirm(form) {
  var pw = form.querySelector('input[name="password"]');
  var conf = form.querySelector('input[name="password_confirm"]');
  if (!pw || !conf) return true;
  var msg = form.getAttribute('data-password-mismatch') || 'Passwords do not match';
  var box = form.querySelector('.password-mismatch-alert');
  if (!box) {
    box = document.createElement('div');
    box.className = 'alert error password-mismatch-alert';
    form.insertBefore(box, form.firstChild);
  }
  if (pw.value !== conf.value) {
    conf.setCustomValidity('');
    box.textContent = msg;
    box.hidden = false;
    conf.focus();
    return false;
  }
  box.hidden = true;
  box.textContent = '';
  conf.setCustomValidity('');
  return true;
}
"""


_EYE_SVG = (
    '<svg class="pw-eye" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="display:none">'
    '<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/>'
    '<circle cx="12" cy="12" r="3"/></svg>'
)
_EYE_OFF_SVG = (
    '<svg class="pw-eye-off" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M17.94 17.94A10.94 10.94 0 0 1 12 19c-7 0-11-7-11-7a21.8 21.8 0 0 1 5.06-5.94"/>'
    '<path d="M9.9 4.24A10.94 10.94 0 0 1 12 5c7 0 11 7 11 7a21.9 21.9 0 0 1-2.16 3.19"/>'
    '<path d="M14.12 14.12a3 3 0 0 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>'
)


def render_password_input(
    *,
    name: str,
    label: str,
    autocomplete: str,
    show_label: str,
    hide_label: str,
    required: bool = True,
) -> str:
    """Labeled password field with show/hide eye toggle."""
    req = " required" if required else ""
    return f"""
        <label style="display:block;margin:12px 0 4px;">{esc(label)}</label>
        <div class="password-field">
          <input name="{esc(name)}" type="password"{req} autocomplete="{esc(autocomplete)}" />
          <button type="button" class="password-toggle" aria-label="{esc(show_label)}" aria-pressed="false"
                  data-show-label="{esc(show_label)}" data-hide-label="{esc(hide_label)}"
                  onclick="ma3TogglePassword(this)">{_EYE_SVG}{_EYE_OFF_SVG}</button>
        </div>"""


def render_copy_js(locale: str = DEFAULT_LOCALE) -> str:
    copied = json.dumps(tr(locale, "shell.copied"), ensure_ascii=False)
    return MA3_COPY_JS_TEMPLATE.replace("__COPIED__", copied)


def portal_nav_items(base: str, *, is_admin: bool, locale: str = DEFAULT_LOCALE) -> list[tuple[str, str, str, bool]]:
    items: list[tuple[str, str, str, bool]] = [
        ("me", tr(locale, "nav.me"), f"{base}/ui/me/", False),
        ("libraries", tr(locale, "nav.libraries"), f"{base}/ui/libraries/", False),
        ("orgs", tr(locale, "nav.orgs"), f"{base}/ui/orgs/", False),
        ("records", tr(locale, "nav.records"), f"{base}/ui/me/writes/", False),
        ("votes", tr(locale, "nav.votes"), f"{base}/ui/me/votes/", False),
        ("keys", tr(locale, "nav.keys"), f"{base}/ui/keys/", False),
        ("billing", tr(locale, "nav.billing"), f"{base}/ui/billing/", False),
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
    show_login: bool = True,
    header_extra_html: str = "",
    meta_description: str = "",
    locale: str = DEFAULT_LOCALE,
    request: Request | None = None,
) -> str:
    from app.api.ui_i18n import render_locale_switcher

    logout = f'<a href="{esc(base)}/auth/logout">{esc(tr(locale, "common.logout"))}</a>' if show_logout else ""
    account = f'<a href="{esc(base)}/auth/account">{esc(tr(locale, "common.account"))}</a>' if show_logout else ""
    login_link = (
        f'<a href="{esc(base)}/auth/login?next={esc(base)}/ui/me/">{esc(tr(locale, "common.login"))}</a>'
        if show_minimal_header and show_login and not show_logout
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
    meta_desc_html = (
        f'  <meta name="description" content="{esc(meta_description)}"/>\n'
        if meta_description
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="{esc(locale)}">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
{meta_desc_html}  <title>{esc(title)} · ma3</title>
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
        <a href="https://ma3-talk.slack.com">Slack</a>
        <a href="https://github.com/hjk41/ma3/blob/main/docs/07-commercial/legal/terms-of-service.md">Terms</a>
        <a href="https://github.com/hjk41/ma3/blob/main/docs/07-commercial/legal/privacy-policy.md">Privacy</a>
        <a href="https://github.com/hjk41/ma3/blob/main/docs/07-commercial/legal/data-retention-and-deletion.md">Data</a>
        <span>v{esc(settings.service_version)} · {esc(settings.instance_id or "local")}</span>
      </div>
    </footer>
  </main>
  <script>{render_copy_js(locale)}</script>
</body>
</html>"""


def _render_table_cell(cell: Any) -> str:
    # Allow pre-built HTML snippets (forms, badges, <code>). Leading whitespace
    # in f-string blocks must not force esc() — that was escaping Observatory
    # plan buttons into visible raw markup.
    if isinstance(cell, str) and cell.lstrip().startswith("<"):
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
        # Callers may pass pre-escaped HTML snippets (e.g. keys empty hint).
        if isinstance(empty_text, str) and empty_text.lstrip().startswith("<"):
            empty_html = empty_text
        elif isinstance(empty_text, str) and "<" in empty_text:
            # Mixed text+tags from callers that already esc()'d text parts.
            empty_html = empty_text
        else:
            empty_html = esc(empty_text)
        return f'<div class="empty"><div class="empty-icon">—</div><div>{empty_html}</div></div>'
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


def render_storage_meter(*, used_bytes: int, limit_bytes: int | None, label: str) -> str:
    used = max(0, int(used_bytes))
    if limit_bytes is None or limit_bytes <= 0:
        pct = 0
        meta = label
        fill_class = ""
    else:
        pct = min(100, int(round(100 * used / limit_bytes)))
        fill_class = " full" if pct >= 100 else (" warn" if pct >= 85 else "")
        meta = label
    return f"""
<div class="storage-meter">
  <div class="storage-meter-track"><div class="storage-meter-fill{fill_class}" style="width:{pct}%;"></div></div>
  <div class="storage-meter-meta">{esc(meta)}</div>
</div>"""

