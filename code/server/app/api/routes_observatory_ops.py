"""Observatory ops: paid users, orgs, and plan assignment (admin only)."""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.api.routes_ui import _observatory_user_line, _require_observatory_admin
from app.api.ui_theme import badge, esc, render_page, render_stat_cards, render_table
from app.core.config import settings
from app.core.security import assert_same_origin as _assert_same_origin
from app.services import billing_ops_service
from app.services import local_auth_service
from app.services import setup_service
from app.services.onboarding_service import set_user_paid
from app.storage import db as storage_db

router = APIRouter(prefix="/ui/observatory", tags=["observatory-ops"])


def _ops_nav(base: str, active: str) -> str:
    items = [
        ("overview", "概览", f"{base}/ui/observatory/"),
        ("billing", "付费概况", f"{base}/ui/observatory/billing/"),
        ("users", "用户 / 付费", f"{base}/ui/observatory/users/"),
        ("local", "本地账号", f"{base}/ui/observatory/local-users/"),
        ("orgs", "组织", f"{base}/ui/observatory/orgs/"),
    ]
    links = []
    for key, label, href in items:
        cls = "btn primary" if key == active else "btn"
        links.append(f'<a class="{cls}" href="{esc(href)}">{esc(label)}</a>')
    return '<div class="actions" style="margin-bottom:16px;">' + " ".join(links) + "</div>"


def _flash(request: Request) -> str:
    msg = (request.query_params.get("ok") or "").strip()
    err = (request.query_params.get("error") or "").strip()
    if err:
        return f'<div class="alert error" style="margin-bottom:12px;">{esc(err)}</div>'
    if msg:
        return f'<div class="alert success" style="margin-bottom:12px;">{esc(msg)}</div>'
    return ""


@router.get("/billing", response_class=HTMLResponse)
@router.get("/billing/", response_class=HTMLResponse)
def observatory_billing(request: Request) -> Response:
    denied = _require_observatory_admin(request)
    if denied is not None:
        return denied
    user, user_line = _observatory_user_line(request)
    base = str(request.base_url).rstrip("/")
    overview = billing_ops_service.billing_overview()
    env_rows = [[pid, badge("env", "muted")] for pid in overview["env_paid_principal_ids"]] or [
        ["—", "（未配置 MA3_PAID_PRINCIPAL_IDS）"]
    ]
    cards = render_stat_cards(
        [
            ("DB Pro 用户", overview["db_pro_count"]),
            ("Env 白名单", overview["env_paid_count"]),
            ("组织总数", overview["org_count"]),
            ("Team 组织", overview["team_org_count"]),
            ("Personal 组织", overview["personal_org_count"]),
            ("带 plan 标签", overview["orgs_with_plan_label"]),
        ]
    )
    linked = billing_ops_service.list_stripe_linked_accounts(limit=200)
    reconcile_rows = [
        [
            f"<code>{esc(row.get('id'))}</code>",
            esc(row.get("plan_code") or ""),
            esc(row.get("status") or ""),
            f"<code>{esc(row.get('provider_subscription_id') or '')}</code>",
            f"<code>{esc(row.get('provider_customer_id') or '—')}</code>",
        ]
        for row in linked
    ]
    reconcile_block = ""
    if settings.billing_provider == "stripe" or linked:
        reconcile_block = f"""
  <div class="card" style="margin-top:16px;">
    <div class="card-header"><h2>Stripe 对账（subscription ↔ BA）</h2></div>
    <div class="card-body" style="padding:0;">
      {render_table(
          ["billing_account_id", "plan", "status", "provider_subscription_id", "provider_customer_id"],
          reconcile_rows or [["—", "—", "—", "（无已链接订阅）", "—"]],
      )}
    </div>
  </div>
"""
    body = f"""
  {_ops_nav(base, "billing")}
  {_flash(request)}
  <div class="alert info">{esc(overview["note"])}</div>
  {cards}
  <div class="card" style="margin-top:16px;">
    <div class="card-header"><h2>环境变量白名单（只读）</h2></div>
    <div class="card-body" style="padding:0;">
      {render_table(["Principal ID", "来源"], env_rows)}
    </div>
  </div>
  {reconcile_block}
  <p class="card-muted" style="margin-top:12px;">
    要持久化付费身份，请到
    <a href="{esc(base)}/ui/observatory/users/">用户 / 付费</a>
    将用户设为 Pro（写入个人组织的 <code>billing_accounts</code>，并投影到 <code>principals.plan_code</code>）。
  </p>
"""
    return HTMLResponse(
        render_page(
            title="付费概况",
            base=base,
            active_nav="observatory",
            subtitle="运营查看：付费用户、组织与 billing accounts（无 Stripe）。",
            user_line=user_line,
            show_logout=settings.portal_auth_enabled,
            is_admin=bool(user and user.is_admin) or not settings.portal_auth_enabled,
            body=body,
        )
    )


