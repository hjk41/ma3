from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import assert_same_origin, allowed_ui_origins


def test_allowed_ui_origins_includes_request_base_and_public_url(monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "https://ma3.io")
    request = MagicMock()
    request.base_url = "http://192.168.31.202:8000/"
    origins = allowed_ui_origins(request)
    assert "https://ma3.io" in origins
    assert "http://192.168.31.202:8000" in origins


def test_assert_same_origin_accepts_request_host_when_public_url_differs(monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "https://ma3.io")
    request = MagicMock()
    request.method = "POST"
    request.base_url = "http://192.168.31.202:8000/"
    request.headers = {"origin": "http://192.168.31.202:8000"}
    assert_same_origin(request)


def test_assert_same_origin_accepts_public_base_url(monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "https://ma3.io")
    request = MagicMock()
    request.method = "POST"
    request.base_url = "http://192.168.31.202:8000/"
    request.headers = {"origin": "https://ma3.io"}
    assert_same_origin(request)


def test_assert_same_origin_rejects_foreign_origin(monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "https://ma3.io")
    request = MagicMock()
    request.method = "POST"
    request.base_url = "http://192.168.31.202:8000/"
    request.headers = {"origin": "https://evil.example"}
    with pytest.raises(HTTPException) as exc:
        assert_same_origin(request)
    assert exc.value.status_code == 403
    assert exc.value.detail == "cross-origin request rejected"
