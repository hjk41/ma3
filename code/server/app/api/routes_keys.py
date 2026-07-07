from __future__ import annotations

import json
import logging
from typing import Any
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from app.core.security import assert_same_origin as _assert_same_origin
from app.api.ui_session import redirect_if_setup_required
from app.api.ui_i18n import html_response, tr, ui_locale
from app.api.ui_theme import badge, esc, render_page, render_table
from app.auth.session import SessionUser, resolve_session_user
from app.core.config import settings
from app.services.api_key_encryption import reveal_stored_key
from app.services.onboarding_service import (
    create_personal_dev_key,
    ensure_personal_library,
    is_paid_principal,
    normalize_key_label,
    normalize_api_key_grants,
    resolve_key_grants,
)
from app.services.principal_service import display_name_setup_required
from app.storage import db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["keys"])


class KeyGrantBody(BaseModel):
    library_id: str
    role: str = Field(pattern="^(reader|writer)$")


class CreateKeyBody(BaseModel):
    label: str = Field(default="agent-key", max_length=120)
    grants: list[KeyGrantBody] | None = None


class UpdateKeyBody(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    grants: list[KeyGrantBody] | None = None


def _require_authing_configured() -> None:
    if not settings.authing_configured:
        raise HTTPException(
            status_code=503,
            detail=(
                "self-service key management requires Authing; "
                "use MA3_DEV_AUTH break-glass key or ask an admin to run seed_personal_library_key.py"
            ),
        )


def _require_session_user(request: Request) -> SessionUser:
    _require_authing_configured()
    user = resolve_session_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    if display_name_setup_required(user.principal_id):
        raise HTTPException(
            status_code=403,
            detail="complete display name setup at /ui/me/setup/ before managing API keys",
        )
    return user


def _redirect_login(request: Request) -> Response:
    return RedirectResponse(f"/auth/login?next={request.url.path}", status_code=302)


def _require_ui_keys_user(request: Request) -> SessionUser | Response:
    user = resolve_session_user(request)
    if user is None:
        return _redirect_login(request)
    setup_redirect = redirect_if_setup_required(request, user)
    if setup_redirect is not None:
        return setup_redirect
    return user


def _enrich_keys_with_plaintext(keys: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for key in keys:
        item = dict(key)
        item["plaintext_key"] = reveal_stored_key(item.pop("key_ciphertext", None))
        enriched.append(item)
    return enriched


def _render_copy_row(plaintext: str, *, primary: bool = False, locale: str = "zh-CN") -> str:
    btn_class = "btn primary" if primary else "btn"
    return (
        f'<div class="copy-row">'
        f'<input class="copy-input" type="text" readonly value="{esc(plaintext)}" onclick="this.select();" />'
        f'<button type="button" class="{btn_class}" onclick="ma3CopyFrom(this)">{esc(tr(locale, "common.copy"))}</button>'
        f"</div>"
    )


def _grants_to_role_choices(
    grants: list[dict[str, Any]],
    personal_lib_id: str,
) -> tuple[str, str]:
    personal_role = "none"
    community_role = "none"
    for grant in grants:
        library_id = str(grant.get("library_id", ""))
        role = str(grant.get("role", "")).lower()
        if role not in {"reader", "writer"}:
            continue
        if library_id == personal_lib_id:
            personal_role = role
        elif library_id == settings.default_library_id:
            community_role = role
    return personal_role, community_role


def _public_key_payload(key: dict[str, Any]) -> dict[str, Any]:
    return {
        "key_id": key["key_id"],
        "key_prefix": key.get("key_prefix"),
        "label": key.get("label"),
        "grants": key.get("grants", []),
        "created_at": key.get("created_at"),
        "last_used_at": key.get("last_used_at"),
        "expires_at": key.get("expires_at"),
        "plaintext_key": key.get("plaintext_key"),
    }


def _grant_summary(grants: list[dict[str, Any]], *, locale: str = "zh-CN") -> str:
    parts: list[str] = []
    for grant in grants:
        name = grant.get("library_name") or grant.get("library_id")
        role = grant.get("role", "")
        role_label = tr(locale, f"role.{role}") if str(role) in {"reader", "writer", "none"} else str(role)
        parts.append(f"{name} ({role_label})")
    return ", ".join(parts) if parts else "—"


def _render_grant_picker(
    *,
    personal_lib: dict[str, Any],
    is_paid: bool,
    personal_role: str = "writer",
    community_role: str = "writer",
    locale: str = "zh-CN",
) -> str:
    community_name = tr(locale, "keys.grant.community_name")
    personal_name = esc(personal_lib.get("name") or personal_lib["library_id"])
    free_hint = ""
    community_select = ""
    if is_paid:
        community_select = (
            f'<select name="grant_community">'
            f'{_role_options(community_role, locale=locale)}'
            f"</select>"
        )
    else:
        free_hint = f'<div class="grant-hint">{esc(tr(locale, "keys.grant.free_hint"))}</div>'
        community_select = (
            f'<select name="grant_community" disabled>'
            f'<option value="writer" selected>{esc(tr(locale, "role.writer"))}</option>'
            f"</select>"
            '<input type="hidden" name="grant_community" value="writer"/>'
        )
    return f"""
        {free_hint}
        <div class="grant-picker">
          <table>
            <thead><tr><th>{esc(tr(locale, "keys.grant.library_header"))}</th><th>{esc(tr(locale, "keys.grant.permission_header"))}</th></tr></thead>
            <tbody>
              <tr>
                <td>{esc(community_name)}</td>
                <td>{community_select}</td>
              </tr>
              <tr>
                <td>{personal_name}<br/><code>{esc(personal_lib["library_id"])}</code></td>
                <td><select name="grant_personal">{_role_options(personal_role, locale=locale)}</select></td>
              </tr>
            </tbody>
          </table>
        </div>"""


def _role_options(selected: str, *, locale: str = "zh-CN") -> str:
    labels = {"none": tr(locale, "role.none"), "reader": tr(locale, "role.reader"), "writer": tr(locale, "role.writer")}
    return "".join(
        f'<option value="{esc(value)}"{" selected" if value == selected else ""}>{esc(label)}</option>'
        for value, label in labels.items()
    )


def _grants_from_form(form: Any, personal_lib_id: str, principal_id: str) -> list[dict[str, str]]:
    personal_role = str(form.get("grant_personal", "writer")).lower()
    community_role = str(form.get("grant_community", "writer")).lower()
    return resolve_key_grants(
        personal_library_id=personal_lib_id,
        personal_role=personal_role,  # type: ignore[arg-type]
        community_role=community_role,  # type: ignore[arg-type]
        principal_id=principal_id,
    )


def _render_key_list_name_cell(base: str, key: dict[str, Any]) -> str:
    key_id = esc(key["key_id"])
    label = esc(key.get("label") or key_id)
    return f'<a class="key-link" href="{esc(base)}/ui/keys/{key_id}">{label}</a>'


def _resolve_grants_payload(
    grants: list[dict[str, str]],
    *,
    personal_lib_id: str,
    principal_id: str,
) -> list[dict[str, str]]:
    return normalize_api_key_grants(
        grants,
        personal_library_id=personal_lib_id,
        principal_id=principal_id,
    )


def _render_list_actions_cell(base: str, key: dict[str, Any], *, locale: str = "zh-CN") -> str:
    key_id = esc(key["key_id"])
    plaintext = key.get("plaintext_key")
    copy_part = ""
    if plaintext:
        copy_part = (
            f'<input class="copy-src" type="text" readonly value="{esc(plaintext)}" tabindex="-1" aria-hidden="true"/>'
            f'<button type="button" class="btn sm" onclick="ma3CopyFrom(this)">{esc(tr(locale, "common.copy"))}</button>'
        )
    delete_confirm = tr(locale, "keys.delete_confirm")
    delete_part = (
        f'<form method="post" action="{esc(base)}/ui/keys/{key_id}/delete" '
        f'onsubmit="return confirm({json.dumps(delete_confirm)})">'
        f'<button type="submit" class="btn sm danger">{esc(tr(locale, "common.delete"))}</button></form>'
    )
    return f'<div class="cell-actions">{copy_part}{delete_part}</div>'


def _render_keys_page(
    base: str,
    user: SessionUser,
    personal_lib: dict[str, Any] | None,
    keys: list[dict[str, Any]],
    *,
    error: str | None = None,
    locale: str = "zh-CN",
    request: Request | None = None,
) -> str:
    personal_line = "—"
    if personal_lib:
        personal_line = (
            f'<div class="pill-list" style="margin-bottom:8px;"><code>{esc(personal_lib["library_id"])}</code></div>'
            f'<div>{esc(personal_lib["name"])}</div>'
            f'<div style="margin-top:8px;">{badge(personal_lib.get("visibility", "private"), "muted")}</div>'
        )
    table_rows: list[list[Any]] = []
    for key in keys:
        last_used = key.get("last_used_at") or "—"
        prefix = key.get("key_prefix") or key.get("key_id")
        table_rows.append(
            [
                _render_key_list_name_cell(base, key),
                f'<code>{esc(prefix)}…</code>',
                esc(_grant_summary(key.get("grants", []), locale=locale)),
                esc(last_used),
                _render_list_actions_cell(base, key, locale=locale),
            ]
        )
    err_html = f'<div class="alert error">{esc(error)}</div>' if error else ""
    is_paid = is_paid_principal(user.principal_id)
    grant_picker = ""
    if personal_lib:
        grant_picker = _render_grant_picker(personal_lib=personal_lib, is_paid=is_paid, locale=locale)
    empty_keys = (
        f'{esc(tr(locale, "keys.empty"))}<br/>'
        f'<span class="grant-hint">{esc(tr(locale, "keys.empty_hint"))}</span>'
    )
    body = f"""
  {err_html}
  <div class="split">
    <div class="card">
      <div class="card-header"><h2>{esc(tr(locale, "keys.management"))}</h2></div>
      <div class="card-body">
        <div style="padding:0 0 16px;">
          {render_table([tr(locale, "keys.table.name"), tr(locale, "keys.table.prefix"), tr(locale, "keys.table.grants"), tr(locale, "keys.table.last_used"), ""], table_rows, empty=empty_keys, locale=locale)}
        </div>
        <form method="post" action="{esc(base)}/ui/keys/create">
          <div class="key-create-row">
            <span class="key-create-label">{esc(tr(locale, "keys.label"))}</span>
            <input class="key-create-input" type="text" name="label" value="my-laptop-agent" maxlength="120"/>
            <button type="submit" class="btn primary">{esc(tr(locale, "keys.create_new"))}</button>
          </div>
          {grant_picker}
        </form>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><h2>{esc(tr(locale, "keys.personal_library"))}</h2></div>
      <div class="card-body">{personal_line}</div>
    </div>
  </div>"""
    return render_page(
        title=tr(locale, "keys.title"),
        base=base,
        active_nav="keys",
        subtitle=tr(locale, "keys.subtitle"),
        user_line=f"{user.display_name}",
        show_logout=True,
        is_admin=user.is_admin,
        body=body,
        locale=locale,
        request=request,
    )


def _render_key_detail_page(
    base: str,
    user: SessionUser,
    personal_lib: dict[str, Any],
    key: dict[str, Any],
    *,
    error: str | None = None,
    saved: bool = False,
    label_override: str | None = None,
    personal_role_override: str | None = None,
    community_role_override: str | None = None,
    locale: str = "zh-CN",
    request: Request | None = None,
) -> str:
    key_id = esc(key["key_id"])
    display_label = esc(label_override if label_override is not None else (key.get("label") or key["key_id"]))
    is_paid = is_paid_principal(user.principal_id)
    personal_role, community_role = _grants_to_role_choices(key.get("grants", []), personal_lib["library_id"])
    if personal_role_override is not None:
        personal_role = personal_role_override
    if community_role_override is not None:
        community_role = community_role_override
    grant_picker = _render_grant_picker(
        personal_lib=personal_lib,
        is_paid=is_paid,
        personal_role=personal_role,
        community_role=community_role,
        locale=locale,
    )
    plaintext = key.get("plaintext_key")
    if plaintext:
        key_block = _render_copy_row(plaintext, primary=True, locale=locale)
    else:
        prefix = esc(key.get("key_prefix") or key["key_id"])
        key_block = (
            f'<code>{prefix}…</code>'
            f'<div class="grant-hint">{esc(tr(locale, "keys.old_key_hint"))}</div>'
        )
    err_html = f'<div class="alert error">{esc(error)}</div>' if error else ""
    saved_html = f'<div class="alert info">{esc(tr(locale, "keys.saved"))}</div>' if saved else ""
    last_used = esc(key.get("last_used_at") or "—")
    created = esc(key.get("created_at", ""))
    delete_confirm = json.dumps(tr(locale, "keys.delete_confirm"))
    body = f"""
  <div class="breadcrumb"><a href="{esc(base)}/ui/keys/">{esc(tr(locale, "keys.title"))}</a> / {display_label}</div>
  {err_html}
  {saved_html}
  <div class="card">
    <div class="card-header"><h2>{display_label}</h2></div>
    <div class="card-body key-detail-meta">
      <div class="key-detail-section">
        <h3>{esc(tr(locale, "keys.detail.key_section"))}</h3>
        {key_block}
      </div>
      <dl class="kv">
        <dt>{esc(tr(locale, "keys.table.prefix"))}</dt><dd><code>{esc(key.get("key_prefix") or "—")}</code></dd>
        <dt>{esc(tr(locale, "common.created_at"))}</dt><dd>{created}</dd>
        <dt>{esc(tr(locale, "common.last_used_at"))}</dt><dd>{last_used}</dd>
      </dl>
      <form method="post" action="{esc(base)}/ui/keys/{key_id}/edit">
        <div class="key-detail-section">
          <h3>{esc(tr(locale, "keys.label"))}</h3>
          <input type="text" name="label" value="{display_label}" maxlength="120" style="max-width:360px;width:100%;"/>
        </div>
        <div class="key-detail-section">
          <h3>{esc(tr(locale, "keys.grants"))}</h3>
          {grant_picker}
        </div>
        <div class="form-footer">
          <a class="btn" href="{esc(base)}/ui/keys/">{esc(tr(locale, "keys.back_to_list"))}</a>
          <button type="submit" class="btn primary">{esc(tr(locale, "common.save"))}</button>
        </div>
      </form>
      <div class="danger-zone">
        <div class="zone-text">{esc(tr(locale, "keys.delete_help"))}</div>
        <form method="post" action="{esc(base)}/ui/keys/{key_id}/delete"
              onsubmit="return confirm({delete_confirm})">
          <button type="submit" class="btn danger">{esc(tr(locale, "keys.delete_key"))}</button>
        </form>
      </div>
    </div>
  </div>"""
    return render_page(
        title=key.get("label") or key["key_id"],
        base=base,
        active_nav="keys",
        subtitle=tr(locale, "keys.detail.subtitle"),
        user_line=user.display_name,
        show_logout=True,
        is_admin=user.is_admin,
        body=body,
        locale=locale,
        request=request,
    )


def _render_created_page(base: str, user: SessionUser, created: dict[str, Any]) -> str:
    """Redirect target kept for API compatibility; UI create now returns to the list."""
    plaintext = created["plaintext_key"]
    body = f"""
  <div class="card">
    <div class="card-header">
      <h2>Key 已创建</h2>
      {badge(created.get("label", ""), "success")}
    </div>
    <div class="card-body">
      <p class="card-muted">{esc(user.display_name)} · 可在 key 列表中随时查看</p>
      <div class="copy-row" style="margin:12px 0;">
        <input class="copy-input" type="text" readonly value="{esc(plaintext)}" onclick="this.select();" />
        <button type="button" class="btn primary" onclick="ma3CopyFrom(this)">复制</button>
      </div>
      <p><a class="btn" href="{esc(base)}/ui/keys/">← 返回 key 列表</a></p>
    </div>
  </div>"""
    return render_page(
        title="Key 已创建",
        base=base,
        active_nav="keys",
        subtitle="Key 已保存，可在列表中再次查看。",
        user_line=user.display_name,
        show_logout=True,
        is_admin=user.is_admin,
        body=body,
    )


def _render_authing_disabled_page(base: str, *, locale: str = "zh-CN", request: Request | None = None) -> str:
    body = f"""
  <div class="card">
    <div class="card-body">
      <div class="alert warning">{esc(tr(locale, "keys.authing_disabled.alert"))}</div>
      <p><a class="btn primary" href="{esc(base)}/ui/observatory/">{esc(tr(locale, "keys.authing_disabled.observatory"))}</a></p>
    </div>
  </div>"""
    return render_page(
        title=tr(locale, "keys.authing_disabled.title"),
        base=base,
        active_nav="keys",
        subtitle=tr(locale, "keys.authing_disabled.subtitle"),
        body=body,
        locale=locale,
        request=request,
    )


@router.get("/api/keys")
def api_list_keys(request: Request) -> JSONResponse:
    user = _require_session_user(request)
    ensure_personal_library(user.principal_id, user.display_name)
    keys = _enrich_keys_with_plaintext(db.list_api_keys_for_principal(user.principal_id))
    safe = [_public_key_payload(k) for k in keys]
    return JSONResponse({"keys": safe})


@router.post("/api/keys")
def api_create_key(request: Request, body: CreateKeyBody) -> JSONResponse:
    _assert_same_origin(request)
    user = _require_session_user(request)
    created = create_personal_dev_key(
        user.principal_id,
        user.display_name,
        label=body.label,
        grants=[g.model_dump() for g in body.grants] if body.grants else None,
    )
    return JSONResponse(
        {
            "key_id": created["key_id"],
            "key_prefix": created["key_prefix"],
            "label": created["label"],
            "plaintext_key": created["plaintext_key"],
            "grants": created["grants"],
            "personal_library": created["personal_library"],
        }
    )


@router.patch("/api/keys/{key_id}")
def api_update_key(request: Request, key_id: str, body: UpdateKeyBody) -> JSONResponse:
    _assert_same_origin(request)
    user = _require_session_user(request)
    if body.label is None and body.grants is None:
        raise HTTPException(status_code=400, detail="label or grants required")
    personal = ensure_personal_library(user.principal_id, user.display_name)
    row = db.get_api_key_for_principal(key_id, principal_id=user.principal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="key not found")
    if body.label is not None:
        row = db.update_api_key_label(
            key_id,
            principal_id=user.principal_id,
            label=normalize_key_label(body.label),
        )
        if row is None:
            raise HTTPException(status_code=404, detail="key not found")
    if body.grants is not None:
        resolved = _resolve_grants_payload(
            [g.model_dump() for g in body.grants],
            personal_lib_id=personal["library_id"],
            principal_id=user.principal_id,
        )
        row = db.replace_api_key_grants(key_id, principal_id=user.principal_id, grants=resolved)
        if row is None:
            raise HTTPException(status_code=404, detail="key not found")
    enriched = _enrich_keys_with_plaintext([row])[0]
    return JSONResponse(_public_key_payload(enriched))


@router.delete("/api/keys/{key_id}")
def api_delete_key(request: Request, key_id: str) -> JSONResponse:
    _assert_same_origin(request)
    user = _require_session_user(request)
    row = db.get_api_key_for_principal(key_id, principal_id=user.principal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="key not found")
    if not db.delete_api_key(key_id, principal_id=user.principal_id):
        raise HTTPException(status_code=404, detail="key not found")
    logger.info(
        "api_key_deleted principal_id=%s key_id=%s key_prefix=%s",
        user.principal_id,
        key_id,
        row.get("key_prefix"),
    )
    return JSONResponse({"deleted": True, "key_id": key_id})


@router.get("/ui/keys/{key_id}", response_class=HTMLResponse)
def ui_keys_detail(request: Request, key_id: str) -> Response:
    locale, _t = ui_locale(request)
    if not settings.authing_configured:
        base = str(request.base_url).rstrip("/")
        return html_response(request, _render_authing_disabled_page(base, locale=locale, request=request), status_code=503)
    user = _require_ui_keys_user(request)
    if isinstance(user, Response):
        return user
    personal = ensure_personal_library(user.principal_id, user.display_name)
    row = db.get_api_key_for_principal(key_id, principal_id=user.principal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="key not found")
    key = _enrich_keys_with_plaintext([row])[0]
    base = str(request.base_url).rstrip("/")
    saved = request.query_params.get("saved") == "1"
    return html_response(request, _render_key_detail_page(base, user, personal, key, saved=saved, locale=locale, request=request))


@router.get("/ui/keys/", response_class=HTMLResponse)
@router.get("/ui/keys", response_class=HTMLResponse)
def ui_keys_list(request: Request) -> Response:
    locale, _t = ui_locale(request)
    if not settings.authing_configured:
        base = str(request.base_url).rstrip("/")
        return html_response(request, _render_authing_disabled_page(base, locale=locale, request=request), status_code=503)
    user = _require_ui_keys_user(request)
    if isinstance(user, Response):
        return user
    personal = ensure_personal_library(user.principal_id, user.display_name)
    keys = _enrich_keys_with_plaintext(db.list_api_keys_for_principal(user.principal_id))
    base = str(request.base_url).rstrip("/")
    return html_response(request, _render_keys_page(base, user, personal, keys, locale=locale, request=request))


@router.post("/ui/keys/create")
async def ui_keys_create(request: Request) -> Response:
    _assert_same_origin(request)
    locale, _t = ui_locale(request)
    if not settings.authing_configured:
        base = str(request.base_url).rstrip("/")
        return html_response(request, _render_authing_disabled_page(base, locale=locale, request=request), status_code=503)
    user = _require_ui_keys_user(request)
    if isinstance(user, Response):
        return user
    form = await request.form()
    label = normalize_key_label(str(form.get("label", "")))
    personal = ensure_personal_library(user.principal_id, user.display_name)
    base = str(request.base_url).rstrip("/")
    try:
        grants = _grants_from_form(form, personal["library_id"], user.principal_id)
        created = create_personal_dev_key(
            user.principal_id,
            user.display_name,
            label=label,
            grants=grants,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        keys = _enrich_keys_with_plaintext(db.list_api_keys_for_principal(user.principal_id))
        return html_response(
            request,
            _render_keys_page(base, user, personal, keys, error=detail, locale=locale, request=request),
            status_code=exc.status_code,
        )
    return RedirectResponse(f"{base}/ui/keys/{created['key_id']}?saved=1", status_code=303)


@router.post("/ui/keys/{key_id}/edit")
async def ui_keys_edit(request: Request, key_id: str) -> Response:
    _assert_same_origin(request)
    locale, _t = ui_locale(request)
    if not settings.authing_configured:
        return RedirectResponse("/ui/keys/", status_code=303)
    user = _require_ui_keys_user(request)
    if isinstance(user, Response):
        return user
    personal = ensure_personal_library(user.principal_id, user.display_name)
    base = str(request.base_url).rstrip("/")
    form = await request.form()
    label = normalize_key_label(str(form.get("label", "")))
    personal_role = str(form.get("grant_personal", "writer")).lower()
    community_role = str(form.get("grant_community", "writer")).lower()
    row = db.get_api_key_for_principal(key_id, principal_id=user.principal_id)
    if row is None:
        return RedirectResponse(f"{base}/ui/keys/", status_code=303)
    try:
        grants = _grants_from_form(form, personal["library_id"], user.principal_id)
        db.update_api_key_label(key_id, principal_id=user.principal_id, label=label)
        db.replace_api_key_grants(key_id, principal_id=user.principal_id, grants=grants)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        key = _enrich_keys_with_plaintext([row])[0]
        return html_response(
            request,
            _render_key_detail_page(
                base,
                user,
                personal,
                key,
                error=detail,
                label_override=label,
                personal_role_override=personal_role,
                community_role_override=community_role,
                locale=locale,
                request=request,
            ),
            status_code=exc.status_code,
        )
    return RedirectResponse(f"{base}/ui/keys/{key_id}?saved=1", status_code=303)


@router.post("/ui/keys/{key_id}/delete")
def ui_keys_delete(request: Request, key_id: str) -> Response:
    _assert_same_origin(request)
    if not settings.authing_configured:
        return RedirectResponse("/ui/keys/", status_code=303)
    user = _require_ui_keys_user(request)
    if isinstance(user, Response):
        return user
    row = db.get_api_key_for_principal(key_id, principal_id=user.principal_id)
    if row is not None:
        db.delete_api_key(key_id, principal_id=user.principal_id)
        logger.info(
            "api_key_deleted principal_id=%s key_id=%s key_prefix=%s",
            user.principal_id,
            key_id,
            row.get("key_prefix"),
        )
    return RedirectResponse("/ui/keys/", status_code=303)