@router.get("/users", response_class=HTMLResponse)
@router.get("/users/", response_class=HTMLResponse)
def observatory_users(
    request: Request,
    q: str = Query(""),
    paid_only: int = Query(0),
) -> Response:
    denied = _require_observatory_admin(request)
    if denied is not None:
        return denied
    user, user_line = _observatory_user_line(request)
    base = str(request.base_url).rstrip("/")
    total, rows = billing_ops_service.list_users_for_billing(
        query=q or None, paid_only=bool(paid_only), limit=100, offset=0
    )
    table_rows: list[list[Any]] = []
    for row in rows:
        pid = str(row["principal_id"])
        sources = ",".join(row.get("paid_sources") or []) or "—"
        paid_badge = badge("付费", "success") if row.get("effective_paid") else badge("免费", "muted")
        plan = str(row.get("plan_code") or "free")
        if row.get("effective_paid"):
            action = (
                f'<form method="post" action="{esc(base)}/ui/observatory/users/plan" style="display:inline;" '
                f'onsubmit="return confirm(\'确认取消付费（设为 free）？环境白名单仍会覆盖。\');">'
                f'<input type="hidden" name="principal_id" value="{esc(pid)}" />'
                f'<input type="hidden" name="plan_code" value="free" />'
                f'<input type="hidden" name="q" value="{esc(q)}" />'
                f'<input type="hidden" name="paid_only" value="{esc(paid_only)}" />'
                f'<button type="submit" class="btn">取消付费</button>'
                f"</form>"
            )
        else:
            action = (
                f'<form method="post" action="{esc(base)}/ui/observatory/users/plan" style="display:inline;" '
                f'onsubmit="return confirm(\'确认设为付费用户（Pro）？\');">'
                f'<input type="hidden" name="principal_id" value="{esc(pid)}" />'
                f'<input type="hidden" name="plan_code" value="pro" />'
                f'<input type="hidden" name="q" value="{esc(q)}" />'
                f'<input type="hidden" name="paid_only" value="{esc(paid_only)}" />'
                f'<button type="submit" class="btn primary">设为付费</button>'
                f"</form>"
            )
        table_rows.append(
            [
                f"<code>{esc(pid)}</code>",
                esc(row.get("display_name") or ""),
                paid_badge,
                esc(plan),
                esc(sources),
                esc(row.get("created_at") or ""),
                action,
            ]
        )
    checked = " checked" if paid_only else ""
    body = f"""
  {_ops_nav(base, "users")}
  {_flash(request)}
  <div class="card">
    <div class="card-header"><h2>用户付费状态（{esc(total)}）</h2></div>
    <div class="card-body">
      <form method="get" action="{esc(base)}/ui/observatory/users/" class="actions" style="margin-bottom:12px;">
        <input type="search" name="q" value="{esc(q)}" placeholder="显示名或 principal_id" style="min-width:240px;" />
        <label style="margin-left:8px;"><input type="checkbox" name="paid_only" value="1"{checked} /> 仅付费</label>
        <button type="submit" class="btn">搜索</button>
      </form>
      <div class="alert info">将用户设为付费会更新个人组织的 <code>billing_accounts.plan_code</code>（并投影到 <code>principals.plan_code</code>）。无需改 env / 重启。管理 API：<code>PATCH /api/admin/billing-accounts/&lt;ba_id&gt;</code>。</div>
      {render_table(
          ["Principal ID", "显示名", "生效", "DB plan", "来源", "创建时间", "操作"],
          table_rows,
      )}
    </div>
  </div>
"""
    return HTMLResponse(
        render_page(
            title="用户 / 付费",
            base=base,
            active_nav="observatory",
            subtitle="查看与设置付费用户（Pro）。",
            user_line=user_line,
            show_logout=settings.portal_auth_enabled,
            is_admin=bool(user and user.is_admin) or not settings.portal_auth_enabled,
            body=body,
        )
    )


