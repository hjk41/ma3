"""Observatory ops helpers for paid users / org billing overview (no Stripe)."""
from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.services.onboarding_service import is_paid_principal
from app.storage import db


def billing_overview() -> dict[str, Any]:
    env_ids = list(settings.paid_principal_ids)
    db_paid = db.count_principals_by_plan_code("pro")
    orgs = db.list_organizations_for_ops(limit=500)
    team_orgs = [o for o in orgs if str(o.get("kind") or "") == "team"]
    personal_orgs = [o for o in orgs if str(o.get("kind") or "") == "personal"]
    labeled = [o for o in orgs if str(o.get("billing_account_id") or "").startswith("plan:")]
    return {
        "env_paid_count": len(env_ids),
        "env_paid_principal_ids": env_ids,
        "db_pro_count": db_paid,
        "org_count": len(orgs),
        "team_org_count": len(team_orgs),
        "personal_org_count": len(personal_orgs),
        "orgs_with_plan_label": len(labeled),
        "note": (
            "付费以 principals.plan_code=pro 为准；MA3_PAID_PRINCIPAL_IDS 仍可作为 env 白名单覆盖。"
            "完整 Stripe billing 尚未接入。"
        ),
    }


def enrich_user_billing_row(row: dict[str, Any]) -> dict[str, Any]:
    principal_id = str(row.get("principal_id") or "")
    plan_code = str(row.get("plan_code") or "free").lower() or "free"
    env_hit = principal_id in settings.paid_principal_ids
    effective = is_paid_principal(principal_id)
    sources: list[str] = []
    if plan_code == "pro":
        sources.append("db")
    if env_hit:
        sources.append("env")
    return {
        **row,
        "plan_code": plan_code,
        "env_whitelist": env_hit,
        "effective_paid": effective,
        "paid_sources": sources,
    }


def list_users_for_billing(
    *,
    query: str | None = None,
    paid_only: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> tuple[int, list[dict[str, Any]]]:
    total, rows = db.list_user_principals_for_ops(
        query=query, paid_only=paid_only, limit=limit, offset=offset
    )
    enriched = [enrich_user_billing_row(r) for r in rows]
    if paid_only:
        # Also surface env-only paid users that are not plan_code=pro yet.
        env_only = []
        seen = {str(r["principal_id"]) for r in enriched}
        for pid in settings.paid_principal_ids:
            if pid in seen:
                continue
            principal = db.get_user_principal(pid)
            if not principal:
                env_only.append(
                    enrich_user_billing_row(
                        {
                            "principal_id": pid,
                            "kind": "user",
                            "display_name": "(env only — not in DB)",
                            "plan_code": "free",
                            "created_at": "",
                        }
                    )
                )
                continue
            if query:
                q = query.lower()
                if q not in str(principal.get("display_name") or "").lower() and q not in pid.lower():
                    continue
            env_only.append(enrich_user_billing_row(principal))
        if env_only:
            enriched = env_only + enriched
            total = total + len(env_only)
    return total, enriched


def list_orgs_for_billing(*, limit: int = 200) -> list[dict[str, Any]]:
    rows = db.list_organizations_for_ops(limit=limit)
    out: list[dict[str, Any]] = []
    for org in rows:
        owner = str(org.get("owner_principal_id") or "")
        billing = str(org.get("billing_account_id") or "")
        owner_paid = is_paid_principal(owner) if owner else False
        out.append(
            {
                **org,
                "billing_label": billing or "—",
                "owner_effective_paid": owner_paid,
            }
        )
    return out
