#!/usr/bin/env python3
"""Render ma3 SSR pages to HTML + PNG for visual review."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from app.auth.session import SessionUser  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services.onboarding_service import ensure_personal_library  # noqa: E402
from app.storage.db import initialize_database  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

OUT = Path("/tmp/ma3-ui-preview")
OUT.mkdir(parents=True, exist_ok=True)

initialize_database()

session_user = SessionUser(
    principal_id="user:ui-preview",
    sub="ui-preview",
    display_name="Nova Dev",
    email="nova@example.com",
    phone=None,
    is_admin=False,
)
ensure_personal_library(session_user.principal_id, session_user.display_name)

settings.authing_enabled = True
settings.authing_issuer = "https://example.authing.cn"
settings.authing_app_id = "preview"
settings.authing_app_secret = "preview"

import app.api.routes_keys as routes_keys  # noqa: E402
import app.auth.session as session_mod  # noqa: E402

with patch.object(session_mod, "resolve_session_user", return_value=session_user), patch.object(
    routes_keys, "resolve_session_user", return_value=session_user
):
    client = TestClient(app)
    pages = {
        "observatory": client.get("/ui/observatory/").text,
        "keys": client.get("/ui/keys/").text,
        "keys-disabled": client.get("/ui/keys/", headers={"Host": "testserver"}).text,
    }

# authing disabled page
settings.authing_enabled = False
settings.authing_issuer = None
settings.authing_app_id = None
settings.authing_app_secret = None
client2 = TestClient(app)
pages["keys-authing-disabled"] = client2.get("/ui/keys/").text
pages["observatory-open"] = client2.get("/ui/observatory/").text

# created page via direct render
from app.api.routes_keys import _render_created_page  # noqa: E402

base = "http://127.0.0.1:8000"
pages["keys-created"] = _render_created_page(
    base,
    session_user,
    {
        "plaintext_key": "ma3_live_preview_key_abcdefghijklmnopqrstuvwxyz",
        "key_prefix": "ma3_live",
        "label": "my-laptop-agent",
    },
)

for name, html in pages.items():
    path = OUT / f"{name}.html"
    path.write_text(html, encoding="utf-8")
    print(f"wrote {path}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    for name in pages:
        html_path = OUT / f"{name}.html"
        png_path = OUT / f"{name}.png"
        page.goto(html_path.as_uri(), wait_until="networkidle")
        page.wait_for_timeout(1500)
        page.screenshot(path=str(png_path), full_page=True)
        print(f"screenshot {png_path}")
    browser.close()

print(f"done -> {OUT}")