@router.post("/users/plan")
async def observatory_set_user_plan(
    request: Request,
    principal_id: str = Form(...),
    plan_code: str = Form(...),
    q: str = Form(""),
    paid_only: str = Form("0"),
) -> Response:
    denied = _require_observatory_admin(request)
    if denied is not None:
        return denied
    _assert_same_origin(request)
    base = str(request.base_url).rstrip("/")
    redirect_q = f"q={quote(q)}&paid_only={quote(paid_only)}"
    code = str(plan_code or "").strip().lower()
    if code not in {"free", "pro"}:
        return RedirectResponse(
            f"{base}/ui/observatory/users/?{redirect_q}&error={quote('plan_code 仅支持 free/pro')}",
            status_code=303,
        )
    try:
        result = set_user_paid(principal_id=principal_id.strip(), paid=(code == "pro"))
    except Exception as exc:  # noqa: BLE001 — surface as flash
        from fastapi import HTTPException

        if isinstance(exc, HTTPException):
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        else:
            detail = str(exc)
        return RedirectResponse(
            f"{base}/ui/observatory/users/?{redirect_q}&error={quote(detail)}",
            status_code=303,
        )
    label = "已设为付费 (pro)" if result["paid"] else "已取消付费 (free)"
    if result.get("env_whitelist") and not result["paid"]:
        label += "；注意：仍在 MA3_PAID_PRINCIPAL_IDS 中，生效仍为付费"
    return RedirectResponse(
        f"{base}/ui/observatory/users/?{redirect_q}&ok={quote(label + ': ' + result['principal_id'])}",
        status_code=303,
    )


@router.get("/orgs", response_class=HTMLResponse)
@router.get("/orgs/", response_class=HTMLResponse)
def observatory_orgs(request: Request) -> Response:
    denied = _require_observatory_admin(request)
    if denied is not None:
        return denied
    user, user_line = _observatory_user_line(request)
    base = str(request.base_url).rstrip("/")
    orgs = billing_ops_service.list_orgs_for_billing(limit=300)
    table_rows = []
    for org in orgs:
        owner_paid = badge("owner付费", "success") if org.get("owner_effective_paid") else badge("owner免费", "muted")
        table_rows.append(
            [
                f"<code>{esc(org.get('id'))}</code>",
                esc(org.get("name") or ""),
                badge(str(org.get("kind") or ""), "muted"),
                f"<code>{esc(org.get('owner_principal_id') or '—')}</code>",
                owner_paid,
                esc(org.get("billing_label") or "—"),
                esc(org.get("member_count") or 0),
            ]
        )
    body = f"""
  {_ops_nav(base, "orgs")}
  {_flash(request)}
  <div class="card">
    <div class="card-header"><h2>组织与付费标签（{esc(len(orgs))}）</h2></div>
    <div class="card-body">
      <div class="alert info">组织 <code>billing_account_id</code> 现为真实 <code>ba_*</code> 账户（P0）。列表中显示 BA id 与 <code>plan_code</code>（如 <code>team_stub</code> / <code>team</code> / <code>pro</code>）。</div>
      {render_table(
          ["Org ID", "名称", "类型", "Owner", "Owner 状态", "billing_account_id", "成员数"],
          table_rows,
      )}
    </div>
  </div>
"""
    return HTMLResponse(
        render_page(
            title="组织",
            base=base,
            active_nav="observatory",
            subtitle="组织列表与 billing 标签。",
            user_line=user_line,
            show_logout=settings.portal_auth_enabled,
            is_admin=bool(user and user.is_admin) or not settings.portal_auth_enabled,
            body=body,
        )
    )


