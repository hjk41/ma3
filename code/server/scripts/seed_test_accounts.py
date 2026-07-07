#!/usr/bin/env python3
"""Seed LAN/staging test accounts: Authing user + ma3 principal + personal org + API key.

Idempotent: reuses existing Authing users (sign-in) when signup reports duplicate.

Usage (on 202):
  set -a && source ma3.env && set +a
  python scripts/seed_test_accounts.py
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.services.api_key_encryption import encrypt_stored_key  # noqa: E402
from app.services.api_key_service import hash_key  # noqa: E402
from app.services.onboarding_service import ensure_personal_org  # noqa: E402
from app.services.org_service import seed_team_org  # noqa: E402
from app.storage import db  # noqa: E402

DEFAULT_PASSWORD = "Ma3Test2026!"


@dataclass(frozen=True, slots=True)
class TestAccountSpec:
    username: str
    display_name: str
    key_id: str
    plaintext_key: str
    paid: bool = False


ACCOUNTS: tuple[TestAccountSpec, ...] = (
    TestAccountSpec(
        username="ma3test_alice",
        display_name="Test Alice",
        key_id="key_test_alice",
        plaintext_key="ma3k_test_alice_202",
    ),
    TestAccountSpec(
        username="ma3test_bob",
        display_name="Test Bob",
        key_id="key_test_bob",
        plaintext_key="ma3k_test_bob_202",
    ),
    TestAccountSpec(
        username="ma3test_carol",
        display_name="Test Carol",
        key_id="key_test_carol",
        plaintext_key="ma3k_test_carol_202",
        paid=True,
    ),
    TestAccountSpec(
        username="ma3test_dave",
        display_name="Test Dave",
        key_id="key_test_dave",
        plaintext_key="ma3k_test_dave_202",
    ),
)

TEAM_ORG_NAME = "Acme Test Team"


def _http_client() -> httpx.Client:
    proxy = os.environ.get("MA3_HTTP_PROXY") or os.environ.get("HTTP_PROXY")
    kwargs: dict = {"timeout": 20.0}
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.Client(**kwargs)


def _jwt_sub(access_token: str) -> str:
    payload = access_token.split(".")[1]
    padding = "=" * (-len(payload) % 4)
    data = json.loads(base64.urlsafe_b64decode(payload + padding))
    sub = str(data.get("sub") or "")
    if not sub:
        raise ValueError("missing sub in access token")
    return sub


def _authing_password_auth(client: httpx.Client, *, username: str, password: str) -> str:
    app_id = settings.authing_app_id
    secret = settings.authing_app_secret
    if not app_id or not secret:
        raise RuntimeError("MA3_AUTHING_APP_ID and MA3_AUTHING_APP_SECRET are required")
    headers = {"x-authing-app-id": app_id, "Content-Type": "application/json"}
    body = {
        "client_id": app_id,
        "client_secret": secret,
        "connection": "PASSWORD",
        "passwordPayload": {"username": username, "password": password},
    }
    resp = client.post("https://api.authing.cn/api/v3/signin", headers=headers, json=body)
    payload = resp.json()
    if payload.get("statusCode") == 200:
        token = str(payload.get("data", {}).get("access_token") or "")
        if token:
            return _jwt_sub(token)
    raise RuntimeError(f"Authing sign-in failed for {username}: {payload}")


def _ensure_authing_user(client: httpx.Client, *, username: str, password: str, nickname: str) -> str:
    app_id = settings.authing_app_id
    if not app_id:
        raise RuntimeError("MA3_AUTHING_APP_ID is required")
    headers = {"x-authing-app-id": app_id, "Content-Type": "application/json"}
    resp = client.post(
        "https://api.authing.cn/api/v3/signup",
        headers=headers,
        json={
            "connection": "PASSWORD",
            "passwordPayload": {"username": username, "password": password},
            "profile": {"nickname": nickname},
        },
    )
    body = resp.json()
    if body.get("statusCode") == 200 and body.get("data", {}).get("userId"):
        return str(body["data"]["userId"])
    message = str(body.get("message") or body)
    if "已存在" in message or "already exists" in message.lower():
        return _authing_password_auth(client, username=username, password=password)
    raise RuntimeError(f"Authing signup failed for {username}: {body}")


def _ensure_api_key(*, principal_id: str, personal_library_id: str, spec: TestAccountSpec) -> None:
    existing = db.get_api_key_by_id(spec.key_id)
    if existing is None:
        db.insert_api_key(
            key_id=spec.key_id,
            key_hash=hash_key(spec.plaintext_key),
            key_prefix=spec.plaintext_key[:12],
            key_ciphertext=encrypt_stored_key(spec.plaintext_key),
            principal_id=principal_id,
            label=f"{spec.display_name} test key",
            grants=[
                {"library_id": personal_library_id, "role": "writer"},
                {"library_id": settings.default_library_id, "role": "writer"},
            ],
        )


def _seed_account(client: httpx.Client, spec: TestAccountSpec, *, password: str) -> dict:
    sso_user = _ensure_authing_user(
        client,
        username=spec.username,
        password=password,
        nickname=spec.display_name,
    )
    principal_id = f"user:{sso_user}"
    db.upsert_user_principal(sso_user=sso_user, display_name=spec.display_name)
    db.set_user_display_name(principal_id, spec.display_name)
    org = ensure_personal_org(principal_id, spec.display_name)
    personal_library_id = str(org["personal_library_id"])
    _ensure_api_key(principal_id=principal_id, personal_library_id=personal_library_id, spec=spec)
    return {
        "username": spec.username,
        "principal_id": principal_id,
        "display_name": spec.display_name,
        "paid": spec.paid,
        "key_id": spec.key_id,
        "plaintext_key": spec.plaintext_key,
        "personal_library_id": personal_library_id,
    }


def _seed_team_org(rows: list[dict]) -> str | None:
    by_name = {row["display_name"]: row for row in rows}
    carol = by_name.get("Test Carol")
    alice = by_name.get("Test Alice")
    bob = by_name.get("Test Bob")
    if not carol:
        return None
    team_orgs = [
        org
        for org in db.list_orgs_for_principal(carol["principal_id"])
        if org.get("kind") == "team" and org.get("name") == TEAM_ORG_NAME
    ]
    if team_orgs:
        org_id = str(team_orgs[0]["id"])
    else:
        org_id = str(seed_team_org(name=TEAM_ORG_NAME, admin_principal_id=carol["principal_id"])["id"])
    if alice and not db.get_org_member(org_id, alice["principal_id"]):
        db.add_org_member(org_id=org_id, principal_id=alice["principal_id"], role="member")
    if bob and not db.get_org_member(org_id, bob["principal_id"]):
        db.add_org_member(org_id=org_id, principal_id=bob["principal_id"], role="member")
    return org_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed ma3 test accounts on Authing + DB")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Authing login password for all accounts")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary")
    args = parser.parse_args()

    db.initialize_database()
    rows: list[dict] = []
    with _http_client() as client:
        for spec in ACCOUNTS:
            rows.append(_seed_account(client, spec, password=args.password))

    team_org_id = _seed_team_org(rows)
    paid_ids = sorted({row["principal_id"] for row in rows if row["paid"]})

    if paid_ids:
        print("MA3_PAID_PRINCIPAL_IDS=" + ",".join(paid_ids))
    if team_org_id:
        print(f"team_org_id={team_org_id} name={TEAM_ORG_NAME}")

    if args.json:
        print(
            json.dumps(
                {"accounts": rows, "paid_principal_ids": paid_ids, "team_org_id": team_org_id},
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(f"password={args.password}")
        for row in rows:
            paid = " (Pro)" if row["paid"] else ""
            print(
                f"- {row['username']}{paid}: principal={row['principal_id']} "
                f"display_name={row['display_name']} api_key={row['plaintext_key']}"
            )
        print("Login: /auth/login → 密码登录 → username + password")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