@router.get("/local-users", response_class=HTMLResponse)
@router.get("/local-users/", response_class=HTMLResponse)
def observatory_local_users(request: Request) -> Response:
    denied = _require_observatory_admin(request)
    if denied is not None:
        return denied
    user, user_line = _observatory_user_line(request)
    base = str(request.base_url).rstrip("/")
    if not settings.local_auth_enabled:
        body = f"""
  {_ops_nav(base, "local")}
  <div class="alert info">当前未启用本地账号（OIDC 已配置，或 <code>MA3_LOCAL_AUTH=0</code>）。</div>
"""
    else:
        rows = []
        for acc in local_auth_service.list_local_accounts():
            uname = str(acc["username"])
            is_admin = bool(int(acc.get("is_admin") or 0))
            admin_badge = badge("管理员", "success") if is_admin else badge("普通", "muted")
            toggle = "0" if is_admin else "1"
            label = "取消管理员" if is_admin else "设为管理员"
            action = f"""
            <form method="post" action="{esc(base)}/ui/observatory/local-users/admin" style="display:inline;"
                  onsubmit="return confirm('确认修改管理员权限？');">
              <input type="hidden" name="username" value="{esc(uname)}" />
              <input type="hidden" name="is_admin" value="{esc(toggle)}" />
              <button type="submit" class="btn">{esc(label)}</button>
            </form>"""
            rows.append(
                [
                    esc(uname),
                    f"<code>{esc(acc.get('principal_id'))}</code>",
                    admin_badge,
                    esc(acc.get("created_at") or ""),
                    action,
                ]
            )
        reg_open = local_auth_service.is_registration_open()
        toggle_val = "0" if reg_open else "1"
        toggle_label = "关闭开放注册" if reg_open else "开启开放注册"
        body = f"""
  {_ops_nav(base, "local")}
  {_flash(request)}
  <div class="card">
    <div class="card-header"><h2>本地账号（{esc(storage_db.count_local_accounts())}）</h2></div>
    <div class="card-body">
      <div class="alert info">
        开放注册：{"开" if reg_open else "关"}（数据库覆盖 env；无需重启）。
        首个注册用户自动成为管理员。也可访问 <a href="{esc(base)}/auth/register">/auth/register</a>
        或 <a href="{esc(base)}/ui/setup/">/ui/setup/</a>。
      </div>
      <form method="post" action="{esc(base)}/ui/observatory/local-users/registration" style="margin-bottom:16px;"
            onsubmit="return confirm('确认修改开放注册？');">
        <input type="hidden" name="open" value="{esc(toggle_val)}" />
        <button type="submit" class="btn">{esc(toggle_label)}</button>
      </form>
      {render_table(["用户名", "Principal", "角色", "创建时间", "操作"], rows)}
    </div>
  </div>
"""
    return HTMLResponse(
        render_page(
            title="本地账号",
            base=base,
            active_nav="observatory",
            subtitle="自托管本地用户注册与管理员管理。",
            user_line=user_line,
            show_logout=settings.portal_auth_enabled,
            is_admin=bool(user and user.is_admin) or not settings.portal_auth_enabled,
            body=body,
        )
    )


@router.post("/local-users/registration")
async def observatory_local_users_set_registration(
    request: Request,
    open: str = Form(...),
) -> Response:
    denied = _require_observatory_admin(request)
    if denied is not None:
        return denied
    _assert_same_origin(request)
    base = str(request.base_url).rstrip("/")
    if not settings.local_auth_enabled:
        return RedirectResponse(f"{base}/ui/observatory/local-users/?error={quote('local auth off')}", status_code=303)
    want_open = str(open).strip() in {"1", "true", "yes", "on"}
    setup_service.set_registration_open(want_open)
    msg = "registration opened" if want_open else "registration closed"
    return RedirectResponse(
        f"{base}/ui/observatory/local-users/?ok={quote(msg)}",
        status_code=303,
    )


@router.post("/local-users/admin")
async def observatory_local_users_set_admin(
    request: Request,
    username: str = Form(...),
    is_admin: str = Form(...),
) -> Response:
    denied = _require_observatory_admin(request)
    if denied is not None:
        return denied
    _assert_same_origin(request)
    base = str(request.base_url).rstrip("/")
    if not settings.local_auth_enabled:
        return RedirectResponse(f"{base}/ui/observatory/local-users/?error={quote('local auth off')}", status_code=303)
    want_admin = str(is_admin).strip() in {"1", "true", "yes", "on"}
    row = local_auth_service.set_local_account_admin(username=username, is_admin=want_admin)
    if row is None:
        return RedirectResponse(f"{base}/ui/observatory/local-users/?error={quote('user not found')}", status_code=303)
    return RedirectResponse(
        f"{base}/ui/observatory/local-users/?ok={quote('updated: ' + username)}",
        status_code=303,
    )
